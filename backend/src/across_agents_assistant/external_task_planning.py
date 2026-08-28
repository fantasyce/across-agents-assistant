from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import sys
from typing import Any, Optional

from .llm_gateway.provider_registry import get_default_provider_ids


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
    r"(?:创建|生成|输出|交付|新增|写入|更新|修改|修复|实现|"
    r"create|generate|produce|deliver|write|update|modify|edit|fix|build|implement|add)\s+",
    re.IGNORECASE,
)
_REFERENCE_INPUT_CLAUSE_RE = re.compile(
    r"(?:现有|已有|当前|读取|引用|摘录|检查|参考)|"
    r"\b(?:existing|current|read|quote|inspect|reference|referenced|from)\b",
    re.IGNORECASE,
)
_DELIVERABLE_SEGMENT_STOP_RE = re.compile(r"[，,。；;]")
_DELIVERABLE_CLAUSE_SPLIT_RE = re.compile(r"[，,。；;]+|(?<=[.!?])\s+")
_READ_ONLY_TASK_RE = re.compile(
    r"(?:只读|不要修改(?:任何)?文件|不得修改(?:任何)?文件|"
    r"禁止修改(?:任何)?文件|不改动(?:任何)?文件|"
    r"\bread[\s-]?only\b|\bdo\s+not\s+(?:modify|edit|write|change)\s+(?:any\s+)?files?\b|"
    r"\bwithout\s+(?:modifying|editing|writing|changing)\s+(?:any\s+)?files?\b|"
    r"\bno\s+(?:file\s+)?(?:changes|writes)\b)",
    re.IGNORECASE,
)
_REMOTE_WORKER_REFERENCE_RE = re.compile(
    r"(?:远端|远程|另一台|其他(?:电脑|机器|服务器)).{0,20}(?:worker|工作节点|节点)|"
    r"(?:worker|工作节点|节点).{0,20}(?:远端|远程|另一台|其他(?:电脑|机器|服务器))|"
    r"\bremote\s+worker\b|\bworker\s+node\b",
    re.IGNORECASE,
)
_REMOTE_WORKER_POSITIVE_RE = re.compile(
    r"(?:请|使用|通过|交由|让|必须|需要|要求|委派|派发).{0,32}"
    r"(?:(?:远端|远程|另一台|其他(?:电脑|机器|服务器)).{0,20}(?:worker|工作节点|节点)|"
    r"(?:worker|工作节点|节点).{0,20}(?:远端|远程|另一台|其他(?:电脑|机器|服务器)))|"
    r"(?:(?:远端|远程).{0,12}(?:worker|工作节点)|(?:worker|工作节点).{0,12}(?:远端|远程))"
    r".{0,24}(?:执行|完成|运行|处理|分析)|"
    r"\b(?:use|via|through|dispatch(?:ed)?\s+to|run\s+on|execute\s+on|must\s+use|require)\b"
    r".{0,32}\b(?:remote\s+worker|worker\s+node)\b",
    re.IGNORECASE,
)
_REMOTE_WORKER_NEGATIVE_RE = re.compile(
    r"(?:不要|不得|禁止|无需|不需要|不必).{0,40}"
    r"(?:(?:远端|远程).{0,16}(?:worker|工作节点|节点)|(?:worker|工作节点|节点).{0,16}(?:远端|远程))|"
    r"\b(?:do\s+not|don't|must\s+not|without)\b.{0,40}\b(?:remote\s+worker|worker\s+node)\b",
    re.IGNORECASE,
)
_REMOTE_WORKER_CLAUSE_SPLIT_RE = re.compile(r"[。！？；;\n]+|(?<=[.!?])\s+")
_EXTERNAL_FILE_HINT_MAX_LINE_LENGTH = 4096
_HOST_AGENT_RUNTIME_STATE_ROOTS = {
    "codex": ["~/.codex"],
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
_CLOUD_PROVIDER_IDS = set(get_default_provider_ids())


def deliverables_for_external_task(req: ExternalTaskPlanningRequest) -> list[str]:
    if is_read_only_external_task(req):
        # Mentioned project files are inspection inputs, never outputs.  The
        # adapter result is preserved by Orchestrator as a managed report
        # outside the inspected project tree.
        return ["across-results/task-review.md"]
    if req.strict_dependency:
        wave_deliverables = external_wave_deliverable_hints(req.description)
        if wave_deliverables:
            return wave_deliverables
    deliverables = external_file_hints_from_description(req.description)
    if deliverables:
        return deliverables
    # A repository README is product source, not a generic task receipt.  When
    # the user did not name a concrete output, ask the runtime for a scoped
    # report so an unrelated pre-existing README can never satisfy the task.
    return ["across-results/task-report.md"]


def is_read_only_external_task(req: ExternalTaskPlanningRequest) -> bool:
    """Return whether the user explicitly forbids project mutations.

    Generic Orchestrator tasks still use an existing project file as a
    compatibility anchor, but the host adapter must treat the result as an
    inline analysis and expose no writable project paths.
    """
    return bool(_READ_ONLY_TASK_RE.search(str(req.description or "")))


def requests_remote_worker(req: ExternalTaskPlanningRequest) -> bool:
    """Return whether the user explicitly requires Worker execution.

    This is a routing constraint, not a workflow intent.  A remote Worker
    request must never increase the score of an unrelated Workflow Pack.
    """
    for clause in _REMOTE_WORKER_CLAUSE_SPLIT_RE.split(str(req.description or "")):
        if not _REMOTE_WORKER_REFERENCE_RE.search(clause):
            continue
        if _REMOTE_WORKER_NEGATIVE_RE.search(clause):
            continue
        if _REMOTE_WORKER_POSITIVE_RE.search(clause):
            return True
    return False


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
        if runtime_state_roots or runtime_state_files or agent_id in _CLOUD_PROVIDER_IDS:
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
        source_root = str(Path(__file__).resolve().parents[1])
        bootstrap = (
            "import runpy,sys;"
            f"sys.path.insert(0,{source_root!r});"
            "runpy.run_module('across_agents_assistant.orchestrator_agent_adapter',run_name='__main__')"
        )
        command = [
            sys.executable,
            "-c",
            bootstrap,
            "--agent",
            clean_agent_id,
        ]
    if clean_agent_id == "kimi":
        command.extend(["--timeout", "1200"])
    return command


def autopilot_workflow_adapter_command(workflow_id: str, loop_spec_id: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [
            sys.executable,
            "autopilot-workflow-adapter",
            "--workflow-id",
            str(workflow_id),
            "--loop-spec",
            str(loop_spec_id),
        ]
    return [
        sys.executable,
        "-m",
        "across_agents_assistant.autopilot_workflow_adapter",
        "--workflow-id",
        str(workflow_id),
        "--loop-spec",
        str(loop_spec_id),
    ]


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
            if (
                _REFERENCE_INPUT_CLAUSE_RE.search(clause)
                and not _DELIVERABLE_ACTION_RE.search(clause)
            ):
                continue
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
