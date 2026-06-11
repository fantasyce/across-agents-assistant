from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .agent_ids import LOCAL_CLI_AGENT_IDS, normalize_agent_id
from .llm_gateway.provider_registry import get_default_provider_definitions, get_default_provider_ids
from .native_agent_skills import is_native_skill_available
from .paths import data_file


CLOUD_AGENT_IDS = get_default_provider_ids()
DEFAULT_AGENT_IDS = (*LOCAL_CLI_AGENT_IDS, *CLOUD_AGENT_IDS)
AGENT_DISPLAY_NAMES: Dict[str, str] = {
    "openclaw": "OpenClaw",
    "hermes": "Hermes",
    "claude": "Claude Code",
    "codex": "Codex",
    "deepseek": "DeepSeek",
    "minimax": "MiniMax",
}
AGENT_DISPLAY_NAMES.update(
    {provider.provider_id: provider.name for provider in get_default_provider_definitions()}
)


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    name: str
    description: str
    prompt_hint: str
    tags: List[str] = field(default_factory=list)
    source: str = "built_in"


@dataclass
class AgentCapabilityProfile:
    agent_id: str
    enabled_skill_ids: List[str] = field(default_factory=list)
    enabled_plugin_ids: List[str] = field(default_factory=list)
    enabled_tool_names: List[str] = field(default_factory=list)
    custom_instructions: str = ""
    strict_tool_scope: bool = False


SKILL_CATALOG: List[SkillDefinition] = [
    SkillDefinition(
        id="general_execution",
        name="General execution",
        description="Handle broad implementation work, file changes, and command-line operations.",
        prompt_hint="Act as a general implementation agent, keep changes scoped, and report concrete files changed.",
        tags=["implementation", "local"],
    ),
    SkillDefinition(
        id="macos_automation",
        name="macOS automation",
        description="Operate local macOS context such as Finder, Xcode, browser URLs, notes, and screenshots.",
        prompt_hint="Use macOS context carefully and prefer reversible local actions when interacting with apps.",
        tags=["macos", "local-tools"],
    ),
    SkillDefinition(
        id="frontend_design",
        name="Frontend product design",
        description="Design and implement polished interfaces that match the product visual language.",
        prompt_hint="Match the existing UI system, keep controls compact, verify layout states, and avoid decorative clutter.",
        tags=["frontend", "design"],
    ),
    SkillDefinition(
        id="interaction_design",
        name="Interaction design",
        description="Improve workflow ergonomics, keyboard paths, empty states, loading states, and user feedback.",
        prompt_hint="Design complete interaction states and verify that the user can finish the workflow efficiently.",
        tags=["ux", "frontend"],
    ),
    SkillDefinition(
        id="backend_api",
        name="Backend API implementation",
        description="Build service APIs, validation, persistence, and integration logic.",
        prompt_hint="Prefer explicit schemas, deterministic validation, clear error paths, and tests around API behavior.",
        tags=["backend", "api"],
    ),
    SkillDefinition(
        id="data_modeling",
        name="Data modeling",
        description="Model durable data, migrations, indexing, and consistency constraints.",
        prompt_hint="Keep schemas normalized enough for the workflow, add indexes when reads depend on them, and preserve migrations.",
        tags=["database", "backend"],
    ),
    SkillDefinition(
        id="architecture_review",
        name="Architecture review",
        description="Plan cross-module boundaries, contracts, and technical tradeoffs.",
        prompt_hint="Call out ownership boundaries, contracts, and sequencing before changing shared behavior.",
        tags=["architecture", "review"],
    ),
    SkillDefinition(
        id="code_review",
        name="Code review",
        description="Review changes for correctness, regressions, edge cases, and maintainability.",
        prompt_hint="Prioritize concrete bugs, risky behavior, missing tests, and compatibility issues.",
        tags=["review", "quality"],
    ),
    SkillDefinition(
        id="test_strategy",
        name="Test strategy",
        description="Design focused automated verification for user-facing behavior and cross-module contracts.",
        prompt_hint="Add tests proportional to risk and include at least one end-to-end or integration check for critical workflows.",
        tags=["testing", "quality"],
    ),
    SkillDefinition(
        id="test_authoring",
        name="Test authoring",
        description="Write automated tests, fixtures, and deterministic checks for the implemented surface.",
        prompt_hint="Write tests that run locally without hidden services and make failures actionable.",
        tags=["testing", "implementation"],
    ),
    SkillDefinition(
        id="devops_release",
        name="DevOps and release",
        description="Prepare packaging, CI, deployment, signing, and operational readiness work.",
        prompt_hint="Keep release steps reproducible, avoid embedding secrets, and document required external credentials.",
        tags=["devops", "release"],
    ),
    SkillDefinition(
        id="integration_smoke",
        name="Integration smoke checks",
        description="Verify that separately implemented pieces work together through realistic flows.",
        prompt_hint="Run the smallest meaningful full-flow check and report exact commands, logs, and blockers.",
        tags=["integration", "quality"],
    ),
]


DEFAULT_SKILLS_BY_AGENT: Dict[str, List[str]] = {
    "openclaw": ["general_execution", "macos_automation", "test_authoring"],
    "hermes": ["frontend_design", "interaction_design", "test_authoring"],
    "claude": ["architecture_review", "code_review", "test_strategy"],
    "codex": ["general_execution", "code_review", "test_authoring"],
    "deepseek": ["backend_api", "data_modeling", "code_review"],
    "minimax": ["devops_release", "integration_smoke", "test_strategy"],
}
for _provider_id in CLOUD_AGENT_IDS:
    DEFAULT_SKILLS_BY_AGENT.setdefault(_provider_id, ["backend_api", "code_review"])

DEFAULT_PLUGINS_BY_AGENT: Dict[str, List[str]] = {
    agent_id: ["across_context"]
    for agent_id in DEFAULT_AGENT_IDS
}


def skill_catalog() -> List[Dict[str, Any]]:
    return [asdict(skill) for skill in SKILL_CATALOG]


CUSTOM_SKILL_ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,64}$")


KEYWORD_SKILL_HINTS: Dict[str, List[str]] = {
    "frontend": ["frontend_design", "interaction_design"],
    "front-end": ["frontend_design", "interaction_design"],
    "web": ["frontend_design", "interaction_design"],
    "webapp": ["frontend_design", "interaction_design"],
    "html": ["frontend_design", "interaction_design"],
    "css": ["frontend_design", "interaction_design"],
    "javascript": ["frontend_design", "interaction_design"],
    "canvas": ["frontend_design", "interaction_design"],
    "static": ["frontend_design"],
    "ui": ["frontend_design", "interaction_design"],
    "ux": ["interaction_design"],
    "react": ["frontend_design", "interaction_design"],
    "vue": ["frontend_design", "interaction_design"],
    "dashboard": ["frontend_design", "data_modeling"],
    "backend": ["backend_api", "data_modeling"],
    "api": ["backend_api"],
    "server": ["backend_api"],
    "database": ["data_modeling"],
    "sqlite": ["data_modeling"],
    "schema": ["data_modeling"],
    "architecture": ["architecture_review"],
    "review": ["code_review", "architecture_review"],
    "test": ["test_strategy", "test_authoring"],
    "tests": ["test_strategy", "test_authoring"],
    "testing": ["test_strategy", "test_authoring"],
    "e2e": ["test_strategy", "test_authoring", "integration_smoke"],
    "integration": ["integration_smoke"],
    "release": ["devops_release", "integration_smoke"],
    "package": ["devops_release"],
    "packaging": ["devops_release"],
    "dmg": ["devops_release"],
    "signing": ["devops_release"],
    "macos": ["macos_automation"],
    "screenshot": ["macos_automation"],
    "automation": ["macos_automation"],
}

PREFLIGHT_STOPWORDS = {
    "a",
    "an",
    "and",
    "the",
    "to",
    "for",
    "with",
    "without",
    "in",
    "on",
    "of",
    "by",
    "from",
    "task",
    "functional",
    "artifact",
    "build",
    "create",
    "make",
    "add",
    "update",
    "fix",
    "improve",
    "polished",
}

NATIVE_SKILL_STOPWORDS = PREFLIGHT_STOPWORDS | {
    "agent",
    "agents",
    "apple",
    "app",
    "apps",
    "across",
    "availability",
    "available",
    "button",
    "buttons",
    "canvas",
    "card",
    "cards",
    "check",
    "checks",
    "configured",
    "data",
    "dependency",
    "dependencies",
    "direct",
    "directly",
    "evidence",
    "external",
    "file",
    "files",
    "final",
    "gate",
    "gates",
    "generated",
    "local",
    "manual",
    "matched",
    "mock",
    "mode",
    "modes",
    "native",
    "package",
    "packages",
    "panel",
    "quality",
    "reason",
    "repair",
    "report",
    "reports",
    "required",
    "risk",
    "route",
    "routing",
    "score",
    "selected",
    "server",
    "skill",
    "skills",
    "skipped",
    "task",
    "text",
    "tool",
    "tools",
    "unavailable",
    "verdict",
    "visible",
    "web",
    "openclaw",
    "hermes",
    "claude",
    "deepseek",
    "minimax",
}


def _built_in_skill_ids() -> set[str]:
    return {skill.id for skill in SKILL_CATALOG}


def _known_skill_ids(custom_skills: Optional[Iterable[SkillDefinition]] = None) -> set[str]:
    known = _built_in_skill_ids()
    for skill in custom_skills or []:
        known.add(skill.id)
    return known


def _dedupe_strings(values: Optional[Iterable[Any]]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for value in values or []:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _normalize_profile(
    data: Dict[str, Any],
    fallback_agent_id: str,
    known_skill_ids: Optional[set[str]] = None,
) -> AgentCapabilityProfile:
    agent_id = normalize_agent_id(data.get("agent_id") or fallback_agent_id) or fallback_agent_id
    known = known_skill_ids or _known_skill_ids()
    skill_ids = [sid for sid in _dedupe_strings(data.get("enabled_skill_ids")) if sid in known]
    return AgentCapabilityProfile(
        agent_id=agent_id,
        enabled_skill_ids=skill_ids,
        enabled_plugin_ids=_dedupe_strings(data.get("enabled_plugin_ids")),
        enabled_tool_names=_dedupe_strings(data.get("enabled_tool_names")),
        custom_instructions=str(data.get("custom_instructions") or "").strip(),
        strict_tool_scope=bool(data.get("strict_tool_scope", False)),
    )


def _default_profile(agent_id: str) -> AgentCapabilityProfile:
    normalized = normalize_agent_id(agent_id) or agent_id
    return AgentCapabilityProfile(
        agent_id=normalized,
        enabled_skill_ids=list(DEFAULT_SKILLS_BY_AGENT.get(normalized, [])),
        enabled_plugin_ids=list(DEFAULT_PLUGINS_BY_AGENT.get(normalized, [])),
    )


def _slugify_skill_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    if not slug:
        slug = "skill"
    if not slug.startswith("custom_"):
        slug = f"custom_{slug}"
    return slug[:64].rstrip("_")


def _skill_tokens(skill: SkillDefinition) -> set[str]:
    text = " ".join(
        [
            skill.id.replace("_", " "),
            skill.name,
            skill.description,
            skill.prompt_hint,
            " ".join(skill.tags),
        ]
    ).lower()
    return {token for token in re.split(r"[^a-z0-9]+", text) if token}


def _request_tokens(description: str, task_types: Optional[Iterable[str]] = None) -> set[str]:
    text = " ".join([description or "", " ".join(task_types or [])]).lower()
    return {
        token
        for token in re.split(r"[^a-z0-9]+", text)
        if token and token not in PREFLIGHT_STOPWORDS
    }


def _meaningful_native_tokens(tokens: Iterable[str]) -> set[str]:
    return {
        token
        for token in tokens
        if len(token) >= 3 and token not in NATIVE_SKILL_STOPWORDS
    }


def _native_skill_tokens(skill: Dict[str, Any]) -> set[str]:
    text = " ".join(
        [
            str(skill.get("id") or "").replace("-", " ").replace("_", " "),
            str(skill.get("name") or ""),
            str(skill.get("description") or ""),
        ]
    ).lower()
    return _meaningful_native_tokens(
        token for token in re.split(r"[^a-z0-9]+", text) if token
    )


def _native_skill_name_tokens(skill: Dict[str, Any]) -> set[str]:
    text = " ".join(
        [
            str(skill.get("id") or "").replace("-", " ").replace("_", " "),
            str(skill.get("name") or ""),
        ]
    ).lower()
    return _meaningful_native_tokens(
        token for token in re.split(r"[^a-z0-9]+", text) if token
    )


def _native_skill_name_phrases(skill: Dict[str, Any]) -> List[str]:
    phrases: List[str] = []
    for value in [skill.get("name"), skill.get("id")]:
        text = str(value or "").replace("-", " ").replace("_", " ").strip().lower()
        tokens = [
            token
            for token in re.split(r"[^a-z0-9]+", text)
            if token and token not in NATIVE_SKILL_STOPWORDS
        ]
        if len(tokens) >= 2:
            phrases.append(r"\s+".join(re.escape(token) for token in tokens))
        elif tokens and len(tokens[0]) >= 5:
            phrases.append(re.escape(tokens[0]))
    return _dedupe_strings(phrases)


def _native_skill_has_negative_context(skill: Dict[str, Any], description: str) -> bool:
    text = re.sub(r"\s+", " ", (description or "").lower())
    negative = r"(?:mock|simulated|simulation|fake|demo\s+only|must\s+not|do\s+not|don't|never|without|no\s+real)"
    for phrase in _native_skill_name_phrases(skill):
        if re.search(rf"{negative}[^.?!]{{0,160}}{phrase}", text):
            return True
        if re.search(rf"{phrase}[^.?!]{{0,160}}{negative}", text):
            return True
    return False


def _native_skill_matches_request(
    skill: Dict[str, Any],
    request_tokens: set[str],
    description: str = "",
) -> bool:
    if _native_skill_has_negative_context(skill, description):
        return False
    meaningful_request = _meaningful_native_tokens(request_tokens)
    if not meaningful_request:
        return False
    name_overlap = meaningful_request.intersection(_native_skill_name_tokens(skill))
    if len(name_overlap) >= 2:
        return True
    if any(len(token) >= 5 for token in name_overlap):
        return True
    # Native skills should be strong routing signals only when the task names
    # the skill itself. Description-only overlap is too noisy for skills whose
    # descriptions contain broad words such as page, browser, review, or agent.
    return False


def _native_skill_id(skill: Dict[str, Any]) -> str:
    return str(skill.get("id") or skill.get("name") or "").strip()


def _normalize_risk_level(value: Any) -> str:
    risk = str(value or "unknown").strip().lower()
    return risk if risk in {"low", "medium", "high"} else "unknown"


class AgentCapabilityStore:
    def __init__(self, path: Optional[Path | str] = None) -> None:
        self.path = Path(path) if path is not None else data_file("agent-capabilities.json")

    def _read_raw_payload(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return raw if isinstance(raw, dict) else {}

    def _read_payload(self) -> tuple[Dict[str, Dict[str, Any]], List[SkillDefinition]]:
        raw = self._read_raw_payload()
        if isinstance(raw, dict) and isinstance(raw.get("profiles"), dict):
            raw_profiles = raw.get("profiles") or {}
            raw_custom_skills = raw.get("custom_skills") or []
        elif isinstance(raw, dict):
            raw_profiles = raw
            raw_custom_skills = []
        else:
            raw_profiles = {}
            raw_custom_skills = []
        saved: Dict[str, Dict[str, Any]] = {}
        for key, value in raw_profiles.items():
            if isinstance(value, dict):
                normalized = normalize_agent_id(value.get("agent_id") or key) or str(key)
                saved[normalized] = value

        custom_skills: List[SkillDefinition] = []
        for value in raw_custom_skills:
            if not isinstance(value, dict):
                continue
            try:
                custom_skills.append(self._normalize_custom_skill(value))
            except ValueError:
                continue
        return saved, custom_skills

    def _write_payload(
        self,
        profiles: Dict[str, AgentCapabilityProfile],
        custom_skills: List[SkillDefinition],
        native_skill_states: Optional[Dict[str, Dict[str, Any]]] = None,
        native_skill_cache_updated_at: Optional[float] = None,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if native_skill_states is None:
            native_skill_states, native_skill_cache_updated_at = self.get_native_skill_snapshot()
        payload = {
            "version": 3,
            "custom_skills": [asdict(skill) for skill in sorted(custom_skills, key=lambda item: item.id)],
            "profiles": {
                agent_id: asdict(profile)
                for agent_id, profile in sorted(profiles.items())
            },
        }
        if native_skill_states:
            payload["native_skill_states"] = native_skill_states
            payload["native_skill_cache_updated_at"] = native_skill_cache_updated_at or time.time()
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _write_profiles(self, profiles: Dict[str, AgentCapabilityProfile]) -> None:
        _, custom_skills = self._read_payload()
        self._write_payload(profiles, custom_skills)

    def _normalize_custom_skill(self, data: Dict[str, Any], skill_id: Optional[str] = None) -> SkillDefinition:
        raw_name = str(data.get("name") or "").strip()
        raw_id = str(skill_id or data.get("id") or _slugify_skill_id(raw_name)).strip()
        normalized_id = _slugify_skill_id(raw_id)
        if normalized_id in _built_in_skill_ids():
            raise ValueError(f"Cannot override built-in skill: {normalized_id}")
        if not CUSTOM_SKILL_ID_RE.match(normalized_id):
            raise ValueError("Custom skill id must contain only lowercase letters, numbers, and underscores.")
        if not raw_name:
            raise ValueError("Custom skill name is required.")
        description = str(data.get("description") or "").strip()
        prompt_hint = str(data.get("prompt_hint") or data.get("promptHint") or "").strip()
        if not description:
            raise ValueError("Custom skill description is required.")
        if not prompt_hint:
            raise ValueError("Custom skill prompt hint is required.")
        return SkillDefinition(
            id=normalized_id,
            name=raw_name,
            description=description,
            prompt_hint=prompt_hint,
            tags=_dedupe_strings(data.get("tags")),
            source="custom",
        )

    def _custom_skills(self) -> List[SkillDefinition]:
        _, custom_skills = self._read_payload()
        return custom_skills

    def skill_definitions(self) -> List[SkillDefinition]:
        return [*SKILL_CATALOG, *self._custom_skills()]

    def skill_catalog(self) -> List[Dict[str, Any]]:
        return [asdict(skill) for skill in self.skill_definitions()]

    def save_custom_skill(self, data: Dict[str, Any], skill_id: Optional[str] = None) -> Dict[str, Any]:
        profiles, custom_skills = self._read_payload()
        skill = self._normalize_custom_skill(data, skill_id=skill_id)
        remaining = [item for item in custom_skills if item.id != skill.id]
        remaining.append(skill)
        known = _known_skill_ids(remaining)
        normalized_profiles = {
            aid: _normalize_profile(value, aid, known)
            for aid, value in profiles.items()
        }
        self._write_payload(normalized_profiles, remaining)
        return asdict(skill)

    def delete_custom_skill(self, skill_id: str) -> bool:
        profiles, custom_skills = self._read_payload()
        normalized_id = _slugify_skill_id(skill_id)
        remaining = [item for item in custom_skills if item.id != normalized_id]
        if len(remaining) == len(custom_skills):
            return False
        known = _known_skill_ids(remaining)
        normalized_profiles: Dict[str, AgentCapabilityProfile] = {}
        for aid, value in profiles.items():
            profile = _normalize_profile(value, aid, known | {normalized_id})
            profile.enabled_skill_ids = [
                item for item in profile.enabled_skill_ids if item != normalized_id
            ]
            normalized_profiles[aid] = _normalize_profile(asdict(profile), aid, known)
        self._write_payload(normalized_profiles, remaining)
        return True

    def get_profiles(self) -> Dict[str, Dict[str, Any]]:
        saved, custom_skills = self._read_payload()
        known = _known_skill_ids(custom_skills)
        profiles: Dict[str, AgentCapabilityProfile] = {}
        for agent_id in DEFAULT_AGENT_IDS:
            normalized = normalize_agent_id(agent_id) or agent_id
            profile_data = saved.get(normalized)
            profiles[normalized] = (
                _normalize_profile(profile_data, normalized, known)
                if profile_data
                else _default_profile(normalized)
            )
        for agent_id, profile_data in saved.items():
            if agent_id not in profiles:
                profiles[agent_id] = _normalize_profile(profile_data, agent_id, known)
        return {agent_id: asdict(profile) for agent_id, profile in profiles.items()}

    def get_profile(self, agent_id: str) -> Dict[str, Any]:
        normalized = normalize_agent_id(agent_id) or agent_id
        profiles = self.get_profiles()
        return profiles.get(normalized) or asdict(_default_profile(normalized))

    def save_profile(self, agent_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        normalized = normalize_agent_id(agent_id) or agent_id
        current = self.get_profiles()
        base = current.get(normalized) or asdict(_default_profile(normalized))
        merged = dict(base)
        merged["agent_id"] = normalized
        for key in (
            "enabled_skill_ids",
            "enabled_plugin_ids",
            "enabled_tool_names",
            "custom_instructions",
            "strict_tool_scope",
        ):
            if key in updates:
                merged[key] = updates[key]
        custom_skills = self._custom_skills()
        known = _known_skill_ids(custom_skills)
        profile = _normalize_profile(merged, normalized, known)
        current_profiles = {
            aid: _normalize_profile(value, aid, known)
            for aid, value in current.items()
        }
        current_profiles[normalized] = profile
        self._write_payload(current_profiles, custom_skills)
        return asdict(profile)

    def get_native_skill_snapshot(self) -> tuple[Dict[str, Dict[str, Any]], Optional[float]]:
        raw = self._read_raw_payload()
        raw_states = raw.get("native_skill_states") if isinstance(raw, dict) else {}
        if not isinstance(raw_states, dict):
            return {}, None
        states: Dict[str, Dict[str, Any]] = {}
        for key, value in raw_states.items():
            if not isinstance(value, dict):
                continue
            normalized = normalize_agent_id(value.get("agent_id") or key) or str(key)
            item = dict(value)
            item["agent_id"] = normalized
            states[normalized] = item
        updated_at = raw.get("native_skill_cache_updated_at")
        try:
            timestamp = float(updated_at) if updated_at is not None else None
        except (TypeError, ValueError):
            timestamp = None
        return states, timestamp

    def get_native_skill_states(self) -> Dict[str, Dict[str, Any]]:
        states, _ = self.get_native_skill_snapshot()
        return states

    def save_native_skill_states(self, states: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        saved, custom_skills = self._read_payload()
        known = _known_skill_ids(custom_skills)
        normalized_profiles = {
            aid: _normalize_profile(value, aid, known)
            for aid, value in saved.items()
        }
        normalized_states: Dict[str, Dict[str, Any]] = {}
        for key, value in (states or {}).items():
            if not isinstance(value, dict):
                continue
            normalized = normalize_agent_id(value.get("agent_id") or key) or str(key)
            item = dict(value)
            item["agent_id"] = normalized
            normalized_states[normalized] = item
        self._write_payload(
            normalized_profiles,
            custom_skills,
            native_skill_states=normalized_states,
            native_skill_cache_updated_at=time.time(),
        )
        return normalized_states

    def build_task_context(self, agent_ids: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        requested = _dedupe_strings(agent_ids)
        if not requested:
            requested = list(DEFAULT_AGENT_IDS)
        normalized_ids = _dedupe_strings(normalize_agent_id(agent_id) or agent_id for agent_id in requested)
        all_profiles = self.get_profiles()
        selected_profiles = {
            agent_id: all_profiles.get(agent_id) or asdict(_default_profile(agent_id))
            for agent_id in normalized_ids
        }
        skills = self.skill_definitions()
        skills_by_id = {skill.id: skill for skill in skills}
        lines: List[str] = []
        for agent_id, profile in selected_profiles.items():
            skill_names = [
                skills_by_id[skill_id].name
                for skill_id in profile.get("enabled_skill_ids", [])
                if skill_id in skills_by_id
            ]
            skill_hints = [
                skills_by_id[skill_id].prompt_hint
                for skill_id in profile.get("enabled_skill_ids", [])
                if skill_id in skills_by_id and skills_by_id[skill_id].prompt_hint
            ]
            parts = [
                f"skills={', '.join(skill_names) if skill_names else 'default platform behavior'}",
            ]
            if skill_hints:
                parts.append(f"skill_guidance={' | '.join(skill_hints)}")
            plugins = profile.get("enabled_plugin_ids", [])
            tools = profile.get("enabled_tool_names", [])
            if plugins:
                parts.append(f"plugins={', '.join(plugins)}")
            if tools:
                parts.append(f"tools={', '.join(tools)}")
            if profile.get("custom_instructions"):
                parts.append(f"instructions={profile['custom_instructions']}")
            if profile.get("strict_tool_scope"):
                parts.append("Strict scope: only route tasks that can be completed with the listed plugins/tools unless escalation is required.")
            lines.append(f"- {agent_id}: " + "; ".join(parts))
        return {
            "skills": [asdict(skill) for skill in skills],
            "profiles": selected_profiles,
            "prompt": "\n".join(lines),
        }

    def build_agent_cards(
        self,
        tool_schemas: Optional[List[Dict[str, Any]]] = None,
        native_skills_by_agent: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> List[Dict[str, Any]]:
        profiles = self.get_profiles()
        skills_by_id = {skill.id: skill for skill in self.skill_definitions()}
        tools_by_name = {
            str(schema.get("name")): schema
            for schema in tool_schemas or []
            if isinstance(schema, dict) and schema.get("name")
        }
        native_skills_by_agent = native_skills_by_agent or {}
        cards: List[Dict[str, Any]] = []
        for agent_id in DEFAULT_AGENT_IDS:
            profile = profiles.get(agent_id) or asdict(_default_profile(agent_id))
            native_skills = native_skills_by_agent.get(agent_id) or []
            available_native = [
                skill for skill in native_skills
                if isinstance(skill, dict) and is_native_skill_available(skill)
            ]
            unavailable_native = [
                skill for skill in native_skills
                if isinstance(skill, dict) and not is_native_skill_available(skill)
            ]
            risk_summary = {"high": 0, "low": 0, "medium": 0, "unknown": 0}
            enabled_tools = _dedupe_strings(profile.get("enabled_tool_names"))
            for tool_name in enabled_tools:
                risk = _normalize_risk_level(tools_by_name.get(tool_name, {}).get("risk_level"))
                risk_summary[risk] += 1

            warnings: List[str] = []
            if risk_summary["high"]:
                warnings.append("High-risk tools require explicit approval.")
            if unavailable_native:
                warnings.append("Unavailable native skills need repair before routing.")
            if profile.get("strict_tool_scope") and not (
                profile.get("enabled_plugin_ids") or profile.get("enabled_tool_names")
            ):
                warnings.append("Strict scope is enabled without selected plugins or tools.")

            cards.append(
                {
                    "agent_id": agent_id,
                    "display_name": AGENT_DISPLAY_NAMES.get(agent_id, agent_id),
                    "agent_type": "cloud" if agent_id in CLOUD_AGENT_IDS else "local",
                    "configured_skill_ids": _dedupe_strings(profile.get("enabled_skill_ids")),
                    "configured_skill_names": [
                        skills_by_id[skill_id].name
                        for skill_id in _dedupe_strings(profile.get("enabled_skill_ids"))
                        if skill_id in skills_by_id
                    ],
                    "enabled_plugin_ids": _dedupe_strings(profile.get("enabled_plugin_ids")),
                    "enabled_tool_names": enabled_tools,
                    "strict_tool_scope": bool(profile.get("strict_tool_scope", False)),
                    "native_skill_health": {
                        "available": len(available_native),
                        "unavailable": len(unavailable_native),
                        "total": len([skill for skill in native_skills if isinstance(skill, dict)]),
                    },
                    "tool_risk_summary": risk_summary,
                    "warnings": warnings,
                }
            )
        return cards

    def build_task_preflight(
        self,
        description: str,
        owner_agent: Optional[str] = None,
        allowed_subtask_agents: Optional[Iterable[str]] = None,
        task_types: Optional[Iterable[str]] = None,
        native_skills_by_agent: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> Dict[str, Any]:
        selected_agent_ids: List[str] = []
        normalized_owner = normalize_agent_id(owner_agent) if owner_agent else None
        if normalized_owner and normalized_owner != "auto":
            selected_agent_ids.append(normalized_owner)
        for agent_id in allowed_subtask_agents or []:
            normalized = normalize_agent_id(agent_id) or agent_id
            if normalized != "auto":
                selected_agent_ids.append(normalized)
        if not selected_agent_ids:
            selected_agent_ids = list(DEFAULT_AGENT_IDS)
        selected_agent_ids = _dedupe_strings(selected_agent_ids)

        profiles = self.get_profiles()
        skills = self.skill_definitions()
        skills_by_id = {skill.id: skill for skill in skills}
        tokens = _request_tokens(description, task_types)
        hinted_skill_ids: set[str] = set()
        for token in tokens:
            hinted_skill_ids.update(KEYWORD_SKILL_HINTS.get(token, []))

        summaries: List[Dict[str, Any]] = []
        warnings: List[str] = []
        native_skills_by_agent = native_skills_by_agent or {}
        for agent_id in selected_agent_ids:
            profile = profiles.get(agent_id) or asdict(_default_profile(agent_id))
            enabled_skill_ids = list(profile.get("enabled_skill_ids", []))
            matched_skill_ids: List[str] = []
            matched_native_skill_ids: List[str] = []
            unavailable_native_skill_ids: List[str] = []
            native_skill_repair_suggestions: List[str] = []
            routing_evidence: List[Dict[str, Any]] = []
            score = 0
            for skill_id in enabled_skill_ids:
                skill = skills_by_id.get(skill_id)
                if not skill:
                    continue
                hinted = skill_id in hinted_skill_ids
                text_matched = bool(tokens.intersection(_skill_tokens(skill)))
                if hinted or text_matched:
                    matched_skill_ids.append(skill_id)
                    score += (3 if hinted else 0) + (1 if text_matched else 0)
                    routing_evidence.append({
                        "source": "platform_skill",
                        "status": "matched",
                        "skill_id": skill_id,
                        "skill_name": skill.name,
                        "reason": "keyword_hint" if hinted else "text_overlap",
                    })
            matched_skill_ids = _dedupe_strings(matched_skill_ids)
            for native_skill in (
                native_skills_by_agent.get(agent_id)
                or native_skills_by_agent.get(normalize_agent_id(agent_id) or agent_id)
                or []
            ):
                if not isinstance(native_skill, dict):
                    continue
                skill_id = _native_skill_id(native_skill)
                if not skill_id:
                    continue
                if not _native_skill_matches_request(native_skill, tokens, description):
                    continue
                if is_native_skill_available(native_skill):
                    matched_native_skill_ids.append(skill_id)
                    score += 4
                    routing_evidence.append({
                        "source": "native_skill",
                        "status": "available",
                        "skill_id": skill_id,
                        "skill_name": str(native_skill.get("name") or skill_id),
                        "reason": "native_skill_name_match",
                    })
                    continue
                unavailable_native_skill_ids.append(skill_id)
                routing_evidence.append({
                    "source": "native_skill",
                    "status": "unavailable",
                    "skill_id": skill_id,
                    "skill_name": str(native_skill.get("name") or skill_id),
                    "reason": str(native_skill.get("unavailable_reason") or "missing requirements"),
                    "repair_suggestions": [
                        str(suggestion)
                        for suggestion in native_skill.get("repair_suggestions") or []
                    ],
                })
                for suggestion in native_skill.get("repair_suggestions") or []:
                    native_skill_repair_suggestions.append(str(suggestion))
            configured_count = (
                len(enabled_skill_ids)
                + len(profile.get("enabled_plugin_ids", []))
                + len(profile.get("enabled_tool_names", []))
                + len(matched_native_skill_ids)
                + (1 if str(profile.get("custom_instructions") or "").strip() else 0)
            )
            profile_warnings: List[str] = []
            if profile.get("strict_tool_scope") and not (
                profile.get("enabled_plugin_ids") or profile.get("enabled_tool_names")
            ):
                profile_warnings.append("Strict scope is enabled without selected plugins or tools.")
            for native_skill in (
                native_skills_by_agent.get(agent_id)
                or native_skills_by_agent.get(normalize_agent_id(agent_id) or agent_id)
                or []
            ):
                skill_id = _native_skill_id(native_skill) if isinstance(native_skill, dict) else ""
                if skill_id not in unavailable_native_skill_ids:
                    continue
                name = str(native_skill.get("name") or skill_id)
                reason = str(native_skill.get("unavailable_reason") or "missing requirements")
                warning = f"{agent_id} native skill {name} is unavailable: {reason}."
                profile_warnings.append(warning)
                warnings.append(warning)
            summaries.append(
                {
                    "agent_id": agent_id,
                    "score": score,
                    "matched_skill_ids": matched_skill_ids,
                    "matched_native_skill_ids": _dedupe_strings(matched_native_skill_ids),
                    "unavailable_native_skill_ids": _dedupe_strings(unavailable_native_skill_ids),
                    "native_skill_repair_suggestions": _dedupe_strings(native_skill_repair_suggestions),
                    "routing_evidence": routing_evidence,
                    "configured_count": configured_count,
                    "warnings": profile_warnings,
                }
            )

        summaries.sort(key=lambda item: (-int(item["score"]), item["agent_id"]))
        recommended = [item["agent_id"] for item in summaries if int(item["score"]) > 0]
        if not recommended and selected_agent_ids:
            recommended = selected_agent_ids[:1]
            warnings.append("No selected agent has a strong skill match for this task description.")
        if not summaries:
            warnings.append("No agent profiles are available for preflight.")

        context = self.build_task_context(selected_agent_ids)
        return {
            "selected_agent_ids": selected_agent_ids,
            "recommended_agent_ids": recommended,
            "agent_summaries": summaries,
            "warnings": _dedupe_strings(warnings),
            "prompt_preview": context["prompt"],
        }


def get_agent_capability_store() -> AgentCapabilityStore:
    return AgentCapabilityStore()
