from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


MEMORY_TYPES = {"preference", "decision", "note", "command", "session"}
MEMORY_SCOPES = {"global", "project"}
MEMORY_STATUSES = {"pending", "active", "pinned", "archived", "expired"}
VISIBILITIES = {"private", "team"}
MAX_TEXT_LENGTH = 1200
RECENCY_WINDOW_SECONDS = 60 * 60 * 24 * 30

SECRET_PATTERNS = [
    re.compile(r"\bsk-[a-zA-Z0-9_-]{12,}\b"),
    re.compile(r"\bgh[pousr]_[a-zA-Z0-9_]{20,}\b"),
    re.compile(r"\b(api[_-]?key|token|secret|password|passwd|cookie)\s*[:=]\s*\S+", re.I),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]

RELATED_TERMS = {
    "agent": ["assistant", "coding", "tool", "tools", "model", "models"],
    "agents": ["assistant", "assistants", "coding", "tools", "models"],
    "assistant": ["agent", "agents", "coding"],
    "context": ["memory", "memories", "preference", "preferences", "knowledge"],
    "memory": ["context", "memories", "preference", "preferences", "knowledge", "vault"],
    "memories": ["memory", "context", "knowledge", "vault"],
    "shared": ["share", "portable", "cross", "between", "common"],
    "switch": ["handoff", "portable", "between", "move"],
    "switching": ["handoff", "portable", "between", "move"],
    "bootstrap": ["start", "startup", "task-start", "context"],
    "review": ["approve", "approval", "pending"],
    "release": ["ship", "publish", "version"],
    "test": ["tests", "testing", "verify", "verification"],
}

FIELD_WEIGHTS = {
    "text": 4,
    "type": 3,
    "tags": 5,
    "projectName": 2,
    "status": 1,
    "visibility": 0.5,
}


def call_across_context_tool(tool_name: str, arguments: Dict[str, Any], env: Optional[Dict[str, str]] = None) -> str:
    vault = AcrossContextVault(env=env)
    if tool_name == "remember_context":
        entry = vault.remember(arguments)
        return f"Remembered {entry['status']} {entry['scope']} {entry['type']}: {entry['text']}"
    if tool_name == "search_context":
        results = vault.search(arguments)
        return "\n".join(f"- {item['entry']['text']}" for item in results) or "No matching context found."
    if tool_name == "get_project_context":
        return vault.render_context_document(_required_project_root(arguments))
    if tool_name == "review_pending_memories":
        memories = vault.list_memories(arguments.get("projectRoot"), status="pending", include_global=True)
        return "\n".join(f"- {item['id']}: {item['text']}" for item in memories) or "No pending memories."
    if tool_name == "approve_memory":
        memory_id = str(arguments.get("id") or "").strip()
        if not memory_id:
            raise ValueError("id is required")
        entry = vault.update_status(memory_id, "active")
        return f"Approved {entry['id']}: {entry['text']}"
    if tool_name == "get_agent_card":
        return json.dumps(agent_card(), ensure_ascii=False, indent=2)
    if tool_name == "export_agent_instructions":
        project_root = _required_project_root(arguments)
        target = str(arguments.get("target") or "agents")
        result = vault.export_context(project_root, target)
        return f"Exported {result['target']} context to {result['path']}"
    raise ValueError(f"Unsupported Across Context tool: {tool_name}")


class AcrossContextVault:
    def __init__(self, env: Optional[Dict[str, str]] = None):
        source_env = env or os.environ
        self.env = source_env
        explicit_home = str(source_env.get("ACROSS_CONTEXT_HOME") or "").strip()
        across_home = str(source_env.get("ACROSS_HOME") or "").strip()
        if explicit_home:
            self.home = Path(explicit_home).expanduser().resolve()
            self.should_migrate_legacy = False
        else:
            root = Path(across_home).expanduser() if across_home else Path.home() / ".across"
            self.home = (root / "data" / "across-context").resolve()
            self.should_migrate_legacy = True

    def init(self) -> None:
        self._migrate_legacy_default_vault()
        (self.home / "global").mkdir(parents=True, exist_ok=True)
        (self.home / "projects").mkdir(parents=True, exist_ok=True)
        (self.home / "global" / "memories.jsonl").touch(exist_ok=True)

    def _migrate_legacy_default_vault(self) -> None:
        if not self.should_migrate_legacy or self.home.exists():
            return
        home = str(self.env.get("HOME") or "").strip()
        legacy = ((Path(home).expanduser() if home else Path.home()) / ".across-context").resolve()
        if legacy == self.home or not legacy.exists():
            return
        shutil.copytree(legacy, self.home)

    def remember(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        self.init()
        text = normalize_whitespace(arguments.get("text"))
        if not text:
            raise ValueError("Memory text is required")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            raise ValueError("Memory looks like a secret or credential")

        scope = normalize_choice(arguments.get("scope") or "global", MEMORY_SCOPES, "scope")
        memory_type = normalize_choice(arguments.get("type") or "note", MEMORY_TYPES, "type")
        project_root = str(arguments.get("projectRoot") or "").strip()
        if scope == "project" and not project_root:
            raise ValueError("projectRoot is required for project memories")

        existing = self.list_memories(project_root or None, include_global=True)
        duplicate = find_duplicate(text, scope, memory_type, existing)
        if duplicate:
            return {
                **duplicate,
                "duplicateOf": duplicate.get("id"),
                "policy": {"status": "duplicate", "reason": "A matching memory already exists."},
            }

        trimmed_text = text[: MAX_TEXT_LENGTH - 3].rstrip() + "..." if len(text) > MAX_TEXT_LENGTH else text
        status = normalize_choice(
            arguments.get("status") or default_status(bool(arguments.get("auto", True)), memory_type),
            MEMORY_STATUSES,
            "status",
        )
        visibility = normalize_choice(arguments.get("visibility") or "private", VISIBILITIES, "visibility")
        timestamp = now_iso()
        entry: Dict[str, Any] = {
            "id": f"mem_{uuid.uuid4().hex[:18]}",
            "scope": scope,
            "type": memory_type,
            "text": trimmed_text,
            "tags": split_tags(arguments.get("tags") or []),
            "source": "mcp",
            "status": status,
            "visibility": visibility,
            "policy": {"status": "allow", "trimmed": trimmed_text != text},
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }

        file = self.home / "global" / "memories.jsonl"
        if scope == "project":
            root = resolved_project_root(project_root)
            entry["projectId"] = stable_project_id(root)
            entry["projectName"] = Path(root).name or "project"
            project_dir = self.home / "projects" / entry["projectId"]
            project_dir.mkdir(parents=True, exist_ok=True)
            file = project_dir / "memories.jsonl"
            file.touch(exist_ok=True)

        with file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(drop_none(entry), ensure_ascii=False) + "\n")
        return drop_none(entry)

    def list_memories(
        self,
        project_root: Optional[str] = None,
        *,
        include_global: bool = True,
        status: Optional[str] = None,
        visibility: Optional[str] = None,
        memory_type: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        self.init()
        memories: List[Dict[str, Any]] = []
        if include_global:
            memories.extend(read_jsonl(self.home / "global" / "memories.jsonl"))
        if project_root:
            memories.extend(read_jsonl(self.home / "projects" / stable_project_id(resolved_project_root(project_root)) / "memories.jsonl"))
        memories = [
            item
            for item in memories
            if (not status or (item.get("status") or "active") == status)
            and (not visibility or (item.get("visibility") or "private") == visibility)
            and (not memory_type or item.get("type") == memory_type)
            and (not scope or item.get("scope") == scope)
        ]
        return sorted(memories, key=lambda item: str(item.get("createdAt") or ""))

    def search(self, arguments: Dict[str, Any]) -> List[Dict[str, Any]]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            return []
        memories = self.list_memories(
            arguments.get("projectRoot"),
            include_global=True,
            status=arguments.get("status"),
        )
        return search_entries(memories, query, mode=str(arguments.get("mode") or "hybrid"), limit=int(arguments.get("limit") or 10))

    def update_status(self, memory_id: str, status: str) -> Dict[str, Any]:
        self.init()
        next_status = normalize_choice(status, MEMORY_STATUSES, "status")
        for file in self.memory_files():
            memories = read_jsonl(file)
            for index, entry in enumerate(memories):
                if entry.get("id") != memory_id:
                    continue
                updated = {**entry, "status": next_status, "updatedAt": now_iso()}
                memories[index] = updated
                write_jsonl(file, memories)
                return updated
        raise ValueError(f"Memory not found: {memory_id}")

    def forget(self, memory_id: str) -> Dict[str, Any]:
        self.init()
        removed = False
        for file in self.memory_files():
            memories = read_jsonl(file)
            next_memories = [entry for entry in memories if entry.get("id") != memory_id]
            if len(next_memories) != len(memories):
                write_jsonl(file, next_memories)
                removed = True
        return {"forgotten": removed, "id": memory_id}

    def memory_files(self) -> Iterable[Path]:
        yield self.home / "global" / "memories.jsonl"
        projects_root = self.home / "projects"
        if projects_root.exists():
            for child in projects_root.iterdir():
                if child.is_dir():
                    yield child / "memories.jsonl"

    def render_context_document(self, project_root: str) -> str:
        root = resolved_project_root(project_root)
        memories = self.list_memories(root, include_global=True)
        global_memories = [item for item in memories if item.get("scope") == "global"]
        project_memories = [item for item in memories if item.get("scope") == "project"]
        lines = [
            "# Agent Context",
            "",
            "This file is generated by Across Context. It contains sanitized operating context for coding agents.",
            "",
            "## Project",
            "",
            f"- Name: {Path(root).name or 'project'}",
            "",
        ]
        append_memory_section(lines, "Global Preferences", global_memories)
        append_memory_section(lines, "Project Memory", project_memories)
        lines.extend(
            [
                "## Across Context Automation",
                "",
                "- Task start memory lookup: before planning or editing, search Across Context for relevant global and project memory.",
                "- Before final response memory write: remember only durable user preferences, project decisions, reusable commands, and compact session summaries.",
                "- Pending review: use review_pending_memories or approve_memory before treating uncertain automatic memories as active context.",
                "- Never write secrets, API keys, tokens, credentials, cookies, huge logs, full chat history, temporary errors, private screenshots, or one-off noise.",
                "",
                "## Safety",
                "",
                "- Do not expose API keys, tokens, private local paths, or private project names in public output.",
                "- Prefer small, reviewable changes with tests or explicit verification evidence.",
                "",
            ]
        )
        return "\n".join(lines).strip() + "\n"

    def export_context(self, project_root: str, target: str) -> Dict[str, Any]:
        root = resolved_project_root(project_root)
        content = self.render_context_document(root)
        path = export_path(root, target)
        path.parent.mkdir(parents=True, exist_ok=True)
        final_content = f"---\nalwaysApply: true\n---\n\n{content}" if target == "cursor" else content
        path.write_text(final_content, encoding="utf-8")
        return {"path": str(path), "target": target, "bytes": len(final_content.encode("utf-8"))}


def search_entries(entries: List[Dict[str, Any]], query: str, *, mode: str, limit: int) -> List[Dict[str, Any]]:
    query_terms = unique(tokenize(query))
    expanded_terms = expand_terms(query_terms)
    results = []
    for entry in entries:
        scored = score_entry(entry, query_terms, expanded_terms, mode)
        if scored["score"] > 0:
            results.append({"entry": entry, **scored, "matchMode": mode})
    return sorted(results, key=lambda item: (-item["score"], str(item["entry"].get("createdAt") or "")), reverse=False)[:limit]


def score_entry(entry: Dict[str, Any], query_terms: List[str], expanded_terms: List[str], mode: str) -> Dict[str, Any]:
    fields = {
        "text": tokenize(entry.get("text")),
        "type": tokenize(entry.get("type")),
        "tags": tokenize(" ".join(entry.get("tags") or [])),
        "projectName": tokenize(entry.get("projectName")),
        "status": tokenize(entry.get("status") or "active"),
        "visibility": tokenize(entry.get("visibility") or "private"),
    }
    exact = score_terms(fields, query_terms, 3)
    related_terms = [term for term in expanded_terms if term not in query_terms]
    related = {"score": 0, "matchedTerms": [], "matchedFields": []} if mode == "keyword" else score_terms(fields, related_terms, 1)
    type_score = 3 if entry.get("type") in query_terms else 0
    status_score = 1 if (entry.get("status") or "active") in {"active", "pinned"} else 0
    recency = recency_score(entry)
    if mode == "keyword":
        total = exact["score"]
    elif mode == "semantic":
        total = related["score"] + exact["score"] + type_score + status_score + recency
    else:
        total = exact["score"] * 2 + related["score"] + type_score + status_score + recency
    return {
        "score": round(total, 3),
        "explanation": {
            "reason": "matched",
            "matchedTerms": unique([*exact["matchedTerms"], *related["matchedTerms"]]),
            "matchedFields": unique([*exact["matchedFields"], *related["matchedFields"]]),
            "scoreComponents": {
                "exact": round(exact["score"], 3),
                "related": round(related["score"], 3),
                "type": round(type_score, 3),
                "status": round(status_score, 3),
                "recency": round(recency, 3),
            },
        },
    }


def score_terms(fields: Dict[str, List[str]], terms: List[str], weight: float) -> Dict[str, Any]:
    matched_terms = set()
    matched_fields = set()
    score = 0.0
    for field, field_terms in fields.items():
        haystack = " ".join(field_terms)
        for term in terms:
            term_score = score_term(haystack, term, weight * FIELD_WEIGHTS.get(field, 1))
            if term_score > 0:
                score += term_score
                matched_terms.add(term)
                matched_fields.add(field)
    return {"score": score, "matchedTerms": sorted(matched_terms), "matchedFields": sorted(matched_fields)}


def score_term(haystack: str, term: str, weight: float) -> float:
    if not term:
        return 0
    if term in haystack:
        return weight
    if len(term) > 4 and stem(term) in haystack:
        return max(1, weight - 1)
    return 0


def recency_score(entry: Dict[str, Any]) -> float:
    try:
        created = datetime.fromisoformat(str(entry.get("createdAt") or "").replace("Z", "+00:00"))
    except ValueError:
        return 0
    age = max(0, (datetime.now(timezone.utc) - created).total_seconds())
    return max(0, 1 - age / RECENCY_WINDOW_SECONDS)


def tokenize(text: Any) -> List[str]:
    terms: List[str] = []
    for term in re.split(r"[^a-z0-9._-]+", str(text or "").lower()):
        term = term.strip()
        if term:
            terms.extend([term, stem(term)])
    return [term for term in terms if term]


def expand_terms(terms: List[str]) -> List[str]:
    expanded = set(terms)
    for term in terms:
        for related in RELATED_TERMS.get(term, []):
            expanded.add(related)
            expanded.add(stem(related))
    return sorted(term for term in expanded if term)


def stem(term: str) -> str:
    return re.sub(r"(ing|ers|ies|ied|ed|es|s)$", "", str(term or ""), flags=re.I)


def append_memory_section(lines: List[str], title: str, memories: List[Dict[str, Any]]) -> None:
    if not memories:
        return
    lines.extend([f"## {title}", ""])
    for entry in memories:
        tags = f" [{', '.join(entry.get('tags') or [])}]" if entry.get("tags") else ""
        lines.append(f"- ({entry.get('type')}) {entry.get('text')}{tags}")
    lines.append("")


def export_path(project_root: str, target: str) -> Path:
    root = Path(project_root)
    if target == "claude":
        return root / "CLAUDE.md"
    if target == "cursor":
        return root / ".cursor" / "rules" / "across-context.mdc"
    if target == "markdown":
        return root / "docs" / "agent-context.md"
    return root / "AGENTS.md"


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def write_jsonl(path: Path, entries: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(drop_none(entry), ensure_ascii=False) for entry in entries)
    path.write_text(f"{content}\n" if content else "", encoding="utf-8")


def resolved_project_root(project_root: str) -> str:
    return str(Path(project_root).expanduser().resolve())


def stable_project_id(project_root: str) -> str:
    root = resolved_project_root(project_root)
    digest = hashlib.sha256(root.encode("utf-8")).hexdigest()[:16]
    name = re.sub(r"[^a-zA-Z0-9._-]+", "-", Path(root).name) or "project"
    return f"{name}-{digest}"


def find_duplicate(text: str, scope: str, memory_type: str, memories: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    normalized = normalize_memory_text(text)
    for entry in memories:
        if entry.get("scope") == scope and entry.get("type") == memory_type and normalize_memory_text(entry.get("text")) == normalized:
            return entry
    return None


def normalize_memory_text(text: Any) -> str:
    return normalize_whitespace(text).lower()


def normalize_whitespace(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_choice(value: Any, choices: set[str], field: str) -> str:
    normalized = str(value or "").strip()
    if normalized not in choices:
        raise ValueError(f"Invalid {field}: {value}")
    return normalized


def default_status(auto: bool, memory_type: str) -> str:
    if not auto:
        return "active"
    if memory_type in {"preference", "decision", "command"}:
        return "active"
    return "pending"


def split_tags(tags: Any) -> List[str]:
    if isinstance(tags, list):
        raw_items = tags
    else:
        raw_items = str(tags or "").split(",")
    result: List[str] = []
    for item in raw_items:
        result.extend(part.strip() for part in str(item).split(",") if part.strip())
    return result


def unique(values: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def drop_none(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in entry.items() if value is not None}


def _required_project_root(arguments: Dict[str, Any]) -> str:
    project_root = str(arguments.get("projectRoot") or "").strip()
    if not project_root:
        raise ValueError("projectRoot is required")
    return project_root


def agent_card() -> Dict[str, Any]:
    return {
        "name": "Across Context",
        "version": "0.3.0",
        "description": "Local-first shared memory provider for coding agents.",
        "url": "https://github.com/fantasyce/across-context",
        "capabilities": {
            "memory": True,
            "semanticSearch": True,
            "pendingApproval": True,
            "teamExport": True,
            "localFirst": True,
        },
        "endpoints": {
            "mcp": {"transport": "stdio", "command": "across-context", "args": ["mcp"]},
            "dashboard": {"command": "across-context", "args": ["dashboard"]},
        },
        "memory": {
            "storage": "local-jsonl",
            "types": sorted(MEMORY_TYPES),
            "scopes": sorted(MEMORY_SCOPES),
            "retrievalModes": ["keyword", "semantic", "hybrid"],
            "explanations": True,
        },
    }
