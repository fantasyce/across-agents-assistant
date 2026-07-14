from __future__ import annotations

from dataclasses import dataclass, field
import re
import sys
from typing import Any, Optional


@dataclass(frozen=True)
class ExternalTaskPlanningRequest:
    description: str
    task_types: list[str] = field(default_factory=list)
    owner_agent: Optional[str] = None
    allowed_subtask_agents: list[str] = field(default_factory=list)
    project_dir: Optional[str] = None
    strict_dependency: bool = True
    enable_wave_gate: bool = True


_EXTERNAL_FILE_HINT_EXTENSIONS = {
    "md",
    "json",
    "mjs",
    "js",
    "html",
    "css",
    "txt",
    "yml",
    "yaml",
    "toml",
    "py",
    "ts",
    "tsx",
    "jsx",
}
_NEGATIVE_DELIVERABLE_LINE_RE = re.compile(r"(不允许|不要|禁止|do\s+not|must\s+not|no\s+files?|no\s+cdn|node_modules)", re.IGNORECASE)
_DELIVERABLE_ACTION_RE = re.compile(
    r"(?:创建|生成|输出|交付|新增|写入|create|generate|produce|deliver|write)\s+",
    re.IGNORECASE,
)
_DELIVERABLE_SEGMENT_STOP_RE = re.compile(r"[，,。；;]")
_DELIVERABLE_CLAUSE_SPLIT_RE = re.compile(r"[，,。；;]+|(?<=[.!?])\s+")
_EXTERNAL_FILE_HINT_MAX_LINE_LENGTH = 4096
_HOST_AGENT_RUNTIME_STATE_ROOTS = {
    "kimi": [
        "~/.kimi-code/logs",
        "~/.kimi-code/sessions",
        "~/.kimi-code/telemetry",
        "~/.kimi-code/updates",
        "~/.kimi-code/user-history",
    ],
}
_HOST_AGENT_RUNTIME_STATE_FILES = {
    "kimi": ["~/.kimi-code/session_index.jsonl"],
}


def deliverables_for_external_task(req: ExternalTaskPlanningRequest) -> list[str]:
    if req.strict_dependency:
        wave_deliverables = external_wave_deliverable_hints(req.description)
        if wave_deliverables:
            return wave_deliverables
    deliverables = external_file_hints_from_description(req.description)
    if deliverables:
        return deliverables
    return ["README.md"]


def external_owner_agent(req: ExternalTaskPlanningRequest) -> str:
    owner = _normalize_external_agent_id(req.owner_agent)
    if owner and owner != "auto":
        return owner
    for agent in req.allowed_subtask_agents or []:
        value = _normalize_external_agent_id(agent)
        if value:
            return value
    return "demo"


def external_subtask_agents(req: ExternalTaskPlanningRequest) -> list[str]:
    agents = [
        value
        for agent in req.allowed_subtask_agents or []
        if (value := _normalize_external_agent_id(agent))
    ]
    if not agents:
        owner = external_owner_agent(req)
        agents = [owner] if owner else ["demo"]
    return agents or ["demo"]


def agent_adapters_for_external_task(req: ExternalTaskPlanningRequest) -> dict[str, dict[str, Any]]:
    """Declare AAA host execution adapters for non-demo external task agents."""
    agents: list[str] = []
    owner = external_owner_agent(req)
    if owner:
        agents.append(owner)
    agents.extend(external_subtask_agents(req))

    specs: dict[str, dict[str, Any]] = {}
    for agent in agents:
        agent_id = _normalize_external_agent_id(agent)
        if not agent_id or agent_id == "demo" or agent_id in specs:
            continue
        spec = {
            "type": "command",
            "command": host_agent_adapter_command(agent_id),
            "description": "AAA host-provided agent execution adapter.",
        }
        runtime_state_roots = _HOST_AGENT_RUNTIME_STATE_ROOTS.get(agent_id)
        runtime_state_files = _HOST_AGENT_RUNTIME_STATE_FILES.get(agent_id)
        if runtime_state_roots or runtime_state_files:
            spec["sandboxPolicy"] = {
                "network_policy": "adapter_scoped",
                "execution": {
                    "timeout_seconds": 90,
                    "refresh_timeout_on_output": True,
                    "max_wall_timeout_seconds": 1200,
                },
                "filesystem_policy": {
                    "mode": "run_scoped",
                    "runtime_state_roots": list(runtime_state_roots or []),
                    "runtime_state_files": list(runtime_state_files or []),
                }
            }
        specs[agent_id] = spec
    return specs


def host_agent_adapter_command(agent_id: str) -> list[str]:
    clean_agent_id = _normalize_external_agent_id(agent_id) or str(agent_id or "").strip()
    if getattr(sys, "frozen", False):
        command = [
            sys.executable,
            "orchestrator-agent-adapter",
            "--agent",
            clean_agent_id,
        ]
    else:
        command = [
            sys.executable,
            "-m",
            "across_agents_assistant.orchestrator_agent_adapter",
            "--agent",
            clean_agent_id,
        ]
    if clean_agent_id == "kimi":
        command.extend(["--timeout", "1200"])
    return command


def _normalize_external_agent_id(agent_id: Any) -> str:
    return str(agent_id or "").strip().lower()


def planned_subtasks_for_external_task(req: ExternalTaskPlanningRequest, deliverables: list[str]) -> list[dict[str, Any]]:
    """Build an explicit serial plan for the external generic runtime.

    The generic Across Orchestrator sidecar owns orchestration state and
    evidence. AAA declares host-native agent execution through explicit command
    adapters. This helper preserves user-authored Wave N structure so the UI can
    verify dependency/wave behavior instead of collapsing to a single README.
    """
    if not req.strict_dependency:
        return []

    wave_specs: dict[int, list[tuple[str, str, str]]] = {}
    for line in str(req.description or "").splitlines():
        parsed_wave = parse_external_wave_line(line)
        if parsed_wave is None:
            continue
        wave_number, parsed_title, _body = parsed_wave
        title = parsed_title or f"Wave {wave_number}"
        files = external_deliverable_hints_from_wave_line(line)
        for path in files:
            wave_specs.setdefault(wave_number, []).append((title, line.strip(), path))

    subtask_agents = external_subtask_agents(req)
    subtasks: list[dict[str, Any]] = []
    previous_wave_ids: list[str] = []
    if wave_specs:
        for wave_number, entries in wave_specs.items():
            current_ids: list[str] = []
            for index, (title, source_line, path) in enumerate(entries, start=1):
                spec_id = f"wave-{wave_number}-{index}"
                subtasks.append(
                    {
                        "id": spec_id,
                        "description": f"Wave {wave_number} {title}: produce {path}. Source requirement: {source_line}",
                        "path": path,
                        "agent": subtask_agents[len(subtasks) % len(subtask_agents)],
                        "wave": wave_number,
                        "priority": (wave_number * 100) + index,
                        "dependencies": list(previous_wave_ids),
                    }
                )
                current_ids.append(spec_id)
            previous_wave_ids = current_ids
        return subtasks

    if len(deliverables) <= 1:
        return []

    previous_id: Optional[str] = None
    for index, path in enumerate(deliverables, start=1):
        spec_id = f"stage-{index}"
        subtasks.append(
            {
                "id": spec_id,
                "description": f"Serial stage {index}: produce {path}.",
                "path": path,
                "agent": subtask_agents[(index - 1) % len(subtask_agents)],
                "wave": index,
                "priority": index,
                "dependencies": [previous_id] if previous_id else [],
            }
        )
        previous_id = spec_id
    return subtasks


def normalize_external_artifact_path(path: str) -> Optional[str]:
    value = str(path or "").strip().replace("\\", "/").lstrip("/")
    if not value or "\x00" in value:
        return None
    parts = [part for part in value.split("/") if part and part != "."]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


def external_file_hints_from_line(line: str) -> list[str]:
    if _NEGATIVE_DELIVERABLE_LINE_RE.search(line or ""):
        return []
    hints: list[str] = []
    for token in external_file_hint_tokens(line or ""):
        normalized = normalize_external_artifact_path(token)
        if normalized and normalized not in hints:
            hints.append(normalized)
    return hints


def external_file_hint_tokens(line: str) -> list[str]:
    """Extract file-like tokens with a linear scan to avoid regex backtracking."""
    text = str(line or "")[:_EXTERNAL_FILE_HINT_MAX_LINE_LENGTH]
    tokens: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if not current:
            return
        token = "".join(current).strip("./")
        current.clear()
        if not token or "/" in {token[0], token[-1]}:
            return
        last_segment = token.rsplit("/", 1)[-1]
        if "." not in last_segment:
            return
        extension = last_segment.rsplit(".", 1)[-1].lower()
        if extension in _EXTERNAL_FILE_HINT_EXTENSIONS:
            tokens.append(token)

    for char in text:
        if char.isalnum() or char in {"_", "-", ".", "/"}:
            current.append(char)
        else:
            flush()
    flush()
    return tokens


def external_file_hints_from_description(description: str) -> list[str]:
    hints: list[str] = []
    for line in str(description or "").splitlines():
        # Negative guidance later in a sentence must not erase positive file
        # requirements stated in an earlier clause on the same line.
        for clause in _DELIVERABLE_CLAUSE_SPLIT_RE.split(line):
            for path in external_file_hints_from_line(clause):
                if path not in hints:
                    hints.append(path)
    return hints


def external_deliverable_hints_from_wave_line(line: str) -> list[str]:
    if _NEGATIVE_DELIVERABLE_LINE_RE.search(line or ""):
        return []
    action = _DELIVERABLE_ACTION_RE.search(line or "")
    if not action:
        return []
    segment = str(line or "")[action.end():]
    stop = _DELIVERABLE_SEGMENT_STOP_RE.search(segment)
    if stop:
        segment = segment[: stop.start()]
    return external_file_hints_from_line(segment)


def external_wave_deliverable_hints(description: str) -> list[str]:
    hints: list[str] = []
    for line in str(description or "").splitlines():
        if parse_external_wave_line(line) is None:
            continue
        for path in external_deliverable_hints_from_wave_line(line):
            if path not in hints:
                hints.append(path)
    return hints


def parse_external_wave_line(line: str) -> Optional[tuple[int, str, str]]:
    value = str(line or "").strip()
    if not value[:4].lower() == "wave":
        return None
    index = 4
    length = len(value)
    while index < length and value[index].isspace():
        index += 1
    digit_start = index
    while index < length and value[index].isdigit():
        index += 1
    if index == digit_start:
        return None
    wave_number = int(value[digit_start:index])
    while index < length and value[index].isspace():
        index += 1
    colon_index = -1
    for candidate in (":", "："):
        found = value.find(candidate, index)
        if found >= 0 and (colon_index < 0 or found < colon_index):
            colon_index = found
    if colon_index < 0:
        return None
    title = value[index:colon_index].strip()
    body = value[colon_index + 1 :].strip()
    return wave_number, title, body
