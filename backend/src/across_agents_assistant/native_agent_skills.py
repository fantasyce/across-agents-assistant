from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol

from .agent_ids import LOCAL_CLI_AGENT_IDS, normalize_agent_id


APP_MANAGED_BY = "across-agents-assistant"


class NativeSkillError(Exception):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class NativeSkillCommandRunner(Protocol):
    def run(self, command: List[str], *, timeout: int = 20) -> str:
        ...


class SubprocessNativeSkillCommandRunner:
    def run(self, command: List[str], *, timeout: int = 20) -> str:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise NativeSkillError(f"Executable not found: {command[0]}", status_code=404) from exc
        except subprocess.TimeoutExpired as exc:
            raise NativeSkillError(f"Native skill command timed out: {' '.join(command)}", status_code=504) from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            message = detail or f"Native skill command failed: {' '.join(command)}"
            raise NativeSkillError(message, status_code=502)
        return result.stdout or ""


@dataclass
class NativeSkillRequest:
    identifier: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    body: Optional[str] = None
    scope: str = "user"
    project_dir: Optional[str] = None
    source_path: Optional[str] = None
    version: Optional[str] = None
    force: bool = False


@dataclass
class NativeSkillSummary:
    id: str
    name: str
    description: str = ""
    status: str = "installed"
    source: str = "native"
    version: Optional[str] = None
    path: Optional[str] = None
    availability: Optional[str] = None
    unavailable_reason: Optional[str] = None
    missing_requirements: Optional[List[str]] = None
    repair_suggestions: Optional[List[str]] = None
    managed_by_app: bool = False
    supports_update: bool = False
    supports_uninstall: bool = False


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "skill"


def _clean_frontmatter_value(value: Optional[str]) -> str:
    return (value or "").replace("\n", " ").replace("\r", " ").strip()


def _parse_frontmatter(path: Path) -> Dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    metadata: Dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            metadata[key] = value
    return metadata


def _summary_dict(summary: NativeSkillSummary) -> Dict[str, Any]:
    payload = asdict(summary)
    return {key: value for key, value in payload.items() if value is not None}


INACTIVE_NATIVE_SKILL_STATUSES = {
    "blocked",
    "disabled",
    "error",
    "failed",
    "missing",
    "not_ready",
    "unavailable",
}


def is_native_skill_available(skill: Dict[str, Any]) -> bool:
    status = str(skill.get("status") or "").strip().lower()
    availability = str(skill.get("availability") or "").strip().lower()
    return status not in INACTIVE_NATIVE_SKILL_STATUSES and availability != "unavailable"


def _skill_line_name_and_requirements(line: str) -> Optional[tuple[str, List[str]]]:
    match = re.search(r"([A-Za-z0-9][A-Za-z0-9_.-]*)", line)
    if not match:
        return None
    name = match.group(1)
    requirements: List[str] = []
    requirement_match = re.search(r"\(([^)]*)\)", line[match.end():])
    if requirement_match:
        requirements = [
            item.strip()
            for item in re.split(r";|,", requirement_match.group(1))
            if item.strip()
        ]
    return name, requirements


def _parse_skill_readiness_output(output: str) -> Dict[str, Any]:
    ready_skill_ids: List[str] = []
    unavailable_skills: Dict[str, Dict[str, Any]] = {}
    section: Optional[str] = None

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("ready to use"):
            section = "ready"
            continue
        if lower.startswith("missing requirements"):
            section = "missing"
            continue
        if lower.startswith(("skills status", "total:", "tip:", "eligible:", "disabled:", "blocked")):
            continue
        if section not in {"ready", "missing"}:
            continue

        parsed = _skill_line_name_and_requirements(line)
        if not parsed:
            continue
        name, requirements = parsed
        skill_id = _slugify(name)
        if section == "ready":
            if skill_id not in ready_skill_ids:
                ready_skill_ids.append(skill_id)
            continue
        reason = "Missing requirements"
        if requirements:
            reason += ": " + "; ".join(requirements)
        unavailable_skills[skill_id] = {
            "id": skill_id,
            "name": name,
            "unavailable_reason": reason,
            "missing_requirements": requirements,
            "repair_suggestions": _repair_suggestions_for_requirements(requirements),
        }

    return {
        "ready_skill_ids": ready_skill_ids,
        "unavailable_skill_ids": list(unavailable_skills.keys()),
        "unavailable_skills": unavailable_skills,
    }


def _repair_suggestions_for_requirements(requirements: Iterable[str]) -> List[str]:
    suggestions: List[str] = []
    for requirement in requirements or []:
        text = str(requirement or "").strip()
        if not text:
            continue
        lowered = text.lower()
        label = text.split(":", 1)[1].strip() if ":" in text else text
        if lowered.startswith(("bin:", "bins:", "binary:", "binaries:")):
            suggestions.append(f"Install required binary `{label}` and make it available on PATH.")
        elif lowered.startswith(("env:", "env var:", "environment:", "environment variable:")):
            suggestions.append(f"Set environment variable `{label}` for the agent runtime.")
        elif lowered.startswith(("config:", "configuration:", "settings:")):
            suggestions.append(f"Configure `{label}` for the native skill.")
        elif lowered.startswith(("file:", "path:")):
            suggestions.append(f"Create or grant access to required path `{label}`.")
        else:
            suggestions.append(f"Resolve native skill requirement: {text}.")
    return suggestions


def _apply_skill_readiness(
    skills: List[Dict[str, Any]],
    readiness: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not readiness:
        return skills
    ready_ids = set(readiness.get("ready_skill_ids") or [])
    unavailable = readiness.get("unavailable_skills") or {}
    annotated: List[Dict[str, Any]] = []

    for skill in skills:
        item = dict(skill)
        skill_id = _slugify(str(item.get("id") or item.get("name") or ""))
        if skill_id in unavailable:
            missing = unavailable[skill_id]
            item["status"] = "unavailable"
            item["availability"] = "unavailable"
            item["unavailable_reason"] = missing.get("unavailable_reason") or "Missing requirements"
            item["missing_requirements"] = missing.get("missing_requirements") or []
            item["repair_suggestions"] = missing.get("repair_suggestions") or _repair_suggestions_for_requirements(
                item["missing_requirements"]
            )
        elif skill_id in ready_ids:
            item["availability"] = "available"
        annotated.append(item)
    return annotated


def _parse_cli_skill_lines(output: str, source: str) -> List[Dict[str, Any]]:
    skills: List[Dict[str, Any]] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith(("installed", "available", "skills")):
            continue
        if line[0] in {"┏", "┡", "└", "┗", "┣", "┠", "┌", "├", "╞"}:
            continue
        if "│" in line or "┃" in line:
            cells = [cell.strip() for cell in re.split(r"[│┃]", line) if cell.strip()]
            if not cells:
                continue
            name = cells[0]
            if not name or name.lower() in {"name", "identifier"}:
                continue
            status = cells[-1] if len(cells) > 1 else "installed"
            skills.append(
                _summary_dict(
                    NativeSkillSummary(
                        id=_slugify(name),
                        name=name,
                        status=status or "installed",
                        source=source,
                        supports_update=True,
                        supports_uninstall=source == "hermes",
                    )
                )
            )
            continue
        line = line.lstrip("-* ").strip()
        if not line:
            continue
        parts = [part for part in re.split(r"\s{2,}|\t+", line) if part]
        if not parts:
            parts = line.split()
        name = parts[0].strip()
        if not name or name.lower() in {"name", "identifier"}:
            continue
        status_parts = parts[1:]
        if status_parts and status_parts[-1].lower() in {
            "enabled",
            "disabled",
            "installed",
            "ready",
            "missing",
            "blocked",
            "available",
        }:
            status = status_parts[-1]
        else:
            status = " ".join(status_parts).strip() if status_parts else "installed"
        skills.append(
            _summary_dict(
                NativeSkillSummary(
                    id=_slugify(name),
                    name=name,
                    status=status or "installed",
                    source=source,
                    supports_update=True,
                    supports_uninstall=source == "hermes",
                )
            )
        )
    return skills


class ClaudeNativeSkillAdapter:
    agent_id = "claude"
    display_name = "Claude Code"
    supports_create = True
    supports_install = True
    supports_uninstall = True
    supports_update = False
    supports_check = True

    def __init__(self, user_skills_dir: Optional[Path | str] = None) -> None:
        self.user_skills_dir = Path(user_skills_dir) if user_skills_dir else Path.home() / ".claude" / "skills"

    def list_skills(self, request: Optional[NativeSkillRequest] = None) -> Dict[str, Any]:
        request = request or NativeSkillRequest()
        roots = [(self.user_skills_dir, "user")]
        if request.project_dir:
            roots.append((Path(request.project_dir) / ".claude" / "skills", "project"))

        skills: List[Dict[str, Any]] = []
        for root, source in roots:
            if not root.exists():
                continue
            for child in sorted(root.iterdir()):
                skill_file = child / "SKILL.md"
                if not child.is_dir() or not skill_file.exists():
                    continue
                metadata = _parse_frontmatter(skill_file)
                name = metadata.get("name") or child.name
                description = metadata.get("description") or ""
                skills.append(
                    _summary_dict(
                        NativeSkillSummary(
                            id=child.name,
                            name=name,
                            description=description,
                            source=source,
                            path=str(skill_file),
                            managed_by_app=metadata.get("managed_by") == APP_MANAGED_BY,
                            supports_uninstall=True,
                        )
                    )
                )
        return self._state(skills)

    def install_skill(self, request: NativeSkillRequest) -> Dict[str, Any]:
        if request.source_path:
            return self._install_from_directory(request)
        name = _clean_frontmatter_value(request.name or request.identifier)
        description = _clean_frontmatter_value(request.description)
        if not name:
            raise NativeSkillError("Claude native skills require a name.", status_code=400)
        if not description:
            raise NativeSkillError("Claude native skills require a description.", status_code=400)
        skill_id = _slugify(name)
        root = self._root_for_request(request)
        target = root / skill_id
        if target.exists() and not request.force:
            raise NativeSkillError(f"Native skill already exists: {skill_id}", status_code=409)
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        body = (request.body or "").strip() or description
        skill_file = target / "SKILL.md"
        skill_file.write_text(
            "\n".join(
                [
                    "---",
                    f"name: {name}",
                    f"description: {description}",
                    f"managed_by: {APP_MANAGED_BY}",
                    "---",
                    "",
                    body,
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return _summary_dict(
            NativeSkillSummary(
                id=skill_id,
                name=name,
                description=description,
                status="installed",
                source=request.scope or "user",
                path=str(skill_file),
                managed_by_app=True,
                supports_uninstall=True,
            )
        )

    def uninstall_skill(self, skill_id: str, request: Optional[NativeSkillRequest] = None) -> Dict[str, Any]:
        request = request or NativeSkillRequest()
        root = self._root_for_request(request)
        target = root / _slugify(skill_id)
        skill_file = target / "SKILL.md"
        if not skill_file.exists():
            raise NativeSkillError(f"Native skill not found: {skill_id}", status_code=404)
        metadata = _parse_frontmatter(skill_file)
        if metadata.get("managed_by") != APP_MANAGED_BY and not request.force:
            raise NativeSkillError(
                "Refusing to remove a skill that was not managed by Across Agents Assistant.",
                status_code=409,
            )
        shutil.rmtree(target)
        return {
            "id": _slugify(skill_id),
            "name": metadata.get("name") or skill_id,
            "status": "uninstalled",
            "source": request.scope or "user",
        }

    def update_skill(self, skill_id: str, request: Optional[NativeSkillRequest] = None) -> Dict[str, Any]:
        raise NativeSkillError("Claude native skills are updated by reinstalling with force enabled.", status_code=400)

    def check_skills(self, request: Optional[NativeSkillRequest] = None) -> Dict[str, Any]:
        state = self.list_skills(request)
        warnings = [
            f"{skill['id']} is missing a description."
            for skill in state["skills"]
            if not str(skill.get("description") or "").strip()
        ]
        return {
            "agent_id": self.agent_id,
            "status": "ok" if not warnings else "warning",
            "warnings": warnings,
            "checked_count": len(state["skills"]),
        }

    def _install_from_directory(self, request: NativeSkillRequest) -> Dict[str, Any]:
        source = Path(request.source_path or "").expanduser()
        if not source.exists() or not source.is_dir():
            raise NativeSkillError("Source skill directory does not exist.", status_code=404)
        skill_file = source / "SKILL.md"
        if not skill_file.exists():
            raise NativeSkillError("Source skill directory must contain SKILL.md.", status_code=400)
        metadata = _parse_frontmatter(skill_file)
        skill_id = _slugify(request.identifier or metadata.get("name") or source.name)
        target = self._root_for_request(request) / skill_id
        if target.exists() and not request.force:
            raise NativeSkillError(f"Native skill already exists: {skill_id}", status_code=409)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        return _summary_dict(
            NativeSkillSummary(
                id=skill_id,
                name=metadata.get("name") or skill_id,
                description=metadata.get("description") or "",
                status="installed",
                source=request.scope or "user",
                path=str(target / "SKILL.md"),
                managed_by_app=metadata.get("managed_by") == APP_MANAGED_BY,
                supports_uninstall=True,
            )
        )

    def _root_for_request(self, request: NativeSkillRequest) -> Path:
        scope = (request.scope or "user").strip().lower()
        if scope == "project":
            if not request.project_dir:
                raise NativeSkillError("Project-scoped Claude skills require project_dir.", status_code=400)
            root = Path(request.project_dir) / ".claude" / "skills"
        else:
            root = self.user_skills_dir
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _state(self, skills: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "mode": "directory",
            "supports_create": self.supports_create,
            "supports_install": self.supports_install,
            "supports_uninstall": self.supports_uninstall,
            "supports_update": self.supports_update,
            "supports_check": self.supports_check,
            "skills": skills,
        }


class HermesNativeSkillAdapter:
    agent_id = "hermes"
    display_name = "Hermes"
    supports_create = False
    supports_install = True
    supports_uninstall = True
    supports_update = True
    supports_check = True

    def __init__(self, runner: NativeSkillCommandRunner) -> None:
        self.runner = runner

    def list_skills(self, request: Optional[NativeSkillRequest] = None) -> Dict[str, Any]:
        output = self.runner.run(["hermes", "skills", "list", "--source", "all"], timeout=20)
        return self._state(_parse_cli_skill_lines(output, "hermes"))

    def install_skill(self, request: NativeSkillRequest) -> Dict[str, Any]:
        identifier = request.identifier or request.name
        if not identifier:
            raise NativeSkillError("Hermes native skill install requires an identifier.", status_code=400)
        command = ["hermes", "skills", "install", identifier]
        if request.force:
            command.append("--force")
        command.append("--yes")
        output = self.runner.run(command, timeout=60)
        return {
            "id": _slugify(identifier),
            "name": identifier,
            "status": "installed",
            "source": "hermes",
            "output": output.strip(),
            "command": command,
        }

    def uninstall_skill(self, skill_id: str, request: Optional[NativeSkillRequest] = None) -> Dict[str, Any]:
        command = ["hermes", "skills", "uninstall", skill_id]
        output = self.runner.run(command, timeout=60)
        return {
            "id": _slugify(skill_id),
            "name": skill_id,
            "status": "uninstalled",
            "source": "hermes",
            "output": output.strip(),
            "command": command,
        }

    def update_skill(self, skill_id: str, request: Optional[NativeSkillRequest] = None) -> Dict[str, Any]:
        command = ["hermes", "skills", "update", skill_id]
        output = self.runner.run(command, timeout=60)
        return {
            "id": _slugify(skill_id),
            "name": skill_id,
            "status": "updated",
            "source": "hermes",
            "output": output.strip(),
            "command": command,
        }

    def check_skills(self, request: Optional[NativeSkillRequest] = None) -> Dict[str, Any]:
        command = ["hermes", "skills", "check"]
        output = self.runner.run(command, timeout=60)
        return {
            "agent_id": self.agent_id,
            "status": "checked",
            "output": output.strip(),
            "command": command,
        }

    def _state(self, skills: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "mode": "cli",
            "supports_create": self.supports_create,
            "supports_install": self.supports_install,
            "supports_uninstall": self.supports_uninstall,
            "supports_update": self.supports_update,
            "supports_check": self.supports_check,
            "skills": skills,
        }


class OpenClawNativeSkillAdapter:
    agent_id = "openclaw"
    display_name = "OpenClaw"
    supports_create = False
    supports_install = True
    supports_uninstall = False
    supports_update = True
    supports_check = True

    def __init__(self, runner: NativeSkillCommandRunner) -> None:
        self.runner = runner

    def list_skills(self, request: Optional[NativeSkillRequest] = None) -> Dict[str, Any]:
        command = ["openclaw", "skills", "list", "--json"]
        if request and request.project_dir:
            command.extend(["--agent", request.project_dir])
        output = self.runner.run(command, timeout=30)
        readiness = None
        readiness_error = None
        try:
            readiness = self._check_readiness()
        except NativeSkillError as exc:
            readiness_error = str(exc)
        skills = _apply_skill_readiness(self._parse_json_or_text(output), readiness)
        state = self._state(skills)
        if readiness:
            state["readiness"] = readiness
        if readiness_error:
            state["readiness_error"] = readiness_error
        return state

    def install_skill(self, request: NativeSkillRequest) -> Dict[str, Any]:
        identifier = request.identifier or request.name
        if not identifier:
            raise NativeSkillError("OpenClaw native skill install requires an identifier.", status_code=400)
        command = ["openclaw", "skills", "install", identifier]
        if request.force:
            command.append("--force")
        if request.version:
            command.extend(["--version", request.version])
        output = self.runner.run(command, timeout=60)
        return {
            "id": _slugify(identifier),
            "name": identifier,
            "status": "installed",
            "source": "openclaw",
            "output": output.strip(),
            "command": command,
        }

    def uninstall_skill(self, skill_id: str, request: Optional[NativeSkillRequest] = None) -> Dict[str, Any]:
        raise NativeSkillError("OpenClaw does not expose a native uninstall command in this build.", status_code=501)

    def update_skill(self, skill_id: str, request: Optional[NativeSkillRequest] = None) -> Dict[str, Any]:
        command = ["openclaw", "skills", "update", skill_id]
        output = self.runner.run(command, timeout=60)
        return {
            "id": _slugify(skill_id),
            "name": skill_id,
            "status": "updated",
            "source": "openclaw",
            "output": output.strip(),
            "command": command,
        }

    def check_skills(self, request: Optional[NativeSkillRequest] = None) -> Dict[str, Any]:
        command = ["openclaw", "skills", "check"]
        output = self.runner.run(command, timeout=60)
        readiness = _parse_skill_readiness_output(output)
        return {
            "agent_id": self.agent_id,
            "status": "checked",
            "output": output.strip(),
            "command": command,
            **readiness,
        }

    def _check_readiness(self) -> Dict[str, Any]:
        command = ["openclaw", "skills", "check"]
        output = self.runner.run(command, timeout=60)
        return _parse_skill_readiness_output(output)

    def _parse_json_or_text(self, output: str) -> List[Dict[str, Any]]:
        try:
            raw = json.loads(output)
        except Exception:
            return _parse_cli_skill_lines(output, "openclaw")
        if isinstance(raw, dict):
            values = raw.get("skills") or raw.get("items") or []
        elif isinstance(raw, list):
            values = raw
        else:
            values = []
        skills: List[Dict[str, Any]] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("id") or item.get("slug") or "").strip()
            if not name:
                continue
            status = "ready" if item.get("ready") is True else str(item.get("status") or "installed")
            skills.append(
                _summary_dict(
                    NativeSkillSummary(
                        id=_slugify(str(item.get("id") or item.get("slug") or name)),
                        name=name,
                        description=str(item.get("description") or ""),
                        status=status,
                        source="openclaw",
                        version=str(item["version"]) if item.get("version") else None,
                        supports_update=True,
                        supports_uninstall=False,
                    )
                )
            )
        return skills

    def _state(self, skills: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "mode": "cli",
            "supports_create": self.supports_create,
            "supports_install": self.supports_install,
            "supports_uninstall": self.supports_uninstall,
            "supports_update": self.supports_update,
            "supports_check": self.supports_check,
            "skills": skills,
        }


class NativeSkillManager:
    def __init__(
        self,
        *,
        command_runner: Optional[NativeSkillCommandRunner] = None,
        claude_user_skills_dir: Optional[Path | str] = None,
    ) -> None:
        runner = command_runner or SubprocessNativeSkillCommandRunner()
        self.adapters = {
            "openclaw": OpenClawNativeSkillAdapter(runner),
            "hermes": HermesNativeSkillAdapter(runner),
            "claude": ClaudeNativeSkillAdapter(claude_user_skills_dir),
        }

    def list_all_agent_skills(self) -> Dict[str, Dict[str, Any]]:
        states: Dict[str, Dict[str, Any]] = {}
        for agent_id in LOCAL_CLI_AGENT_IDS:
            try:
                states[agent_id] = self.list_agent_skills(agent_id)
            except NativeSkillError as exc:
                states[agent_id] = self._error_state(agent_id, str(exc))
        return states

    def list_agent_skills(self, agent_id: str, request: Optional[NativeSkillRequest] = None) -> Dict[str, Any]:
        adapter = self._adapter(agent_id)
        return adapter.list_skills(request)

    def install_skill(self, agent_id: str, request: NativeSkillRequest) -> Dict[str, Any]:
        adapter = self._adapter(agent_id)
        return adapter.install_skill(request)

    def uninstall_skill(
        self,
        agent_id: str,
        skill_id: str,
        request: Optional[NativeSkillRequest] = None,
    ) -> Dict[str, Any]:
        adapter = self._adapter(agent_id)
        return adapter.uninstall_skill(skill_id, request)

    def update_skill(
        self,
        agent_id: str,
        skill_id: str,
        request: Optional[NativeSkillRequest] = None,
    ) -> Dict[str, Any]:
        adapter = self._adapter(agent_id)
        return adapter.update_skill(skill_id, request)

    def check_skills(self, agent_id: str, request: Optional[NativeSkillRequest] = None) -> Dict[str, Any]:
        adapter = self._adapter(agent_id)
        return adapter.check_skills(request)

    def _adapter(self, agent_id: str):
        normalized = normalize_agent_id(agent_id) or agent_id
        adapter = self.adapters.get(normalized)
        if not adapter:
            raise NativeSkillError(f"Native skills are only supported for local agents: {agent_id}", status_code=404)
        return adapter

    def _error_state(self, agent_id: str, message: str) -> Dict[str, Any]:
        normalized = normalize_agent_id(agent_id) or agent_id
        adapter = self.adapters.get(normalized)
        return {
            "agent_id": normalized,
            "display_name": getattr(adapter, "display_name", normalized),
            "mode": getattr(adapter, "mode", "native"),
            "supports_create": bool(getattr(adapter, "supports_create", False)),
            "supports_install": bool(getattr(adapter, "supports_install", False)),
            "supports_uninstall": bool(getattr(adapter, "supports_uninstall", False)),
            "supports_update": bool(getattr(adapter, "supports_update", False)),
            "supports_check": bool(getattr(adapter, "supports_check", False)),
            "skills": [],
            "error": message,
        }


def get_native_skill_manager() -> NativeSkillManager:
    return NativeSkillManager()
