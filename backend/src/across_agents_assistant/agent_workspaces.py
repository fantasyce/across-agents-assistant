"""Durable, isolated lifecycle for parallel local-agent workspaces.

Prompts and agent transcripts are intentionally memory-only. Durable state is
limited to lifecycle metadata, review comments metadata, diffs, test outcomes,
and evidence needed to review or promote a candidate after a restart.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from .agent_ids import LOCAL_CLI_AGENT_IDS, normalize_agent_id
from .agent_workspace_readiness import agent_workspace_root
from .local_agent_health import detect_local_agents


WORKSPACE_SCHEMA_VERSION = "agent-workspace/1.1"
EVENT_SCHEMA_VERSION = "agent-workspace-event/1.0"
TERMINAL_CANDIDATE_STATUSES = {"completed", "failed", "cancelled", "interrupted", "blocked"}
ACTIVE_CANDIDATE_STATUSES = {"pending", "running", "cancelling"}
ACTIVE_WORKSPACE_STATUSES = {"creating", "running", "revising", "cancelling", "promoting"}
MAX_AGENTS = 4
MAX_PROMPT_LENGTH = 50_000
MAX_COMMENT_LENGTH = 10_000
MAX_LINE_REVIEW_COMMENTS = 50
MAX_LINE_REVIEW_BODY_LENGTH = 4_000
MAX_LINE_REVIEW_TOTAL_LENGTH = 20_000
MAX_VALIDATION_COMMANDS = 8
MAX_COMMAND_PARTS = 64
MAX_COMMAND_PART_LENGTH = 1_024
DEFAULT_TASK_TIMEOUT_SECONDS = 900.0
DEFAULT_TEST_TIMEOUT_SECONDS = 300.0
DEFAULT_COMMAND_IDLE_TIMEOUT_SECONDS = 30.0

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SENSITIVE_KEY_RE = re.compile(
    r"(?:secret|token|password|passwd|credential|api[_-]?key|private[_-]?key|authorization|cookie|transcript|prompt|stdout|stderr|output|content|instructions?)",
    re.IGNORECASE,
)
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\b(?:ghp|github_pat|glpat)-?[A-Za-z0-9_-]{12,}\b", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}\b", re.IGNORECASE),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(
        r"\b(?:API_KEY|ACCESS_TOKEN|AUTH_TOKEN|PASSWORD|SECRET_KEY)\s*[:=]\s*[^\s]{6,}",
        re.IGNORECASE,
    ),
)


class AgentWorkspaceError(RuntimeError):
    """A client-actionable workspace lifecycle error."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message

    def detail(self) -> Dict[str, str]:
        return {"code": self.code, "message": self.message}


AgentRunner = Callable[[str, str, str, float, str], Mapping[str, Any]]
AgentCanceller = Callable[[str], bool]
QualityGateRunner = Callable[[str, str, float, Mapping[str, Any]], Mapping[str, Any]]
CapabilityPreflight = Callable[[str, Sequence[str], Optional[str]], Mapping[str, Any]]
QUALITY_GATE_WORKFLOWS = {"repo-quality-copilot", "repo-push-gate", "across-gate"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def inspect_git_repository(
    repo_root: str,
    *,
    repo_access: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Read-only repository validation shared by readiness and creation."""
    raw = str(repo_root or "").strip()
    if not raw:
        raise AgentWorkspaceError(422, "repo_root_required", "repo_root is required.")
    supplied = Path(raw).expanduser()
    if not supplied.is_absolute():
        raise AgentWorkspaceError(422, "repo_root_not_absolute", "repo_root must be an absolute path.")
    access = _normalize_repo_access(repo_access)
    if access["mode"] == "security_scoped" and not access["security_scope_active"]:
        raise AgentWorkspaceError(
            403,
            "repository_access_not_authorized",
            "Swift must activate the security-scoped repository URL before this request "
            "and keep it active for the workspace lifecycle.",
        )
    try:
        if supplied.is_symlink():
            raise AgentWorkspaceError(422, "repo_root_symlink", "repo_root must not be a symbolic link.")
        resolved = supplied.resolve()
        is_directory = resolved.is_dir()
    except PermissionError as exc:
        raise AgentWorkspaceError(
            403,
            "repository_access_denied",
            "The repository directory is not accessible. Grant folder access in the macOS picker and retry.",
        ) from exc
    if resolved == Path(resolved.anchor) or resolved == Path.home().resolve():
        raise AgentWorkspaceError(422, "unsafe_repo_root", "repo_root is too broad for an isolated workspace run.")
    if not is_directory:
        raise AgentWorkspaceError(404, "repo_root_not_found", "repo_root must be an existing directory.")
    if shutil.which("git") is None:
        raise AgentWorkspaceError(503, "git_unavailable", "git is required for isolated workspaces.")

    try:
        top_level_result = _run_command(
            ["git", "-C", str(resolved), "rev-parse", "--show-toplevel"],
            operation="Inspect repository root",
            check=False,
        )
    except AgentWorkspaceError as exc:
        if exc.code in {"command_idle_timeout", "command_total_timeout"}:
            raise AgentWorkspaceError(
                408,
                "repository_access_timeout",
                "Repository inspection made no bounded progress. This commonly means macOS "
                "folder access is missing; activate a security-scoped grant and retry.",
            ) from exc
        raise
    if _permission_failure(top_level_result.stderr):
        raise AgentWorkspaceError(
            403,
            "repository_access_denied",
            "Git could not access the repository. Grant folder access in the macOS picker and retry.",
        )
    if top_level_result.returncode != 0:
        raise AgentWorkspaceError(422, "not_git_repository", "repo_root must be a git repository.")
    top_level = top_level_result.stdout.strip()
    actual_root = Path(top_level).resolve()
    if actual_root != resolved:
        raise AgentWorkspaceError(
            422,
            "repo_root_not_top_level",
            "repo_root must be the repository top-level directory.",
        )
    managed_root = agent_workspace_root().resolve()
    if _is_relative_to(resolved, managed_root) or _is_relative_to(managed_root, resolved):
        raise AgentWorkspaceError(
            422,
            "unsafe_repo_root",
            "Source repositories and managed agent workspaces must not contain one another.",
        )

    base_result = _run_command(
        ["git", "-C", str(resolved), "rev-parse", "HEAD"],
        operation="Resolve repository base",
        check=False,
    )
    if base_result.returncode != 0:
        raise AgentWorkspaceError(422, "repository_has_no_commits", "repo_root must have a committed base revision.")
    base_sha = base_result.stdout.strip()
    branch = _run_command(
        ["git", "-C", str(resolved), "branch", "--show-current"],
        operation="Resolve repository branch",
    ).stdout.strip()
    status = _run_command(
        ["git", "-C", str(resolved), "status", "--porcelain=v1", "--untracked-files=all"],
        operation="Inspect repository status",
    ).stdout
    return {
        "repo_root": str(resolved),
        "base_sha": base_sha,
        "branch": branch or None,
        "clean": not bool(status.strip()),
        "access": access,
    }


class AgentWorkspaceManager:
    """Create and supervise durable sets of isolated git worktrees."""

    def __init__(
        self,
        *,
        root: Optional[Path] = None,
        agent_runner: Optional[AgentRunner] = None,
        agent_canceller: Optional[AgentCanceller] = None,
        agent_health_provider: Optional[Callable[..., Mapping[str, Any]]] = None,
        quality_gate_runner: Optional[QualityGateRunner] = None,
        capability_preflight: Optional[CapabilityPreflight] = None,
        max_workers: int = MAX_AGENTS,
    ) -> None:
        self.root = (root or agent_workspace_root()).expanduser().resolve()
        self._ensure_managed_root()
        self._agent_runner = agent_runner or self._unconfigured_runner
        self._agent_canceller = agent_canceller or (lambda _session_id: False)
        self._agent_health_provider = agent_health_provider or detect_local_agents
        self._quality_gate_runner = quality_gate_runner
        self._capability_preflight = capability_preflight
        self._lock = threading.RLock()
        self._create_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=max(1, min(max_workers, MAX_AGENTS)))
        self._futures: Dict[str, Future[Any]] = {}
        self._recover_durable_states()

    def shutdown(self, *, wait: bool = False, cancel_active: bool = False) -> None:
        if cancel_active:
            for state in self._iter_states():
                if state.get("status") in ACTIVE_WORKSPACE_STATUSES and state.get("status") != "promoting":
                    try:
                        self.cancel(str(state["workspace_id"]), reason="backend_shutdown")
                    except AgentWorkspaceError:
                        pass
        self._executor.shutdown(wait=wait, cancel_futures=True)

    def create(
        self,
        *,
        repo_root: str,
        prompt: str,
        agent_ids: Sequence[str],
        execution_strategy: str = "parallel_worktrees",
        validation_commands: Optional[Sequence[Sequence[str]]] = None,
        task_timeout_seconds: float = DEFAULT_TASK_TIMEOUT_SECONDS,
        test_timeout_seconds: float = DEFAULT_TEST_TIMEOUT_SECONDS,
        idempotency_key: Optional[str] = None,
        workflow: Optional[str] = None,
        quality_gate_ci_path: Optional[str] = None,
        quality_gate_ci_wait_seconds: int = 0,
        quality_gate_draft_pr: bool = False,
        repo_access: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._create_lock:
            return self._create_serialized(
                repo_root=repo_root,
                prompt=prompt,
                agent_ids=agent_ids,
                execution_strategy=execution_strategy,
                validation_commands=validation_commands,
                task_timeout_seconds=task_timeout_seconds,
                test_timeout_seconds=test_timeout_seconds,
                idempotency_key=idempotency_key,
                workflow=workflow,
                quality_gate_ci_path=quality_gate_ci_path,
                quality_gate_ci_wait_seconds=quality_gate_ci_wait_seconds,
                quality_gate_draft_pr=quality_gate_draft_pr,
                repo_access=repo_access,
            )

    def _create_serialized(
        self,
        *,
        repo_root: str,
        prompt: str,
        agent_ids: Sequence[str],
        execution_strategy: str,
        validation_commands: Optional[Sequence[Sequence[str]]],
        task_timeout_seconds: float,
        test_timeout_seconds: float,
        idempotency_key: Optional[str],
        workflow: Optional[str],
        quality_gate_ci_path: Optional[str],
        quality_gate_ci_wait_seconds: int,
        quality_gate_draft_pr: bool,
        repo_access: Optional[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        prompt_text = str(prompt or "")
        if not prompt_text.strip():
            raise AgentWorkspaceError(422, "prompt_required", "prompt is required.")
        if len(prompt_text) > MAX_PROMPT_LENGTH:
            raise AgentWorkspaceError(422, "prompt_too_long", "prompt exceeds the bounded task limit.")
        if execution_strategy != "parallel_worktrees":
            raise AgentWorkspaceError(
                422,
                "unsupported_execution_strategy",
                "Only parallel_worktrees is supported.",
            )
        normalized_agents = self._validate_agents(agent_ids)
        commands = _normalize_validation_commands(validation_commands)
        task_timeout = _bounded_timeout(task_timeout_seconds, "task_timeout_seconds", maximum=3600.0)
        test_timeout = _bounded_timeout(test_timeout_seconds, "test_timeout_seconds", maximum=1800.0)
        capability_preflight = self._run_capability_preflight(
            prompt_text,
            normalized_agents,
            str(workflow or "").strip() or None,
        )
        quality_gate_options = _normalize_quality_gate_options(
            ci_path=quality_gate_ci_path,
            ci_wait_seconds=quality_gate_ci_wait_seconds,
            draft_pr=quality_gate_draft_pr,
        )
        repo = inspect_git_repository(repo_root, repo_access=repo_access)
        prompt_digest = _sha256_text(prompt_text)
        request_fingerprint = _sha256_json(
            {
                "repo_root": repo["repo_root"],
                "prompt_digest": prompt_digest,
                "agent_ids": normalized_agents,
                "execution_strategy": execution_strategy,
                "validation_commands": commands,
                "task_timeout_seconds": task_timeout,
                "test_timeout_seconds": test_timeout,
                "workflow": str(workflow or "").strip() or None,
                "quality_gate_ci_sha256": quality_gate_options.get("ci_sha256"),
                "quality_gate_ci_wait_seconds": quality_gate_options["ci_wait_seconds"],
                "quality_gate_draft_pr": quality_gate_options["draft_pr"],
                "repo_access": repo["access"],
            }
        )
        idempotency_hash = _sha256_text(idempotency_key.strip()) if idempotency_key and idempotency_key.strip() else None
        if idempotency_hash:
            existing = self._find_by_idempotency_hash(idempotency_hash)
            if existing:
                if existing.get("request_fingerprint") != request_fingerprint:
                    raise AgentWorkspaceError(
                        409,
                        "idempotency_conflict",
                        "The idempotency key was already used for a different workspace request.",
                    )
                return self._public_state(existing)
        if not repo["clean"]:
            raise AgentWorkspaceError(
                409,
                "source_not_clean",
                "The source repository must be clean before isolated workspaces are created.",
            )

        workspace_id = f"aws-{uuid.uuid4().hex}"
        workspace_dir = self._workspace_dir(workspace_id)
        worktrees_dir = workspace_dir / "worktrees"
        gitdirs_dir = workspace_dir / "gitdirs"
        workspace_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
        worktrees_dir.mkdir(mode=0o700)
        gitdirs_dir.mkdir(mode=0o700)
        candidates: List[Dict[str, Any]] = []
        try:
            for agent_id in normalized_agents:
                candidate_id = f"{agent_id}-{uuid.uuid4().hex[:10]}"
                worktree = worktrees_dir / candidate_id
                git_dir = gitdirs_dir / f"{candidate_id}.git"
                _run_command(
                    [
                        "git",
                        "clone",
                        "--bare",
                        "--shared",
                        "--no-tags",
                        repo["repo_root"],
                        str(git_dir),
                    ],
                    operation="Create isolated candidate git directory",
                )
                _run_command(
                    [
                        "git",
                        "--git-dir",
                        str(git_dir),
                        "worktree",
                        "add",
                        "--detach",
                        str(worktree),
                        repo["base_sha"],
                    ],
                    operation="Create isolated git worktree",
                )
                candidates.append(
                    {
                        "candidate_id": candidate_id,
                        "agent_id": agent_id,
                        "status": "pending",
                        "attempt": 1,
                        "worktree": str(worktree),
                        "git_dir": str(git_dir),
                        "session_id": f"{workspace_id}:{candidate_id}:1",
                        "started_at": None,
                        "completed_at": None,
                        "comparison": _empty_comparison(),
                        "evidence": _empty_evidence(),
                    }
                )
        except Exception:
            for candidate in candidates:
                self._remove_worktree(
                    Path(candidate["git_dir"]),
                    Path(candidate["worktree"]),
                    tolerate_errors=True,
                )
            shutil.rmtree(workspace_dir, ignore_errors=True)
            raise

        now = utc_now()
        state: Dict[str, Any] = {
            "schema_version": WORKSPACE_SCHEMA_VERSION,
            "workspace_id": workspace_id,
            "status": "running",
            "created_at": now,
            "updated_at": now,
            "repo_root": repo["repo_root"],
            "repo_access": repo["access"],
            "base_sha": repo["base_sha"],
            "base_branch": repo["branch"],
            "execution_strategy": execution_strategy,
            "workflow": str(workflow or "").strip() or None,
            "quality_gate_options": quality_gate_options,
            "prompt_digest": prompt_digest,
            "prompt_length": len(prompt_text),
            "agent_ids": normalized_agents,
            "capability_preflight": capability_preflight,
            "validation_commands": commands,
            "task_timeout_seconds": task_timeout,
            "test_timeout_seconds": test_timeout,
            "selected_candidate_id": None,
            "candidates": candidates,
            "review_comments": [],
            "line_review_batches": [],
            "promotion": {
                "status": "review_required",
                "approved": False,
                "candidate_id": None,
                "promoted_at": None,
            },
            "cancel_requested": False,
            "cleanup": {"status": "retained", "completed_at": None},
            "event_sequence": 0,
            "request_fingerprint": request_fingerprint,
            "idempotency_hash": idempotency_hash,
        }
        with self._lock:
            self._write_state(state)
            self._append_event_locked(
                state,
                "workspace.created",
                {
                    "base_sha": repo["base_sha"],
                    "agent_count": len(candidates),
                    "execution_strategy": execution_strategy,
                },
            )
            for candidate in candidates:
                self._append_event_locked(
                    state,
                    "candidate.assigned",
                    {"agent_id": candidate["agent_id"], "attempt": 1},
                    candidate_id=candidate["candidate_id"],
                )

        for candidate in candidates:
            self._submit_candidate(workspace_id, candidate["candidate_id"], prompt_text)
        return self.get(workspace_id)

    def _run_capability_preflight(
        self,
        prompt: str,
        agent_ids: Sequence[str],
        workflow: Optional[str],
    ) -> Dict[str, Any]:
        if self._capability_preflight is None:
            return {
                "status": "not_configured",
                "selected_agent_ids": list(agent_ids),
                "recommended_agent_ids": [],
                "agent_summaries": [],
                "warnings": [],
            }
        try:
            raw = self._capability_preflight(prompt, agent_ids, workflow)
        except Exception:
            return {
                "status": "unavailable",
                "selected_agent_ids": list(agent_ids),
                "recommended_agent_ids": [],
                "agent_summaries": [],
                "warnings": ["Capability preflight was unavailable."],
            }
        return _normalize_capability_preflight(raw, agent_ids)

    def list(self) -> Dict[str, Any]:
        states = [self._public_state(state) for state in self._iter_states()]
        states.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return {"workspaces": states, "count": len(states)}

    def get(self, workspace_id: str) -> Dict[str, Any]:
        with self._lock:
            return self._public_state(self._load_state(workspace_id))

    def events(self, workspace_id: str, *, after_sequence: Optional[int] = None) -> Dict[str, Any]:
        with self._lock:
            state = self._load_state(workspace_id)
            path = self._events_path(workspace_id)
            events: List[Dict[str, Any]] = []
            if path.exists():
                for raw_line in path.read_text(encoding="utf-8").splitlines():
                    if not raw_line.strip():
                        continue
                    try:
                        event = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue
                    sequence = event.get("sequence")
                    if after_sequence is not None and isinstance(sequence, int) and sequence <= after_sequence:
                        continue
                    events.append(event)
            return {
                "workspace_id": workspace_id,
                "workspace_status": state.get("status"),
                "events": events,
                "last_sequence": state.get("event_sequence", 0),
            }

    def comparison(self, workspace_id: str) -> Dict[str, Any]:
        with self._lock:
            state = self._load_state(workspace_id)
            candidates = []
            for candidate in state.get("candidates", []):
                item = {
                    "candidate_id": candidate.get("candidate_id"),
                    "agent_id": candidate.get("agent_id"),
                    "status": candidate.get("status"),
                    "selected": candidate.get("candidate_id") == state.get("selected_candidate_id"),
                    "comparison": _sanitize_for_persistence(candidate.get("comparison") or {}),
                    "evidence": _sanitize_for_persistence(candidate.get("evidence") or {}),
                }
                patch_path = self._patch_path(workspace_id, str(candidate.get("candidate_id")))
                comparison = candidate.get("comparison") or {}
                if comparison.get("patch_available") and patch_path.exists():
                    patch_text = patch_path.read_text(encoding="utf-8", errors="replace")
                    if not _contains_secret(patch_text):
                        item["diff"] = patch_text
                candidates.append(item)
            return {
                "workspace_id": workspace_id,
                "base_sha": state.get("base_sha"),
                "status": state.get("status"),
                "selected_candidate_id": state.get("selected_candidate_id"),
                "candidates": candidates,
            }

    def select(self, workspace_id: str, candidate_id: str) -> Dict[str, Any]:
        with self._lock:
            state = self._load_state(workspace_id)
            candidate = self._candidate(state, candidate_id)
            if candidate.get("status") != "completed":
                raise AgentWorkspaceError(409, "candidate_not_reviewable", "Only completed candidates can be selected.")
            if not (candidate.get("evidence") or {}).get("ready_for_review"):
                raise AgentWorkspaceError(409, "candidate_evidence_incomplete", "Candidate evidence is not ready for review.")
            if state.get("selected_candidate_id") == candidate_id:
                return self._public_state(state)
            state["selected_candidate_id"] = candidate_id
            state["updated_at"] = utc_now()
            state["promotion"]["candidate_id"] = candidate_id
            self._append_event_locked(state, "candidate.selected", {}, candidate_id=candidate_id)
            return self._public_state(state)

    def comment(self, workspace_id: str, candidate_id: str, comment: str) -> Dict[str, Any]:
        comment_text = str(comment or "")
        if not comment_text.strip():
            raise AgentWorkspaceError(422, "comment_required", "comment is required.")
        if len(comment_text) > MAX_COMMENT_LENGTH:
            raise AgentWorkspaceError(422, "comment_too_long", "comment exceeds the bounded feedback limit.")
        with self._lock:
            state = self._load_state(workspace_id)
            if state.get("status") in {"promoted", "promoting", "cleaned"} or state.get("cancel_requested"):
                raise AgentWorkspaceError(
                    409,
                    "workspace_not_reviewable",
                    "This workspace no longer accepts review feedback.",
                )
            candidate = self._candidate(state, candidate_id)
            if candidate.get("status") not in TERMINAL_CANDIDATE_STATUSES:
                raise AgentWorkspaceError(409, "candidate_busy", "Wait for the candidate to stop before sending feedback.")
            if candidate.get("status") == "blocked":
                raise AgentWorkspaceError(409, "candidate_blocked", "Blocked candidates cannot be relaunched.")
            attempt = int(candidate.get("attempt") or 1) + 1
            session_id = f"{workspace_id}:{candidate_id}:{attempt}"
            candidate.update(
                {
                    "status": "pending",
                    "attempt": attempt,
                    "session_id": session_id,
                    "started_at": None,
                    "completed_at": None,
                    "comparison": _empty_comparison(),
                    "evidence": _empty_evidence(),
                }
            )
            patch_path = self._patch_path(workspace_id, candidate_id)
            patch_path.unlink(missing_ok=True)
            metadata = {
                "comment_id": f"comment-{uuid.uuid4().hex}",
                "candidate_id": candidate_id,
                "created_at": utc_now(),
                "comment_digest": _sha256_text(comment_text),
                "comment_length": len(comment_text),
                "redacted": True,
            }
            state.setdefault("review_comments", []).append(metadata)
            state["status"] = "revising"
            state["selected_candidate_id"] = None
            state["promotion"] = {
                "status": "review_required",
                "approved": False,
                "candidate_id": None,
                "promoted_at": None,
            }
            state["updated_at"] = utc_now()
            self._append_event_locked(
                state,
                "review.comment.accepted",
                {"comment_id": metadata["comment_id"], "comment_length": len(comment_text), "attempt": attempt},
                candidate_id=candidate_id,
            )
        feedback_prompt = (
            "Apply the following human review feedback to the current isolated candidate. "
            "Keep the change bounded and run only repository-safe checks.\n\n"
            + comment_text
        )
        self._submit_candidate(workspace_id, candidate_id, feedback_prompt)
        return self.get(workspace_id)

    def line_review(
        self,
        workspace_id: str,
        candidate_id: str,
        *,
        anchor: Mapping[str, Any],
        comments: Sequence[Mapping[str, Any]],
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Validate anchored line comments and relaunch exactly one candidate."""
        normalized_anchor = _normalize_review_anchor(anchor)
        normalized_comments = _normalize_line_review_comments(comments)
        request_fingerprint = _sha256_json(
            {
                "candidate_id": candidate_id,
                "anchor": normalized_anchor,
                "comments": [
                    {
                        "path": item["path"],
                        "side": item["side"],
                        "start_line": item["start_line"],
                        "line": item["line"],
                        "body_sha256": _sha256_text(item["body"]),
                    }
                    for item in normalized_comments
                ],
            }
        )
        idempotency_hash = (
            _sha256_text(str(idempotency_key).strip())
            if str(idempotency_key or "").strip()
            else None
        )
        with self._lock:
            state = self._load_state(workspace_id)
            for prior in state.get("line_review_batches", []):
                if idempotency_hash and prior.get("idempotency_hash") == idempotency_hash:
                    if prior.get("request_fingerprint") != request_fingerprint:
                        raise AgentWorkspaceError(
                            409,
                            "line_review_idempotency_conflict",
                            "The line-review idempotency key was already used with different content.",
                        )
                    return self._public_state(state)
            if state.get("status") in {"promoted", "promoting", "cleaned"} or state.get("cancel_requested"):
                raise AgentWorkspaceError(409, "workspace_not_reviewable", "This workspace no longer accepts review feedback.")
            candidate = self._candidate(state, candidate_id)
            if candidate.get("status") != "completed":
                raise AgentWorkspaceError(
                    409,
                    "candidate_not_reviewable",
                    "Line review requires a completed candidate diff.",
                )

            # Rebuild the evidence before comparing anchors so edits made after
            # the reviewer loaded the diff are detected, not silently accepted.
            self._refresh_candidate_locked(state, candidate)
            current_anchor = _candidate_review_anchor(state, candidate)
            if current_anchor != normalized_anchor:
                raise AgentWorkspaceError(
                    409,
                    "stale_review_anchor",
                    "The candidate diff changed after review began. Reload the comparison and re-anchor the comments.",
                )
            patch_path = self._patch_path(workspace_id, candidate_id)
            if not patch_path.is_file():
                raise AgentWorkspaceError(409, "diff_unavailable", "The anchored candidate patch is unavailable.")
            patch_text = patch_path.read_text(encoding="utf-8", errors="strict")
            _validate_review_locations(patch_text, normalized_comments)

            attempt = int(candidate.get("attempt") or 1) + 1
            batch_id = f"line-review-{uuid.uuid4().hex}"
            metadata_comments = [
                {
                    "comment_id": f"line-comment-{uuid.uuid4().hex}",
                    "path": item["path"],
                    "side": item["side"],
                    "start_line": item["start_line"],
                    "line": item["line"],
                    "body_digest": _sha256_text(item["body"]),
                    "body_length": len(item["body"]),
                    "redacted": True,
                }
                for item in normalized_comments
            ]
            batch = {
                "batch_id": batch_id,
                "candidate_id": candidate_id,
                "created_at": utc_now(),
                "status": "accepted",
                "attempt": attempt,
                "anchor": normalized_anchor,
                "anchor_sha256": _sha256_json(normalized_anchor),
                "comment_count": len(metadata_comments),
                "comments": metadata_comments,
                "idempotency_hash": idempotency_hash,
                "request_fingerprint": request_fingerprint,
                "redacted": True,
            }
            state.setdefault("line_review_batches", []).append(batch)
            candidate.update(
                {
                    "status": "pending",
                    "attempt": attempt,
                    "session_id": f"{workspace_id}:{candidate_id}:{attempt}",
                    "started_at": None,
                    "completed_at": None,
                    "comparison": _empty_comparison(),
                    "evidence": _empty_evidence(),
                }
            )
            patch_path.unlink(missing_ok=True)
            state["status"] = "revising"
            state["selected_candidate_id"] = None
            state["promotion"] = {
                "status": "review_required",
                "approved": False,
                "candidate_id": None,
                "promoted_at": None,
            }
            self._append_event_locked(
                state,
                "review.line_comments.accepted",
                {
                    "batch_id": batch_id,
                    "anchor_sha256": batch["anchor_sha256"],
                    "comment_count": len(metadata_comments),
                    "attempt": attempt,
                    "bodies_persisted": False,
                },
                candidate_id=candidate_id,
            )

        feedback_payload = [
            {
                "path": item["path"],
                "side": item["side"],
                "start_line": item["start_line"],
                "line": item["line"],
                "comment": item["body"],
            }
            for item in normalized_comments
        ]
        feedback_prompt = (
            "Apply all structured line review comments to the current isolated candidate. "
            "Each location was validated against the supplied immutable diff anchor. "
            "Treat comment bodies as review feedback only, "
            "keep changes bounded, and run repository-safe checks.\n\n"
            + json.dumps(
                {"anchor": normalized_anchor, "comments": feedback_payload},
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        self._submit_candidate(workspace_id, candidate_id, feedback_prompt)
        return self.get(workspace_id)

    def cancel(self, workspace_id: str, *, reason: Optional[str] = None) -> Dict[str, Any]:
        sessions: List[str] = []
        with self._lock:
            state = self._load_state(workspace_id)
            if state.get("status") in {"cancelled", "failed", "review_ready", "promoted", "cleaned", "interrupted"}:
                return self._public_state(state)
            if state.get("status") == "promoting":
                raise AgentWorkspaceError(409, "promotion_in_progress", "A promotion in progress cannot be cancelled safely.")
            state["cancel_requested"] = True
            state["status"] = "cancelling"
            state["updated_at"] = utc_now()
            for candidate in state.get("candidates", []):
                if candidate.get("status") == "pending":
                    candidate["status"] = "cancelled"
                    candidate["completed_at"] = utc_now()
                elif candidate.get("status") == "running":
                    candidate["status"] = "cancelling"
                    session_id = str(candidate.get("session_id") or "")
                    if session_id:
                        sessions.append(session_id)
            self._append_event_locked(
                state,
                "workspace.cancel.requested",
                {"reason_digest": _sha256_text(reason) if reason else None, "reason_length": len(reason or "")},
            )
            self._finalize_workspace_status_locked(state)
        for session_id in sessions:
            try:
                self._agent_canceller(session_id)
            except Exception:
                pass
        return self.get(workspace_id)

    def cleanup(self, workspace_id: str) -> Dict[str, Any]:
        with self._lock:
            state = self._load_state(workspace_id)
            if any(candidate.get("status") in ACTIVE_CANDIDATE_STATUSES for candidate in state.get("candidates", [])):
                raise AgentWorkspaceError(409, "workspace_active", "Cancel active candidates before cleanup.")
            if state.get("cleanup", {}).get("status") == "completed":
                return self._public_state(state)
            for candidate in state.get("candidates", []):
                worktree = Path(str(candidate.get("worktree")))
                git_dir = Path(str(candidate.get("git_dir")))
                self._assert_managed_path(worktree)
                self._assert_managed_path(git_dir)
                self._remove_worktree(git_dir, worktree, tolerate_errors=False)
                candidate["worktree_removed"] = True
                candidate["git_dir_removed"] = True
            state["cleanup"] = {"status": "completed", "completed_at": utc_now()}
            if state.get("status") != "promoted":
                state["status"] = "cleaned"
            state["updated_at"] = utc_now()
            self._append_event_locked(state, "workspace.cleaned", {})
            return self._public_state(state)

    def promote(
        self,
        workspace_id: str,
        *,
        candidate_id: Optional[str],
        approved: bool,
        approved_by: Optional[str],
    ) -> Dict[str, Any]:
        if approved is not True or not str(approved_by or "").strip():
            raise AgentWorkspaceError(
                403,
                "human_approval_required",
                "Promotion requires approved=true and a non-empty approved_by identity.",
            )
        with self._lock:
            state = self._load_state(workspace_id)
            selected_id = str(candidate_id or state.get("selected_candidate_id") or "")
            if not selected_id:
                raise AgentWorkspaceError(422, "candidate_required", "Select a candidate before promotion.")
            if state.get("status") == "promoted":
                if state.get("promotion", {}).get("candidate_id") == selected_id:
                    return self._public_state(state)
                raise AgentWorkspaceError(409, "workspace_already_promoted", "A different candidate was already promoted.")
            if state.get("status") == "promoting":
                raise AgentWorkspaceError(409, "promotion_in_progress", "Promotion is already in progress.")
            candidate = self._candidate(state, selected_id)
            if candidate.get("status") != "completed":
                raise AgentWorkspaceError(409, "candidate_not_reviewable", "Only completed candidates can be promoted.")
            if state.get("cancel_requested"):
                raise AgentWorkspaceError(409, "workspace_cancelled", "Cancelled workspace sets cannot be promoted.")

            self._refresh_candidate_locked(state, candidate)
            evidence = candidate.get("evidence") or {}
            comparison = candidate.get("comparison") or {}
            tests = comparison.get("tests") or {}
            quality_gate = comparison.get("quality_gate") or {}
            risks = comparison.get("risk") or {}
            if tests.get("status") != "passed":
                raise AgentWorkspaceError(409, "tests_not_passed", "All configured candidate validations must pass.")
            if quality_gate.get("required") and quality_gate.get("status") != "passed":
                raise AgentWorkspaceError(409, "quality_gate_not_passed", "The managed repository quality gate must pass.")
            if risks.get("blocking"):
                raise AgentWorkspaceError(409, "risk_blocked", "Candidate risk evidence contains a blocking finding.")
            changed_files = comparison.get("changed_files") or []
            if not changed_files:
                raise AgentWorkspaceError(409, "empty_diff", "The selected candidate has no changes to promote.")
            patch_path = self._patch_path(workspace_id, selected_id)
            if not comparison.get("patch_available") or not patch_path.is_file():
                raise AgentWorkspaceError(409, "diff_unavailable", "A complete non-secret candidate diff is required.")
            if not evidence.get("ready_for_review"):
                raise AgentWorkspaceError(409, "evidence_incomplete", "Candidate evidence is incomplete.")
            patch = patch_path.read_bytes()
            if hashlib.sha256(patch).hexdigest() != comparison.get("patch_sha256"):
                raise AgentWorkspaceError(409, "diff_changed", "Candidate diff changed after evidence was recorded.")

            repo = inspect_git_repository(
                str(state.get("repo_root")),
                repo_access=state.get("repo_access"),
            )
            if repo["base_sha"] != state.get("base_sha"):
                raise AgentWorkspaceError(409, "base_drift", "Source HEAD no longer matches the workspace base SHA.")
            if not repo["clean"]:
                raise AgentWorkspaceError(409, "source_not_clean", "Source repository changed after workspace creation.")
            apply_check = _run_command(
                ["git", "-C", repo["repo_root"], "apply", "--check", "--binary", "-"],
                operation="Check candidate conflicts",
                input_bytes=patch,
                check=False,
            )
            if apply_check.returncode != 0:
                candidate["comparison"]["conflicts"] = {
                    "status": "conflict",
                    "checked_at": utc_now(),
                }
                self._write_state(state)
                raise AgentWorkspaceError(409, "candidate_conflict", "Candidate diff no longer applies cleanly to the source.")
            candidate["comparison"]["conflicts"] = {"status": "clear", "checked_at": utc_now()}
            candidate["evidence"]["conflicts_validated"] = True
            candidate["evidence"]["human_approval_validated"] = True
            candidate["evidence"]["promotion_validated_at"] = utc_now()

            approval = {
                "status": "approved",
                "approved": True,
                "approved_by": _redact_text(str(approved_by).strip())[:200],
                "approved_at": utc_now(),
                "candidate_id": selected_id,
                "patch_sha256": comparison.get("patch_sha256"),
                "promoted_at": None,
            }
            state["selected_candidate_id"] = selected_id
            state["promotion"] = approval
            state["status"] = "promoting"
            state["updated_at"] = utc_now()
            self._append_event_locked(state, "promotion.approved", {}, candidate_id=selected_id)

            apply_result = _run_command(
                ["git", "-C", repo["repo_root"], "apply", "--binary", "-"],
                operation="Apply approved candidate",
                input_bytes=patch,
                check=False,
            )
            if apply_result.returncode != 0:
                state["status"] = "promotion_failed"
                state["promotion"]["status"] = "failed"
                state["updated_at"] = utc_now()
                self._append_event_locked(state, "promotion.failed", {}, candidate_id=selected_id)
                raise AgentWorkspaceError(409, "promotion_apply_failed", "Approved candidate could not be applied atomically.")

            promoted_files = _git_changed_files(repo["repo_root"])
            if promoted_files != sorted(changed_files):
                reverse = _run_command(
                    ["git", "-C", repo["repo_root"], "apply", "--reverse", "--binary", "-"],
                    operation="Roll back incomplete promotion",
                    input_bytes=patch,
                    check=False,
                )
                state["status"] = "promotion_failed"
                state["promotion"]["status"] = "failed"
                state["updated_at"] = utc_now()
                self._append_event_locked(state, "promotion.failed", {}, candidate_id=selected_id)
                if reverse.returncode != 0:
                    raise AgentWorkspaceError(500, "promotion_verification_failed", "Promotion verification failed; inspect the source repository.")
                raise AgentWorkspaceError(409, "promotion_verification_failed", "Promoted changed files did not match candidate evidence.")

            state["status"] = "promoted"
            state["promotion"]["status"] = "promoted"
            state["promotion"]["promoted_at"] = utc_now()
            state["updated_at"] = utc_now()
            self._append_event_locked(
                state,
                "promotion.completed",
                {"changed_files": promoted_files, "patch_sha256": comparison.get("patch_sha256")},
                candidate_id=selected_id,
            )
            return self._public_state(state)

    def wait(self, workspace_id: str, *, timeout: float = 10.0) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.get(workspace_id)
            if state.get("status") not in {"running", "revising", "cancelling", "creating"}:
                return state
            time.sleep(0.02)
        raise TimeoutError(f"Workspace {workspace_id} did not reach a stable state")

    def _validate_agents(self, agent_ids: Sequence[str]) -> List[str]:
        normalized: List[str] = []
        for raw_agent_id in agent_ids or []:
            agent_id = normalize_agent_id(str(raw_agent_id).strip()) or str(raw_agent_id).strip()
            if agent_id not in LOCAL_CLI_AGENT_IDS:
                raise AgentWorkspaceError(422, "unknown_agent", f"Unknown local agent: {agent_id}")
            if agent_id not in normalized:
                normalized.append(agent_id)
        if not normalized:
            raise AgentWorkspaceError(422, "agent_ids_required", "At least one agent_id is required.")
        if len(normalized) > MAX_AGENTS:
            raise AgentWorkspaceError(422, "too_many_agents", f"At most {MAX_AGENTS} agents can run in one workspace set.")
        health = self._agent_health_provider(force=False)
        unavailable = [
            agent_id
            for agent_id in normalized
            if not bool((health.get(agent_id) or {}).get("available"))
        ]
        if unavailable:
            raise AgentWorkspaceError(
                409,
                "agents_unavailable",
                "Unavailable local agents: " + ", ".join(unavailable),
            )
        return normalized

    def _submit_candidate(self, workspace_id: str, candidate_id: str, prompt: str) -> None:
        key = f"{workspace_id}:{candidate_id}"
        guarded_prompt = (
            "Work only inside the assigned isolated git worktree. Do not commit, create branches, "
            "change remotes, or write credentials. Leave all candidate changes uncommitted for review.\n\n"
            + prompt
        )
        future = self._executor.submit(self._execute_candidate, workspace_id, candidate_id, guarded_prompt)
        with self._lock:
            self._futures[key] = future
        future.add_done_callback(lambda _future, future_key=key: self._drop_future(future_key))

    def _drop_future(self, key: str) -> None:
        with self._lock:
            self._futures.pop(key, None)

    def _execute_candidate(self, workspace_id: str, candidate_id: str, prompt: str) -> None:
        with self._lock:
            state = self._load_state(workspace_id)
            candidate = self._candidate(state, candidate_id)
            if state.get("cancel_requested") or candidate.get("status") == "cancelled":
                candidate["status"] = "cancelled"
                candidate["completed_at"] = utc_now()
                self._finalize_workspace_status_locked(state)
                return
            candidate["status"] = "running"
            candidate["started_at"] = utc_now()
            state["status"] = "revising" if int(candidate.get("attempt") or 1) > 1 else "running"
            state["updated_at"] = utc_now()
            self._append_event_locked(
                state,
                "candidate.started",
                {"agent_id": candidate["agent_id"], "attempt": candidate["attempt"]},
                candidate_id=candidate_id,
            )
            agent_id = str(candidate["agent_id"])
            worktree = str(candidate["worktree"])
            timeout = float(state["task_timeout_seconds"])
            session_id = str(candidate["session_id"])
        started = time.monotonic()
        try:
            result = dict(self._agent_runner(agent_id, prompt, worktree, timeout, session_id) or {})
        except Exception:
            result = {"success": False, "error_code": "runner_exception"}
        elapsed = max(0.0, time.monotonic() - started)
        output_text = str(result.get("output") or result.get("text") or "")

        with self._lock:
            state = self._load_state(workspace_id)
            candidate = self._candidate(state, candidate_id)
            if state.get("cancel_requested") or candidate.get("status") == "cancelling":
                candidate["status"] = "cancelled"
                candidate["completed_at"] = utc_now()
                candidate["run"] = {
                    "success": False,
                    "error_code": "cancelled",
                    "elapsed_seconds": round(elapsed, 3),
                    "output_bytes": len(output_text.encode("utf-8")),
                    "output_sha256": _sha256_text(output_text) if output_text else None,
                    "transcript_persisted": False,
                }
                self._append_event_locked(
                    state,
                    "candidate.cancelled",
                    {"elapsed_seconds": round(elapsed, 3)},
                    candidate_id=candidate_id,
                )
                self._finalize_workspace_status_locked(state)
                return

            success = bool(result.get("success"))
            candidate["run"] = {
                "success": success,
                "error_code": _safe_error_code(result.get("error_code")) if not success else None,
                "elapsed_seconds": round(elapsed, 3),
                "output_bytes": len(output_text.encode("utf-8")),
                "output_sha256": _sha256_text(output_text) if output_text else None,
                "provider": _safe_metadata_value(result.get("provider")),
                "model": _safe_metadata_value(result.get("model")),
                "usage": _safe_usage(result.get("usage")),
                "tool_calls": _safe_tool_calls(result.get("tool_calls")),
                "evidence_links": _safe_evidence_links(result.get("evidence_links")),
                "transcript_persisted": False,
            }
            self._append_event_locked(
                state,
                "candidate.output.observed",
                {
                    "stream": "agent_result",
                    "byte_count": candidate["run"]["output_bytes"],
                    "sha256": candidate["run"]["output_sha256"],
                    "transcript_persisted": False,
                },
                candidate_id=candidate_id,
            )
            if candidate["run"]["tool_calls"]:
                self._append_event_locked(
                    state,
                    "candidate.tool_calls.observed",
                    {
                        "count": len(candidate["run"]["tool_calls"]),
                        "tools": candidate["run"]["tool_calls"],
                        "arguments_persisted": False,
                    },
                    candidate_id=candidate_id,
                )
            try:
                self._refresh_candidate_locked(state, candidate)
            except AgentWorkspaceError as exc:
                candidate["status"] = "blocked" if exc.code == "credential_material_detected" else "failed"
                candidate["run"]["error_code"] = exc.code
            else:
                candidate["status"] = "completed" if success else "failed"
            candidate["completed_at"] = utc_now()
            state["updated_at"] = utc_now()
            self._append_event_locked(
                state,
                "candidate.completed" if candidate["status"] == "completed" else "candidate.failed",
                {
                    "status": candidate["status"],
                    "elapsed_seconds": round(elapsed, 3),
                    "changed_file_count": len((candidate.get("comparison") or {}).get("changed_files") or []),
                    "tests_status": ((candidate.get("comparison") or {}).get("tests") or {}).get("status"),
                },
                candidate_id=candidate_id,
            )
            self._finalize_workspace_status_locked(state)

    def _refresh_candidate_locked(self, state: Dict[str, Any], candidate: Dict[str, Any]) -> None:
        worktree = Path(str(candidate.get("worktree"))).resolve()
        self._assert_managed_path(worktree)
        if not worktree.is_dir():
            raise AgentWorkspaceError(409, "candidate_worktree_missing", "Candidate worktree is missing.")
        raw_changed_files = _candidate_changed_files(str(worktree), str(state["base_sha"]))
        unsafe_paths = [path for path in raw_changed_files if not _safe_relative_path(path)]
        if unsafe_paths:
            candidate["comparison"] = _empty_comparison()
            candidate["comparison"]["risk"] = {
                "level": "blocked",
                "blocking": True,
                "findings": [{"id": "unsafe_changed_path", "severity": "blocked"}],
            }
            raise AgentWorkspaceError(409, "unsafe_changed_path", "Candidate contains an unsafe changed path.")
        if self._candidate_contains_secret(worktree, raw_changed_files, str(state["base_sha"])):
            candidate["comparison"] = _empty_comparison()
            candidate["comparison"].update(
                {
                    "changed_files": sorted(raw_changed_files),
                    "risk": {
                        "level": "blocked",
                        "blocking": True,
                        "findings": [{"id": "credential_material_detected", "severity": "blocked"}],
                    },
                }
            )
            candidate["evidence"] = {
                **_empty_evidence(),
                "blocking_reasons": ["credential_material_detected"],
            }
            self._remove_worktree(Path(str(candidate["git_dir"])), worktree, tolerate_errors=True)
            candidate["worktree_removed"] = True
            candidate["git_dir_removed"] = True
            self._append_event_locked(
                state,
                "candidate.blocked",
                {"reason": "credential_material_detected"},
                candidate_id=str(candidate["candidate_id"]),
            )
            raise AgentWorkspaceError(409, "credential_material_detected", "Candidate contained credential-like material and was quarantined.")

        tests = self._run_validations(state, candidate)
        _run_command(
            ["git", "-C", str(worktree), "add", "-A", "--"],
            operation="Stage candidate comparison",
        )
        diff_result = _run_command(
            [
                "git",
                "-C",
                str(worktree),
                "-c",
                "core.quotePath=false",
                "diff",
                "--cached",
                "--binary",
                "--full-index",
                "--no-ext-diff",
                str(state["base_sha"]),
                "--",
            ],
            operation="Build candidate diff",
        )
        patch_text = diff_result.stdout
        if _contains_secret(patch_text):
            self._remove_worktree(Path(str(candidate["git_dir"])), worktree, tolerate_errors=True)
            candidate["worktree_removed"] = True
            candidate["git_dir_removed"] = True
            raise AgentWorkspaceError(409, "credential_material_detected", "Candidate diff contained credential-like material and was quarantined.")
        changed_files = _git_cached_changed_files(str(worktree), str(state["base_sha"]))
        patch_bytes = patch_text.encode("utf-8")
        patch_path = self._patch_path(str(state["workspace_id"]), str(candidate["candidate_id"]))
        _atomic_write_bytes(patch_path, patch_bytes, mode=0o600)
        stats = _git_diff_stats(str(worktree), str(state["base_sha"]))
        risk = _risk_summary(changed_files, stats)
        quality_gate = self._run_quality_gate(state, candidate)
        patch_sha = hashlib.sha256(patch_bytes).hexdigest()
        head_sha = _run_command(
            ["git", "-C", str(worktree), "rev-parse", "HEAD"],
            operation="Resolve candidate head",
        ).stdout.strip()
        review_anchor = {
            "base_sha": str(state["base_sha"]),
            "head_sha": head_sha,
            "patch_sha256": patch_sha,
        }
        candidate["comparison"] = {
            "changed_files": changed_files,
            "diff": {
                "files_changed": len(changed_files),
                "insertions": stats["insertions"],
                "deletions": stats["deletions"],
                "binary_files": stats["binary_files"],
            },
            "patch_available": bool(patch_bytes),
            "patch_sha256": patch_sha,
            "head_sha": head_sha,
            "review_anchor": review_anchor,
            "review_anchor_sha256": _sha256_json(review_anchor),
            "tests": tests,
            "quality_gate": quality_gate,
            "risk": risk,
            "conflicts": {"status": "not_checked", "checked_at": None},
        }
        evidence_payload = {
            "workspace_id": state["workspace_id"],
            "candidate_id": candidate["candidate_id"],
            "base_sha": state["base_sha"],
            "changed_files": changed_files,
            "patch_sha256": patch_sha,
            "tests_status": tests["status"],
            "quality_gate_status": quality_gate["status"],
            "quality_gate_evidence_hash": quality_gate.get("evidence_hash"),
            "risk_level": risk["level"],
        }
        blocking_reasons: List[str] = []
        if not changed_files:
            blocking_reasons.append("empty_diff")
        if tests["status"] != "passed":
            blocking_reasons.append("tests_not_passed")
        if quality_gate["required"] and quality_gate["status"] != "passed":
            blocking_reasons.append("quality_gate_not_passed")
        if risk["blocking"]:
            blocking_reasons.append("risk_blocked")
        candidate["evidence"] = {
            "schema_version": "agent-workspace-evidence/1.0",
            "generated_at": utc_now(),
            "base_sha": state["base_sha"],
            "patch_sha256": patch_sha,
            "evidence_sha256": _sha256_json(evidence_payload),
            "changed_files_validated": True,
            "diff_validated": bool(patch_bytes),
            "tests_validated": tests["status"] == "passed",
            "quality_gate_validated": not quality_gate["required"] or quality_gate["status"] == "passed",
            "risk_validated": not risk["blocking"],
            "conflicts_validated": False,
            "human_approval_required": True,
            "ready_for_review": not blocking_reasons,
            "blocking_reasons": blocking_reasons,
            "transcript_persisted": False,
        }
        self._append_event_locked(
            state,
            "candidate.evidence.updated",
            {
                "evidence_sha256": candidate["evidence"]["evidence_sha256"],
                "patch_sha256": patch_sha,
                "changed_file_count": len(changed_files),
                "tests_status": tests["status"],
                "quality_gate_status": quality_gate["status"],
                "risk_level": risk["level"],
            },
            candidate_id=str(candidate["candidate_id"]),
        )

    def _run_quality_gate(self, state: Mapping[str, Any], candidate: Mapping[str, Any]) -> Dict[str, Any]:
        workflow = str(state.get("workflow") or "").strip()
        if workflow not in QUALITY_GATE_WORKFLOWS:
            return {
                "required": False,
                "status": "not_requested",
                "gate_verdict": None,
                "findings": [],
                "evidence_hash": None,
                "pr_ready_summary": None,
            }
        if self._quality_gate_runner is None:
            return {
                "required": True,
                "status": "unavailable",
                "gate_verdict": None,
                "findings": [],
                "evidence_hash": None,
                "pr_ready_summary": None,
            }
        try:
            worktree = str(candidate["worktree"])
            staged = _run_command(
                ["git", "-C", worktree, "diff", "--cached", "--quiet", "--exit-code"],
                operation="Inspect candidate gate snapshot",
                check=False,
            )
            if staged.returncode == 1:
                _run_command(
                    [
                        "git",
                        "-C",
                        worktree,
                        "-c",
                        "user.name=Across Workspace Gate",
                        "-c",
                        "user.email=workspace-gate@across.invalid",
                        "commit",
                        "--no-gpg-sign",
                        "--no-verify",
                        "-m",
                        "Across workspace gate snapshot",
                    ],
                    operation="Create isolated candidate gate snapshot",
                )
            elif staged.returncode != 0:
                raise AgentWorkspaceError(409, "gate_snapshot_failed", "Candidate gate snapshot could not be inspected.")
            raw = dict(
                self._quality_gate_runner(
                    worktree,
                    str(state["base_sha"]),
                    float(state.get("test_timeout_seconds") or DEFAULT_TEST_TIMEOUT_SECONDS),
                    dict(state.get("quality_gate_options") or {}),
                )
                or {}
            )
        except Exception:
            return {
                "required": True,
                "status": "failed",
                "gate_verdict": None,
                "findings": [],
                "evidence_hash": None,
                "pr_ready_summary": None,
            }
        return _normalize_quality_gate(raw)

    def _run_validations(self, state: Mapping[str, Any], candidate: Mapping[str, Any]) -> Dict[str, Any]:
        worktree = str(candidate["worktree"])
        commands = list(state.get("validation_commands") or [])
        validation_timeout = float(state.get("test_timeout_seconds") or DEFAULT_TEST_TIMEOUT_SECONDS)
        results: List[Dict[str, Any]] = []
        for index, command in enumerate(commands):
            started = time.monotonic()
            result = _run_command(
                command,
                cwd=worktree,
                operation="Run candidate validation",
                timeout=validation_timeout,
                # Test runners can remain silent while doing useful work. Their
                # configured total timeout is the authoritative bound; the short
                # idle timeout remains reserved for Git and repository probes.
                idle_timeout=validation_timeout,
                check=False,
            )
            results.append(
                {
                    "index": index,
                    "command": command,
                    "status": "passed" if result.returncode == 0 else "failed",
                    "exit_code": result.returncode,
                    "elapsed_seconds": round(max(0.0, time.monotonic() - started), 3),
                    "stdout_bytes": len(result.stdout.encode("utf-8", errors="replace")),
                    "stderr_bytes": len(result.stderr.encode("utf-8", errors="replace")),
                    "output_persisted": False,
                }
            )
            if result.returncode != 0:
                break
        status = "passed" if results and all(item["status"] == "passed" for item in results) else "failed"
        return {
            "status": status,
            "configured_count": len(commands),
            "completed_count": len(results),
            "results": results,
        }

    def _candidate_contains_secret(self, worktree: Path, changed_files: Iterable[str], base_sha: str) -> bool:
        for relative in changed_files:
            path = worktree / relative
            if path.is_symlink():
                target = os.readlink(path)
                return True
            resolved = path.resolve()
            if not _is_relative_to(resolved, worktree) or not resolved.exists() or resolved.is_dir():
                continue
            try:
                data = resolved.read_bytes()
            except OSError:
                continue
            if len(data) > 4 * 1024 * 1024 or b"\x00" in data[:8192]:
                continue
            if _contains_secret(data.decode("utf-8", errors="ignore")):
                return True
        return _new_commit_blobs_contain_secret(str(worktree), base_sha)

    def _finalize_workspace_status_locked(self, state: Dict[str, Any]) -> None:
        statuses = [str(candidate.get("status")) for candidate in state.get("candidates", [])]
        if any(status in ACTIVE_CANDIDATE_STATUSES for status in statuses):
            self._write_state(state)
            return
        previous = state.get("status")
        if state.get("cancel_requested"):
            state["status"] = "cancelled"
        elif any(status == "completed" for status in statuses):
            state["status"] = "review_ready"
        else:
            state["status"] = "failed"
        state["updated_at"] = utc_now()
        if previous != state["status"]:
            self._append_event_locked(state, f"workspace.{state['status']}", {})
        else:
            self._write_state(state)

    def _recover_durable_states(self) -> None:
        for state in self._iter_states():
            if state.get("status") == "promoting":
                self._recover_promotion(state)
                continue
            if state.get("status") not in ACTIVE_WORKSPACE_STATUSES:
                continue
            for candidate in state.get("candidates", []):
                if candidate.get("status") in ACTIVE_CANDIDATE_STATUSES:
                    candidate["status"] = "interrupted"
                    candidate["completed_at"] = utc_now()
                    candidate["run"] = {
                        "success": False,
                        "error_code": "backend_restarted",
                        "transcript_persisted": False,
                    }
            state["status"] = "interrupted"
            state["updated_at"] = utc_now()
            with self._lock:
                self._append_event_locked(state, "workspace.recovered_interrupted", {})

    def _recover_promotion(self, state: Dict[str, Any]) -> None:
        promotion = state.get("promotion") or {}
        candidate_id = str(promotion.get("candidate_id") or "")
        try:
            candidate = self._candidate(state, candidate_id)
            expected_files = sorted((candidate.get("comparison") or {}).get("changed_files") or [])
            repo = inspect_git_repository(
                str(state.get("repo_root")),
                repo_access=state.get("repo_access"),
            )
            actual_files = _git_changed_files(repo["repo_root"])
            patch_path = self._patch_path(str(state["workspace_id"]), candidate_id)
            reverse_check = None
            if patch_path.is_file():
                reverse_check = _run_command(
                    ["git", "-C", repo["repo_root"], "apply", "--reverse", "--check", "--binary", "-"],
                    operation="Recover promotion state",
                    input_bytes=patch_path.read_bytes(),
                    check=False,
                )
            if (
                repo["base_sha"] == state.get("base_sha")
                and actual_files == expected_files
                and actual_files
                and reverse_check is not None
                and reverse_check.returncode == 0
            ):
                state["status"] = "promoted"
                promotion["status"] = "promoted"
                promotion["promoted_at"] = utc_now()
                event_type = "promotion.recovered_completed"
            else:
                state["status"] = "promotion_interrupted"
                promotion["status"] = "interrupted"
                event_type = "promotion.recovered_interrupted"
        except Exception:
            state["status"] = "promotion_interrupted"
            promotion["status"] = "interrupted"
            event_type = "promotion.recovered_interrupted"
        state["promotion"] = promotion
        state["updated_at"] = utc_now()
        with self._lock:
            self._append_event_locked(state, event_type, {}, candidate_id=candidate_id or None)

    def _find_by_idempotency_hash(self, digest: str) -> Optional[Dict[str, Any]]:
        for state in self._iter_states():
            if state.get("idempotency_hash") == digest:
                return state
        return None

    def _iter_states(self) -> List[Dict[str, Any]]:
        states: List[Dict[str, Any]] = []
        if not self.root.exists():
            return states
        for state_path in self.root.glob("aws-*/state.json"):
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(state, dict) and state.get("workspace_id"):
                states.append(state)
        return states

    def _load_state(self, workspace_id: str) -> Dict[str, Any]:
        _validate_id(workspace_id, "workspace_id")
        path = self._state_path(workspace_id)
        if not path.is_file():
            raise AgentWorkspaceError(404, "workspace_not_found", "Agent workspace set was not found.")
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AgentWorkspaceError(500, "workspace_state_invalid", "Agent workspace state is unreadable.") from exc
        if state.get("workspace_id") != workspace_id:
            raise AgentWorkspaceError(500, "workspace_state_invalid", "Agent workspace state identity is invalid.")
        return state

    def _write_state(self, state: Mapping[str, Any]) -> None:
        workspace_id = str(state.get("workspace_id") or "")
        _validate_id(workspace_id, "workspace_id")
        payload = _sanitize_for_persistence(dict(state))
        # Internal integrity values are hashes, not user content, and remain durable.
        payload["request_fingerprint"] = state.get("request_fingerprint")
        payload["idempotency_hash"] = state.get("idempotency_hash")
        _atomic_write_bytes(
            self._state_path(workspace_id),
            (json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("utf-8"),
            mode=0o600,
        )

    def _append_event_locked(
        self,
        state: Dict[str, Any],
        event_type: str,
        data: Mapping[str, Any],
        *,
        candidate_id: Optional[str] = None,
    ) -> None:
        sequence = max(
            int(state.get("event_sequence") or 0),
            self._last_event_sequence(str(state["workspace_id"])),
        ) + 1
        state["event_sequence"] = sequence
        state["updated_at"] = utc_now()
        event = {
            "schema_version": EVENT_SCHEMA_VERSION,
            "sequence": sequence,
            "timestamp": utc_now(),
            "type": event_type,
            "workspace_id": state["workspace_id"],
            "candidate_id": candidate_id,
            "data": _sanitize_for_persistence(dict(data)),
        }
        events_path = self._events_path(str(state["workspace_id"]))
        events_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(events_path, 0o600)
        self._write_state(state)

    def _last_event_sequence(self, workspace_id: str) -> int:
        path = self._events_path(workspace_id)
        if not path.is_file():
            return 0
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return 0
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                sequence = json.loads(line).get("sequence")
            except (AttributeError, json.JSONDecodeError):
                continue
            if isinstance(sequence, int):
                return sequence
        return 0

    def _public_state(self, state: Mapping[str, Any]) -> Dict[str, Any]:
        payload = _sanitize_for_persistence(dict(state))
        payload.pop("request_fingerprint", None)
        payload.pop("idempotency_hash", None)
        payload.pop("quality_gate_options", None)
        payload["security"] = {
            "prompt_persisted": False,
            "agent_transcript_persisted": False,
            "credentials_allowed": False,
            "event_payloads_redacted": True,
        }
        for candidate in payload.get("candidates", []):
            candidate.pop("session_id", None)
            candidate.pop("worktree", None)
            candidate.pop("git_dir", None)
        return payload

    def _candidate(self, state: Mapping[str, Any], candidate_id: str) -> Dict[str, Any]:
        _validate_id(candidate_id, "candidate_id")
        for candidate in state.get("candidates", []):
            if candidate.get("candidate_id") == candidate_id:
                return candidate
        raise AgentWorkspaceError(404, "candidate_not_found", "Candidate was not found in this workspace set.")

    def _ensure_managed_root(self) -> None:
        expected = agent_workspace_root().resolve()
        if self.root != expected and not _is_relative_to(self.root, expected):
            raise AgentWorkspaceError(500, "unsafe_workspace_root", "Managed workspace root escaped the Across data directory.")
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

    def _assert_managed_path(self, path: Path) -> None:
        if not _is_relative_to(path.resolve(), self.root):
            raise AgentWorkspaceError(422, "unsafe_workspace_path", "Managed workspace path escaped its root.")

    def _workspace_dir(self, workspace_id: str) -> Path:
        _validate_id(workspace_id, "workspace_id")
        path = (self.root / workspace_id).resolve()
        self._assert_managed_path(path)
        return path

    def _state_path(self, workspace_id: str) -> Path:
        return self._workspace_dir(workspace_id) / "state.json"

    def _events_path(self, workspace_id: str) -> Path:
        return self._workspace_dir(workspace_id) / "events.jsonl"

    def _patch_path(self, workspace_id: str, candidate_id: str) -> Path:
        _validate_id(candidate_id, "candidate_id")
        return self._workspace_dir(workspace_id) / f"{candidate_id}.patch"

    def _remove_worktree(self, git_dir: Path, worktree: Path, *, tolerate_errors: bool) -> None:
        self._assert_managed_path(worktree)
        self._assert_managed_path(git_dir)
        result = _run_command(
            ["git", "--git-dir", str(git_dir), "worktree", "remove", "--force", str(worktree)],
            operation="Remove isolated git worktree",
            check=False,
        )
        if result.returncode != 0 and not tolerate_errors:
            raise AgentWorkspaceError(409, "worktree_cleanup_failed", "Isolated git worktree could not be removed.")
        if worktree.exists():
            shutil.rmtree(worktree, ignore_errors=tolerate_errors)
        if git_dir.exists():
            shutil.rmtree(git_dir, ignore_errors=tolerate_errors)

    @staticmethod
    def _unconfigured_runner(
        _agent_id: str,
        _prompt: str,
        _worktree: str,
        _timeout: float,
        _session_id: str,
    ) -> Mapping[str, Any]:
        return {"success": False, "error_code": "agent_runner_unconfigured"}


def _normalize_repo_access(value: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    mode = str(raw.get("mode") or "implicit").strip().lower()
    if mode not in {"implicit", "security_scoped"}:
        raise AgentWorkspaceError(
            422,
            "invalid_repo_access_mode",
            "repo_access.mode must be implicit or security_scoped.",
        )
    active = raw.get("security_scope_active") is True
    grant_id = str(raw.get("grant_id") or "").strip()
    if grant_id and not _SAFE_ID_RE.fullmatch(grant_id):
        raise AgentWorkspaceError(422, "invalid_repo_access_grant", "repo_access.grant_id is invalid.")
    unexpected = set(raw) - {
        "schema_version",
        "mode",
        "security_scope_active",
        "grant_id",
        "grant_id_sha256",
        "bookmark_persisted",
        "swift_lifetime_required",
    }
    if unexpected:
        raise AgentWorkspaceError(
            422,
            "invalid_repo_access_metadata",
            "repo_access contains unsupported fields; bookmark data must stay with Swift.",
        )
    digest = str(raw.get("grant_id_sha256") or "").strip().lower()
    if digest and not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise AgentWorkspaceError(422, "invalid_repo_access_grant", "repo_access grant digest is invalid.")
    return {
        "schema_version": "agent-workspace-repository-access/1.0",
        "mode": mode,
        "security_scope_active": active,
        "grant_id_sha256": _sha256_text(grant_id) if grant_id else (digest or None),
        "bookmark_persisted": False,
        "swift_lifetime_required": mode == "security_scoped",
    }


def _normalize_review_anchor(value: Mapping[str, Any]) -> Dict[str, str]:
    if not isinstance(value, Mapping):
        raise AgentWorkspaceError(422, "review_anchor_required", "A diff review anchor is required.")
    normalized: Dict[str, str] = {}
    for key in ("base_sha", "head_sha"):
        digest = str(value.get(key) or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{40,64}", digest):
            raise AgentWorkspaceError(422, "invalid_review_anchor", f"{key} must be a Git object ID.")
        normalized[key] = digest
    patch_digest = str(value.get("patch_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", patch_digest):
        raise AgentWorkspaceError(422, "invalid_review_anchor", "patch_sha256 must be a SHA-256 digest.")
    normalized["patch_sha256"] = patch_digest
    return normalized


def _normalize_line_review_comments(comments: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(comments, (list, tuple)) or not comments:
        raise AgentWorkspaceError(422, "line_review_comments_required", "At least one line review comment is required.")
    if len(comments) > MAX_LINE_REVIEW_COMMENTS:
        raise AgentWorkspaceError(422, "too_many_line_review_comments", "Too many line review comments were supplied.")
    normalized: List[Dict[str, Any]] = []
    total_length = 0
    for raw in comments:
        if not isinstance(raw, Mapping):
            raise AgentWorkspaceError(422, "invalid_line_review_comment", "Each line review comment must be an object.")
        path = str(raw.get("path") or "").strip()
        if not _safe_relative_path(path):
            raise AgentWorkspaceError(
                422,
                "invalid_review_path",
                "Line review paths must be safe repository-relative paths.",
            )
        side = str(raw.get("side") or "").strip().upper()
        if side not in {"LEFT", "RIGHT"}:
            raise AgentWorkspaceError(422, "invalid_review_side", "Line review side must be LEFT or RIGHT.")
        line = raw.get("line")
        start_line = raw.get("start_line", line)
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            raise AgentWorkspaceError(422, "invalid_review_line", "Line review line must be a positive integer.")
        if not isinstance(start_line, int) or isinstance(start_line, bool) or start_line < 1 or start_line > line:
            raise AgentWorkspaceError(
                422,
                "invalid_review_range",
                "start_line must be positive and no greater than line.",
            )
        body = str(raw.get("body") or raw.get("comment") or "")
        if not body.strip():
            raise AgentWorkspaceError(422, "line_review_body_required", "Each line review comment requires a body.")
        if len(body) > MAX_LINE_REVIEW_BODY_LENGTH:
            raise AgentWorkspaceError(
                422,
                "line_review_body_too_long",
                "A line review comment exceeds the bounded feedback limit.",
            )
        if _contains_secret(body):
            raise AgentWorkspaceError(
                422,
                "credential_in_review_comment",
                "Line review comments must not contain credential-like material.",
            )
        total_length += len(body)
        normalized.append({"path": path, "side": side, "start_line": start_line, "line": line, "body": body})
    if total_length > MAX_LINE_REVIEW_TOTAL_LENGTH:
        raise AgentWorkspaceError(422, "line_review_too_long", "The line review batch exceeds the bounded feedback limit.")
    return normalized


def _candidate_review_anchor(state: Mapping[str, Any], candidate: Mapping[str, Any]) -> Dict[str, str]:
    comparison = candidate.get("comparison") if isinstance(candidate.get("comparison"), Mapping) else {}
    return _normalize_review_anchor(
        {
            "base_sha": state.get("base_sha"),
            "head_sha": comparison.get("head_sha"),
            "patch_sha256": comparison.get("patch_sha256"),
        }
    )


def _validate_review_locations(patch_text: str, comments: Sequence[Mapping[str, Any]]) -> None:
    locations = _unified_diff_locations(patch_text)
    for comment in comments:
        key = (str(comment["path"]), str(comment["side"]))
        valid_lines = locations.get(key, set())
        requested = set(range(int(comment["start_line"]), int(comment["line"]) + 1))
        if not requested.issubset(valid_lines):
            raise AgentWorkspaceError(
                422,
                "review_location_not_in_diff",
                "A line review location is not present on the requested side of the anchored diff.",
            )


def _unified_diff_locations(patch_text: str) -> Dict[tuple[str, str], set[int]]:
    locations: Dict[tuple[str, str], set[int]] = {}
    old_path: Optional[str] = None
    new_path: Optional[str] = None
    old_line: Optional[int] = None
    new_line: Optional[int] = None
    in_hunk = False
    hunk_re = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            old_path = new_path = None
            old_line = new_line = None
            in_hunk = False
            continue
        if not in_hunk and line.startswith("--- "):
            old_path = _decode_diff_path(line[4:].split("\t", 1)[0], "a/")
            old_line = new_line = None
            continue
        if not in_hunk and line.startswith("+++ "):
            new_path = _decode_diff_path(line[4:].split("\t", 1)[0], "b/")
            continue
        match = hunk_re.match(line)
        if match:
            old_line, new_line = int(match.group(1)), int(match.group(2))
            in_hunk = True
            continue
        if old_line is None or new_line is None or line.startswith("\\ No newline"):
            continue
        prefix = line[:1]
        if prefix == "-":
            if old_path:
                locations.setdefault((old_path, "LEFT"), set()).add(old_line)
            old_line += 1
        elif prefix == "+":
            if new_path:
                locations.setdefault((new_path, "RIGHT"), set()).add(new_line)
            new_line += 1
        elif prefix == " ":
            if old_path:
                locations.setdefault((old_path, "LEFT"), set()).add(old_line)
            if new_path:
                locations.setdefault((new_path, "RIGHT"), set()).add(new_line)
            old_line += 1
            new_line += 1
    return locations


def _decode_diff_path(value: str, prefix: str) -> Optional[str]:
    text = value.strip()
    if text == "/dev/null":
        return None
    if text.startswith('"') and text.endswith('"'):
        try:
            text = str(ast.literal_eval(text))
        except (SyntaxError, ValueError):
            return None
    if text.startswith(prefix):
        text = text[len(prefix):]
    return text if _safe_relative_path(text) else None


def _normalize_validation_commands(commands: Optional[Sequence[Sequence[str]]]) -> List[List[str]]:
    source = commands or [["git", "diff", "--check"]]
    if len(source) > MAX_VALIDATION_COMMANDS:
        raise AgentWorkspaceError(422, "too_many_validation_commands", "Too many validation commands were requested.")
    normalized: List[List[str]] = []
    for command in source:
        if not isinstance(command, (list, tuple)) or not command:
            raise AgentWorkspaceError(422, "invalid_validation_command", "Validation commands must be non-empty argv arrays.")
        if len(command) > MAX_COMMAND_PARTS:
            raise AgentWorkspaceError(422, "invalid_validation_command", "Validation command has too many arguments.")
        parts = [str(part) for part in command]
        if any(not part or len(part) > MAX_COMMAND_PART_LENGTH or "\x00" in part for part in parts):
            raise AgentWorkspaceError(422, "invalid_validation_command", "Validation command contains an invalid argument.")
        joined = " ".join(parts)
        sensitive_flag = any(
            re.match(
                r"^--?(?:api[-_]?key|access[-_]?token|auth[-_]?token|password|passwd|secret|authorization|cookie)(?:=|$)",
                part,
                re.IGNORECASE,
            )
            for part in parts
        )
        if sensitive_flag or _contains_secret(joined):
            raise AgentWorkspaceError(422, "credential_in_validation_command", "Validation commands must not contain credentials.")
        normalized.append(parts)
    return normalized


def _normalize_quality_gate_options(
    *,
    ci_path: Optional[str],
    ci_wait_seconds: int,
    draft_pr: bool,
) -> Dict[str, Any]:
    try:
        wait_seconds = int(ci_wait_seconds)
    except (TypeError, ValueError) as exc:
        raise AgentWorkspaceError(422, "invalid_quality_gate_ci_wait", "quality_gate_ci_wait_seconds must be an integer.") from exc
    if wait_seconds < 0 or wait_seconds > 900:
        raise AgentWorkspaceError(422, "invalid_quality_gate_ci_wait", "quality_gate_ci_wait_seconds must be between 0 and 900.")
    normalized: Dict[str, Any] = {
        "ci_path": None,
        "ci_sha256": None,
        "ci_wait_seconds": wait_seconds,
        "draft_pr": bool(draft_pr),
    }
    if not str(ci_path or "").strip():
        return normalized
    supplied = Path(str(ci_path)).expanduser()
    if not supplied.is_absolute() or supplied.is_symlink():
        raise AgentWorkspaceError(422, "invalid_quality_gate_ci_path", "quality_gate_ci_path must be an absolute regular file.")
    resolved = supplied.resolve()
    if not resolved.is_file() or resolved.stat().st_size > 1_000_000:
        raise AgentWorkspaceError(422, "invalid_quality_gate_ci_path", "quality_gate_ci_path must be an existing bounded file.")
    try:
        content = resolved.read_text(encoding="utf-8")
        parsed = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AgentWorkspaceError(422, "invalid_quality_gate_ci_snapshot", "quality_gate_ci_path must contain valid JSON.") from exc
    if not isinstance(parsed, (dict, list)) or _contains_secret(content):
        raise AgentWorkspaceError(422, "invalid_quality_gate_ci_snapshot", "quality_gate_ci_path contains an invalid or sensitive snapshot.")
    normalized["ci_path"] = str(resolved)
    normalized["ci_sha256"] = _sha256_text(content)
    return normalized


def _bounded_timeout(value: Any, name: str, *, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AgentWorkspaceError(422, f"invalid_{name}", f"{name} must be numeric.") from exc
    if number < 1.0 or number > maximum:
        raise AgentWorkspaceError(422, f"invalid_{name}", f"{name} must be between 1 and {maximum:g} seconds.")
    return number


def _run_command(
    argv: Sequence[str],
    *,
    operation: str,
    cwd: Optional[str] = None,
    timeout: float = 30.0,
    idle_timeout: Optional[float] = None,
    input_bytes: Optional[bytes] = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    total_timeout = max(0.05, float(timeout))
    idle_limit = max(
        0.05,
        min(
            total_timeout,
            float(idle_timeout) if idle_timeout is not None else DEFAULT_COMMAND_IDLE_TIMEOUT_SECONDS,
        ),
    )
    process: Optional[subprocess.Popen[str]] = None
    try:
        process = subprocess.Popen(
            [str(part) for part in argv],
            cwd=cwd,
            stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            start_new_session=(os.name != "nt"),
            env=_sanitized_subprocess_env(),
        )
        input_text = input_bytes.decode("utf-8", errors="strict") if input_bytes is not None else None
        total_deadline = time.monotonic() + total_timeout
        activity_deadline = time.monotonic() + idle_limit
        observed_size = 0
        first_communicate = True
        while True:
            now = time.monotonic()
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                break
            if now >= total_deadline:
                _terminate_command_process(process)
                raise AgentWorkspaceError(408, "command_total_timeout", f"{operation} exceeded its bounded total timeout.")
            if now >= activity_deadline:
                _terminate_command_process(process)
                raise AgentWorkspaceError(408, "command_idle_timeout", f"{operation} made no observable progress before its idle timeout.")
            try:
                stdout, stderr = process.communicate(
                    input=input_text if first_communicate else None,
                    timeout=max(0.01, min(0.25, total_deadline - now, activity_deadline - now)),
                )
                break
            except subprocess.TimeoutExpired as exc:
                first_communicate = False
                partial_stdout = _timeout_output_text(exc.output)
                partial_stderr = _timeout_output_text(exc.stderr)
                current_size = len(partial_stdout.encode("utf-8")) + len(partial_stderr.encode("utf-8"))
                if current_size > observed_size:
                    observed_size = current_size
                    activity_deadline = time.monotonic() + idle_limit
        result = subprocess.CompletedProcess(
            args=[str(part) for part in argv],
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    except AgentWorkspaceError:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise AgentWorkspaceError(500, "command_failed", f"{operation} could not start.") from exc
    if _permission_failure(result.stderr):
        raise AgentWorkspaceError(
            403,
            "repository_access_denied",
            f"{operation} was denied by the operating system. Activate folder access and retry.",
        )
    if check and result.returncode != 0:
        raise AgentWorkspaceError(409, "git_operation_failed", f"{operation} failed.")
    return result


def _terminate_command_process(process: subprocess.Popen[str]) -> None:
    try:
        if os.name != "nt":
            os.killpg(os.getpgid(process.pid), 9)
        else:
            process.kill()
    except (OSError, ProcessLookupError):
        pass
    try:
        process.communicate(timeout=1.0)
    except Exception:
        pass


def _timeout_output_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _permission_failure(stderr: Any) -> bool:
    text = str(stderr or "").lower()
    return any(
        marker in text
        for marker in (
            "operation not permitted",
            "permission denied",
            "access is denied",
            "not authorized to access",
        )
    )


def _sanitized_subprocess_env() -> Dict[str, str]:
    blocked = ("TOKEN", "SECRET", "PASSWORD", "PASSWD", "API_KEY", "AUTHORIZATION", "COOKIE")
    return {
        key: value
        for key, value in os.environ.items()
        if not any(part in key.upper() for part in blocked)
    }


def _git_changed_files(repo_root: str) -> List[str]:
    result = _run_command(
        ["git", "-C", repo_root, "status", "--porcelain=v1", "--untracked-files=all", "-z"],
        operation="Inspect changed files",
    )
    files: List[str] = []
    entries = result.stdout.split("\x00")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        status = entry[:2]
        path = entry[3:]
        if status and (status[0] in {"R", "C"} or status[1] in {"R", "C"}) and index < len(entries):
            previous_path = entries[index]
            index += 1
            if previous_path and previous_path not in files:
                files.append(previous_path)
        if path and path not in files:
            files.append(path)
    return sorted(files)


def _candidate_changed_files(worktree: str, base_sha: str) -> List[str]:
    files = set(_git_changed_files(worktree))
    committed = _run_command(
        ["git", "-C", worktree, "diff", "--name-only", "-z", base_sha, "HEAD", "--"],
        operation="Inspect committed candidate changes",
    )
    files.update(path for path in committed.stdout.split("\x00") if path)
    return sorted(files)


def _new_commit_blobs_contain_secret(worktree: str, base_sha: str) -> bool:
    git_dir_result = _run_command(
        ["git", "-C", worktree, "rev-parse", "--absolute-git-dir"],
        operation="Inspect candidate git objects",
    )
    git_dir = Path(git_dir_result.stdout.strip()).resolve()
    objects_dir = git_dir / "objects"
    pack_dir = objects_dir / "pack"
    if pack_dir.is_dir() and any(pack_dir.glob("*.pack")):
        # Managed shared clones start without local packs. A candidate-created
        # pack cannot be boundedly inspected without retaining arbitrary data.
        return True

    object_ids: List[str] = []
    if objects_dir.is_dir():
        for prefix_dir in objects_dir.iterdir():
            if not prefix_dir.is_dir() or not re.fullmatch(r"[0-9a-f]{2}", prefix_dir.name):
                continue
            for object_path in prefix_dir.iterdir():
                if re.fullmatch(r"[0-9a-f]{38}", object_path.name):
                    object_ids.append(prefix_dir.name + object_path.name)
                    if len(object_ids) > 10_000:
                        return True

    committed = _run_command(
        ["git", "-C", worktree, "rev-list", "--objects", "HEAD", f"^{base_sha}"],
        operation="Inspect candidate commit objects",
        check=False,
    )
    if committed.returncode == 0:
        for line in committed.stdout.splitlines():
            object_id = line.split(" ", 1)[0].strip()
            if re.fullmatch(r"[0-9a-f]{40,64}", object_id) and object_id not in object_ids:
                object_ids.append(object_id)

    for object_id in object_ids:
        object_type = _run_command(
            ["git", "-C", worktree, "cat-file", "-t", object_id],
            operation="Inspect candidate git object type",
            check=False,
        )
        if object_type.returncode != 0 or object_type.stdout.strip() != "blob":
            continue
        size = _run_command(
            ["git", "-C", worktree, "cat-file", "-s", object_id],
            operation="Inspect candidate git object size",
            check=False,
        )
        try:
            object_size = int(size.stdout.strip())
        except ValueError:
            return True
        if object_size > 4 * 1024 * 1024:
            continue
        blob = _run_command(
            ["git", "-C", worktree, "cat-file", "blob", object_id],
            operation="Inspect candidate git blob",
            timeout=10.0,
            check=False,
        )
        if blob.returncode != 0 or "\x00" in blob.stdout[:8192]:
            continue
        if _contains_secret(blob.stdout):
            return True
    return False


def _git_cached_changed_files(worktree: str, base_sha: str) -> List[str]:
    result = _run_command(
        ["git", "-C", worktree, "diff", "--cached", "--name-only", "-z", base_sha, "--"],
        operation="List candidate changed files",
    )
    return sorted({path for path in result.stdout.split("\x00") if path})


def _git_diff_stats(worktree: str, base_sha: str) -> Dict[str, int]:
    result = _run_command(
        ["git", "-C", worktree, "diff", "--cached", "--numstat", base_sha, "--"],
        operation="Summarize candidate diff",
    )
    insertions = 0
    deletions = 0
    binary_files = 0
    for line in result.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) < 2:
            continue
        if parts[0] == "-" or parts[1] == "-":
            binary_files += 1
            continue
        try:
            insertions += int(parts[0])
            deletions += int(parts[1])
        except ValueError:
            continue
    return {"insertions": insertions, "deletions": deletions, "binary_files": binary_files}


def _risk_summary(changed_files: Sequence[str], stats: Mapping[str, int]) -> Dict[str, Any]:
    findings: List[Dict[str, str]] = []
    sensitive_paths = [
        path
        for path in changed_files
        if path.startswith((".github/", "scripts/", "backend/src/", "macOS-Client/Sources/"))
        or Path(path).name.lower() in {"dockerfile", "makefile", "package-lock.json", "uv.lock"}
    ]
    if sensitive_paths:
        findings.append({"id": "high_impact_paths", "severity": "review_required"})
    total_lines = int(stats.get("insertions") or 0) + int(stats.get("deletions") or 0)
    if total_lines > 1_500 or len(changed_files) > 50:
        findings.append({"id": "large_change", "severity": "review_required"})
    if int(stats.get("binary_files") or 0) > 0:
        findings.append({"id": "binary_change", "severity": "review_required"})
    level = "review_required" if findings else "low"
    return {"level": level, "blocking": False, "findings": findings}


def _normalize_quality_gate(raw: Mapping[str, Any]) -> Dict[str, Any]:
    verdict = str(raw.get("gate_verdict") or "").strip().lower()
    status = "passed" if verdict in {"pass", "passed", "ready", "allow"} else "failed"
    findings: List[Dict[str, Any]] = []
    for index, item in enumerate(raw.get("findings") or []):
        if not isinstance(item, Mapping):
            continue
        finding_state = str(
            item.get("state")
            or item.get("status")
            or ("pass" if status == "passed" else "failed")
        ).strip().lower()
        if finding_state not in {"pass", "auto_fix_available", "ask_user", "blocked", "no_op", "failed"}:
            finding_state = "failed"
        repair_round = item.get("repair_round")
        findings.append(
            {
                "id": _safe_metadata_value(item.get("id")) or f"finding-{index + 1}",
                "state": finding_state,
                "severity": _safe_metadata_value(item.get("severity")) or "unknown",
                "summary": _redact_text(str(item.get("summary") or ""))[:1_000],
                "evidence": _safe_finding_evidence(item.get("evidence")),
                "suggested_action": _redact_text(str(item.get("suggested_action") or ""))[:1_000] or None,
                "owner": _safe_metadata_value(item.get("owner")),
                "repair_round": repair_round if isinstance(repair_round, int) and repair_round >= 0 else 0,
                "source_gate": _safe_metadata_value(item.get("source_gate")) or "across-gate",
            }
        )
        if len(findings) >= 200:
            break
    evidence_hash = str(raw.get("evidence_hash") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", evidence_hash):
        evidence_hash = ""
    run_id = re.sub(r"[^A-Za-z0-9._-]+", "", str(raw.get("run_id") or ""))[:128]
    return {
        "required": True,
        "status": status,
        "schema_version": _safe_metadata_value(raw.get("schema_version")),
        "gate_verdict": verdict or None,
        "findings": findings,
        "evidence_hash": evidence_hash or None,
        "pr_ready_summary": _redact_text(str(raw.get("pr_ready_summary") or ""))[:2_000] or None,
        "head_sha": _safe_metadata_value(raw.get("head_sha")),
        "push_receipt": _public_push_receipt(raw.get("push_receipt")),
        "evidence_routes": [f"/api/autopilot/runs/{run_id}/evidence"] if run_id else [],
    }


def _public_push_receipt(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        return {}
    repository = raw.get("repository")
    repository_name = repository.get("name") if isinstance(repository, Mapping) else repository
    receipt = {
        "schema_version": _safe_metadata_value(raw.get("schema_version")),
        "repository": {"name": _safe_metadata_value(repository_name)} if repository_name else None,
        "base_ref": _safe_metadata_value(raw.get("base_ref")),
        "head_ref": _safe_metadata_value(raw.get("head_ref")),
        "head_sha": _safe_metadata_value(raw.get("head_sha")),
        "dirty_tree": bool(raw.get("dirty_tree")),
        "diff_summary": _sanitize_for_persistence(raw.get("diff_summary") or {}),
        "gate_verdict": _safe_metadata_value(raw.get("gate_verdict")),
        "evidence_hash": _safe_metadata_value(raw.get("evidence_hash")),
        "pr_ready_summary": _redact_text(str(raw.get("pr_ready_summary") or ""))[:2_000] or None,
    }
    return {key: value for key, value in receipt.items() if value is not None}


def _normalize_capability_preflight(raw: Mapping[str, Any], agent_ids: Sequence[str]) -> Dict[str, Any]:
    selected = [
        agent_id
        for agent_id in _dedupe_public_strings(raw.get("selected_agent_ids"))
        if agent_id in agent_ids
    ]
    recommended = [
        agent_id
        for agent_id in _dedupe_public_strings(raw.get("recommended_agent_ids"))
        if agent_id in agent_ids
    ]
    summaries: List[Dict[str, Any]] = []
    for item in raw.get("agent_summaries") or []:
        if not isinstance(item, Mapping) or item.get("agent_id") not in agent_ids:
            continue
        score = item.get("score")
        configured_count = item.get("configured_count")
        summaries.append(
            {
                "agent_id": str(item["agent_id"]),
                "score": score if isinstance(score, int) else 0,
                "configured_count": configured_count if isinstance(configured_count, int) else 0,
                "matched_skill_ids": _dedupe_public_strings(item.get("matched_skill_ids")),
                "matched_native_skill_ids": _dedupe_public_strings(item.get("matched_native_skill_ids")),
                "unavailable_native_skill_ids": _dedupe_public_strings(item.get("unavailable_native_skill_ids")),
                "warnings": [_redact_text(value)[:500] for value in _dedupe_public_strings(item.get("warnings"))[:20]],
            }
        )
    return {
        "status": "ready",
        "selected_agent_ids": selected or list(agent_ids),
        "recommended_agent_ids": recommended,
        "agent_summaries": summaries,
        "warnings": [_redact_text(value)[:500] for value in _dedupe_public_strings(raw.get("warnings"))[:50]],
        "prompt_preview_persisted": False,
    }


def _safe_finding_evidence(value: Any) -> List[Any]:
    source = value if isinstance(value, list) else ([value] if value is not None else [])
    result: List[Any] = []
    for item in source[:50]:
        if isinstance(item, Mapping):
            safe_item = {
                str(key): _sanitize_for_persistence(item.get(key), str(key))
                for key in ("type", "status", "hash", "route", "summary")
                if item.get(key) is not None
            }
            if safe_item:
                result.append(safe_item)
        elif isinstance(item, str):
            text = _redact_text(item)[:1_000]
            if text:
                result.append(text)
    return result


def _dedupe_public_strings(value: Any) -> List[str]:
    source = value if isinstance(value, (list, tuple, set)) else []
    result: List[str] = []
    for item in source:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _empty_comparison() -> Dict[str, Any]:
    return {
        "changed_files": [],
        "diff": {"files_changed": 0, "insertions": 0, "deletions": 0, "binary_files": 0},
        "patch_available": False,
        "patch_sha256": None,
        "head_sha": None,
        "review_anchor": None,
        "review_anchor_sha256": None,
        "tests": {"status": "not_run", "configured_count": 0, "completed_count": 0, "results": []},
        "quality_gate": {
            "required": False,
            "status": "not_requested",
            "gate_verdict": None,
            "findings": [],
            "evidence_hash": None,
            "pr_ready_summary": None,
        },
        "risk": {"level": "unknown", "blocking": False, "findings": []},
        "conflicts": {"status": "not_checked", "checked_at": None},
    }


def _empty_evidence() -> Dict[str, Any]:
    return {
        "schema_version": "agent-workspace-evidence/1.0",
        "generated_at": None,
        "ready_for_review": False,
        "blocking_reasons": ["candidate_not_completed"],
        "human_approval_required": True,
        "transcript_persisted": False,
    }


def _sanitize_for_persistence(value: Any, key: str = "") -> Any:
    if _SENSITIVE_KEY_RE.search(key):
        if key in {
            "prompt_digest",
            "prompt_length",
            "prompt_preview_persisted",
            "output_bytes",
            "output_sha256",
            "output_persisted",
            "transcript_persisted",
        }:
            return value
        return None
    if isinstance(value, Mapping):
        return {str(item_key): _sanitize_for_persistence(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_for_persistence(item, key) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return str(value)


def _redact_text(value: str) -> str:
    text = str(value)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def _contains_secret(value: str) -> bool:
    return any(pattern.search(str(value)) for pattern in _SECRET_PATTERNS)


def _safe_error_code(value: Any) -> str:
    text = str(value or "execution_failed").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "_", text)[:80]
    return text or "execution_failed"


def _safe_metadata_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = _redact_text(str(value).strip())[:200]
    return text or None


def _safe_usage(value: Any) -> Optional[Dict[str, int]]:
    if not isinstance(value, Mapping):
        return None
    result: Dict[str, int] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        raw = value.get(key)
        if isinstance(raw, int) and raw >= 0:
            result[key] = raw
    return result or None


def _safe_tool_calls(value: Any) -> List[str]:
    if not isinstance(value, (list, tuple)):
        return []
    tools: List[str] = []
    for item in value[:100]:
        name = item.get("name") if isinstance(item, Mapping) else item
        text = re.sub(r"[^A-Za-z0-9._:-]+", "_", str(name or "").strip())[:160]
        if text and text not in tools:
            tools.append(text)
    return tools


def _safe_evidence_links(value: Any) -> List[str]:
    if not isinstance(value, (list, tuple)):
        return []
    links: List[str] = []
    for item in value[:100]:
        text = _redact_text(str(item or "").strip())[:1_000]
        if not text or _contains_secret(text):
            continue
        if text.startswith(("/api/", "evidence://", "across://")) and text not in links:
            links.append(text)
    return links


def _safe_relative_path(value: str) -> bool:
    path = Path(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts and ".git" not in path.parts


def _validate_id(value: str, name: str) -> None:
    if not _SAFE_ID_RE.fullmatch(str(value or "")):
        raise AgentWorkspaceError(422, f"invalid_{name}", f"{name} is invalid.")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _sha256_text(value: Optional[str]) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return _sha256_text(encoded)


def _atomic_write_bytes(path: Path, data: bytes, *, mode: int) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
