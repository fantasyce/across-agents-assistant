from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping
import base64
import json
import os
import tempfile
import threading
import time

from .paths import data_file
from .plugin_runtime import PluginLifecycleError, remember_worker_context_outcome
from .worker_control import WorkerControlError, WorkerOrchestratorClient


TERMINAL_WORKER_STATES = {"completed", "failed", "cancelled", "lost", "expired"}
class WorkerTaskBridge:
    """AAA-owned mapping between a normal product Task and durable Worker Jobs."""

    def __init__(self, path: str | Path | None = None, *, client: WorkerOrchestratorClient | None = None):
        self.path = Path(path).expanduser().resolve() if path else data_file("worker-task-links.json")
        self.client = client or WorkerOrchestratorClient()
        self._lock = threading.RLock()

    def submit_workflow(
        self,
        *,
        task_id: str,
        goal: str,
        project_dir: str | None,
        job_plan: Mapping[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            state = self._read()
            existing = state["tasks"].get(task_id)
            if existing:
                return self.status(task_id)

        plan, manifest, input_bytes = _validated_worker_job_plan(job_plan)
        run_id = str(manifest["run_id"])
        job_id = str(manifest["job_id"])
        workflow_id = str(plan["workflow_id"])
        inputs_base64 = {
            logical_name: base64.b64encode(payload).decode("ascii")
            for logical_name, payload in input_bytes.items()
        }
        submitted = self.client.call(
            "job.submit",
            {
                "manifest": manifest,
                "inputs_base64": inputs_base64,
            },
        )
        link = {
            "schema_version": "across-aaa-worker-task-link/1.0",
            "task_id": task_id,
            "run_id": run_id,
            "job_id": job_id,
            "workflow_id": workflow_id,
            "workflow_title": str(plan.get("workflow_title") or workflow_id),
            "expected_outputs": list(plan.get("expected_outputs") or manifest.get("expected_outputs") or ()),
            "execution_phases": list((plan.get("execution_contract") or {}).get("phases") or ()),
            "created_at": time.time(),
            "goal_hash": sha256(goal.encode()).hexdigest(),
            "project_dir": project_dir,
            "status": str(submitted.get("status") or "queued"),
        }
        with self._lock:
            state = self._read()
            state["tasks"][task_id] = link
            self._write(state)
        return self.status(task_id)

    def status(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            link = dict(self._read()["tasks"].get(task_id) or {})
        if not link:
            raise WorkerControlError("Task has no remote Worker execution.", code="worker_task_link_not_found", status_code=404)
        job = self.client.call("job.get", {"job_id": link["job_id"]})
        previous_status = str(link.get("status") or "queued")
        status = str(job.get("status") or link.get("status") or "queued")
        link["status"] = status
        # A status read is not a task update. Prefer the Coordinator's durable
        # state-transition timestamp and never make polling reshuffle history.
        job_updated_at = float(job.get("updated_at") or 0)
        if job_updated_at > 0:
            link["updated_at"] = job_updated_at
        elif status != previous_status:
            link["updated_at"] = time.time()
        else:
            link.setdefault("updated_at", float(link.get("created_at") or time.time()))
        with self._lock:
            state = self._read()
            state["tasks"][task_id] = link
            self._write(state)
        if status in TERMINAL_WORKER_STATES and not link.get("memory_recorded_at"):
            self._record_terminal_memory(task_id, link, job)
            with self._lock:
                link = dict(self._read()["tasks"].get(task_id) or link)
        public_link = {key: value for key, value in link.items() if key not in {"project_dir", "goal_hash"}}
        receipt = _trusted_evidence_receipt(job)
        return {
            **public_link,
            "node_id": job.get("node_id"),
            "attempt": int(job.get("attempt") or 0),
            "manifest_hash": job.get("manifest_hash"),
            "scheduling_decision": job.get("scheduling_decision"),
            "events": list(job.get("events") or []),
            "evidence_receipt": receipt,
            "verified_evidence": _valid_evidence_receipt(receipt),
            "resource_usage": job.get("resource_usage") or {},
            "cleanup_status": job.get("cleanup_status"),
            "reason_category": job.get("reason_category") or job.get("cancel_reason") or job.get("last_lease_failure"),
            "terminal": status in TERMINAL_WORKER_STATES,
            "phases": _execution_phases(status, link.get("execution_phases")),
        }

    def project_task_info(self, task_info: Mapping[str, Any], remote: Mapping[str, Any]) -> dict[str, Any]:
        """Project the single Worker execution onto its durable parent Task.

        The external Orchestrator Task remains the user-visible identity, while
        the Worker Job is its only executor. This projection prevents stale
        parent status and makes verified Worker artifacts first-class Task
        artifacts without creating a second local execution.
        """
        info = dict(task_info)
        worker_state = str(remote.get("status") or "queued")
        status = _task_status_for_worker_state(worker_state)
        progress = _worker_progress(worker_state)
        terminal = bool(remote.get("terminal"))
        receipt = remote.get("evidence_receipt") if isinstance(remote.get("evidence_receipt"), Mapping) else {}
        verified = _valid_evidence_receipt(receipt)
        descriptors = [item for item in receipt.get("artifacts") or [] if isinstance(item, Mapping)]
        produced = {str(item.get("logical_name") or "") for item in descriptors}
        expected = {
            str(item)
            for item in remote.get("expected_outputs") or ()
            if str(item).strip()
        }
        # New generic Workflow Job plans always persist their output contract.
        # Older links predate that field; their verified receipt is the only
        # safe source of truth and remains viewable without a domain special case.
        if not expected and remote.get("terminal"):
            expected = set(produced)
        artifacts_ok = expected.issubset(produced)
        passed = status == "completed" and verified and artifacts_ok

        subtasks = []
        for raw in info.get("subtasks") or []:
            item = dict(raw)
            item["status"] = status if terminal else ("running" if status == "running" else "pending")
            item["progress"] = progress
            if status in {"failed", "cancelled"}:
                item["error_message"] = str(remote.get("reason_category") or worker_state)
            subtasks.append(item)
        info["subtasks"] = subtasks
        for wave in info.get("waves") or []:
            wave["status"] = status if terminal else ("running" if status == "running" else "pending")
            wave["subtasks"] = subtasks

        artifacts = []
        for descriptor in descriptors:
            artifact_id = str(descriptor.get("artifact_id") or "")
            logical_name = str(descriptor.get("logical_name") or artifact_id)
            if not artifact_id or not logical_name:
                continue
            artifacts.append({
                "id": artifact_id,
                "artifact_id": artifact_id,
                "name": logical_name,
                "file_name": logical_name,
                "file_path": f"/api/workers/artifacts/{artifact_id}",
                "content_ref": f"/api/workers/artifacts/{artifact_id}",
                "file_size": f"{max(0, int(descriptor.get('size') or 0))} B",
                "sha256": str(descriptor.get("sha256") or ""),
                "status": "accepted" if passed else "verified" if verified else "pending",
                "source": "remote_worker",
            })

        produced_files = sorted(produced)
        quality_checks = {
            **dict(receipt.get("quality_gates") or {}),
            "artifact_integrity": artifacts_ok,
            "evidence_receipt": verified,
        }
        delivery_report = {
            "quality_gate": "passed" if passed else "failed" if terminal else "pending",
            "final_status": status,
            "summary": "Worker delivery verified." if passed else "Worker delivery is still running." if not terminal else "Worker delivery did not pass verification.",
            "required_total": len(expected),
            "accepted_total": len(expected) if passed else len(produced.intersection(expected)),
            "missing_required": sorted(expected - produced),
            "failed_constraints": [] if verified else (["evidence_receipt_invalid"] if terminal else []),
            "status": "passed" if passed else "failed" if terminal else "pending",
            "source": "remote_worker",
            "required_files": sorted(expected),
            "produced_files": produced_files,
            "produced_required": produced_files,
            "checks": quality_checks,
            "quality_score": 100 if passed else 0,
            "final_quality_score": 100 if passed else 0,
            "failures": [] if passed else sorted(expected - produced),
            "quality_report": {
                "quality_gate": "passed" if passed else "failed" if terminal else "pending",
                "quality_score": 100 if passed else 0,
                "final_quality_score": 100 if passed else 0,
                "required_failed_count": 0 if passed else max(1, len(expected - produced)) if terminal else 0,
                "manual_required_count": 0,
                "required_skipped_count": 0,
                "checks": quality_checks,
            },
        }

        info.update({
            "status": status,
            "progress": progress,
            "completed_count": len(subtasks) if status == "completed" else 0,
            "total_count": len(subtasks),
            "artifacts": artifacts,
            "artifact_versions": {item["name"]: 1 for item in artifacts},
            "error": str(remote.get("reason_category") or worker_state) if status == "failed" else None,
            "remote_execution": dict(remote),
            "quality_health": {
                "manifest_total": len(expected),
                "manifest_required": len(expected),
                "manifest_accepted": len(expected) if passed else len(produced.intersection(expected)),
                "manifest_missing": len(expected - produced),
                "quality_gate": "passed" if passed else "failed" if terminal else "pending",
                "delivery_quality": "passed" if passed else "failed" if terminal else "pending",
                "delivery_quality_report": delivery_report,
                "orchestration_health": "passed" if passed else status,
            },
            "delivery_report": delivery_report,
            "observability": {
                **dict(info.get("observability") or {}),
                "worker_execution": {
                    "job_id": remote.get("job_id"),
                    "run_id": remote.get("run_id"),
                    "node_id": remote.get("node_id"),
                    "receipt_hash": receipt.get("receipt_hash"),
                    "verified": verified,
                },
            },
        })
        deliverables = [
            {"path": name, "status": "accepted" if name in produced and passed else "assigned"}
            for name in sorted(expected)
        ]
        info["requirement_manifest"] = {
            "task_id": info.get("task_id"),
            "project_dir": info.get("project_dir"),
            "deliverables": deliverables,
        }
        if terminal:
            info["acceptance_records"] = [{
                "acceptance_id": f"acc-worker-{info.get('task_id')}",
                "task_id": info.get("task_id"),
                "level": "task",
                "decision": "approve" if passed else "fix",
                "deterministic_passed": passed,
                "judge_passed": passed,
                "failed_checks": [] if passed else ["worker_evidence"],
                "missing_artifacts": sorted(expected - produced),
                "feedback": "Verified remote Worker delivery." if passed else "Remote Worker delivery needs attention.",
                "recommended_action": "approve" if passed else "fix",
                "root_cause_scope": "remote_worker",
                "root_cause_artifact_ids": [item["id"] for item in artifacts],
                "created_at": float(remote.get("updated_at") or time.time()),
            }]
        return info

    def project_task_summary(self, summary: Mapping[str, Any], remote: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(summary)
        status = _task_status_for_worker_state(str(remote.get("status") or "queued"))
        total = int(result.get("total_count") or 0)
        result.update({
            "status": status,
            "progress": _worker_progress(str(remote.get("status") or "queued")),
            "completed_count": total if status == "completed" else 0,
        })
        return result

    def _record_terminal_memory(self, task_id: str, link: dict[str, Any], job: Mapping[str, Any]) -> None:
        receipt = job.get("evidence_receipt") if isinstance(job.get("evidence_receipt"), Mapping) else {}
        receipt_hash = str(receipt.get("receipt_hash") or "")
        artifacts = receipt.get("artifacts") if isinstance(receipt.get("artifacts"), list) else []
        artifact_hashes = sorted(str(item.get("sha256") or "") for item in artifacts if isinstance(item, Mapping) and item.get("sha256"))
        artifact_hash = sha256("\n".join(artifact_hashes).encode()).hexdigest()
        node = receipt.get("node") if isinstance(receipt.get("node"), Mapping) else {}
        node_id = str(job.get("node_id") or node.get("node_id") or "")
        if not node_id or len(receipt_hash) != 64:
            return
        outcome = {
            "run_id": link["run_id"],
            "job_id": link["job_id"],
            "node_id": node_id,
            "artifact_hash": artifact_hash,
            "evidence_hash": receipt_hash,
            "terminal_state": str(job.get("status") or link.get("status") or "failed"),
            "workflow_id": link.get("workflow_id"),
            "platform": {
                "os": node.get("os"),
                "architecture": node.get("architecture"),
                "version": node.get("os_version"),
            },
            "executor": (job.get("manifest") or {}).get("executor") if isinstance(job.get("manifest"), Mapping) else None,
            "isolation_level": node.get("isolation_level"),
            "transport": "unknown",
            "conclusion": f"Worker Job {link['job_id']} ended as {job.get('status')}; verified evidence receipt {receipt_hash[:12]}.",
            "failure": None if job.get("status") == "completed" else {
                "category": _memory_failure_category(job),
                "code": str(job.get("reason_category") or job.get("cancel_reason") or "worker_job_failed")[:80],
                "retryable": str(job.get("status")) in {"lost", "expired"},
                "summary": "Remote Worker execution did not complete successfully.",
            },
            "cleanup_status": job.get("cleanup_status"),
        }
        try:
            memory = remember_worker_context_outcome(outcome=outcome, project_root=link.get("project_dir"))
        except (PluginLifecycleError, OSError, ValueError, RuntimeError) as exc:
            link["memory_error"] = type(exc).__name__
        else:
            link["memory_id"] = memory.get("id")
            link["memory_status"] = memory.get("status")
            link["memory_recorded_at"] = time.time()
            link.pop("memory_error", None)
        with self._lock:
            state = self._read()
            state["tasks"][task_id] = link
            self._write(state)

    def cancel(self, task_id: str, *, reason: str = "task_cancelled_by_user") -> dict[str, Any]:
        with self._lock:
            link = dict(self._read()["tasks"].get(task_id) or {})
        if not link:
            return {"task_id": task_id, "worker_cancelled": False, "reason": "no_worker_job"}
        result = self.client.call("job.cancel", {"job_id": link["job_id"], "reason": reason})
        return {"task_id": task_id, "worker_cancelled": True, "worker_job": result}

    def optional_status(self, task_id: str) -> dict[str, Any] | None:
        try:
            return self.status(task_id)
        except WorkerControlError as exc:
            if exc.code == "worker_task_link_not_found":
                return None
            return {
                "task_id": task_id,
                "status": "degraded",
                "terminal": False,
                "reason_category": exc.code,
                "phases": _execution_phases("degraded"),
            }

    def cached_status(self, task_id: str) -> dict[str, Any] | None:
        """Return the last durable Worker state without contacting its runtime.

        Task list views are navigation surfaces, so they must remain available
        while the Worker coordinator is still reconciling during app startup.
        Opening a task continues to use :meth:`status` and refreshes the live
        Worker state and evidence before presenting task details.
        """
        with self._lock:
            link = dict(self._read()["tasks"].get(task_id) or {})
        if not link:
            return None
        status = str(link.get("status") or "queued")
        public_link = {key: value for key, value in link.items() if key not in {"project_dir", "goal_hash"}}
        return {
            **public_link,
            "status": status,
            "terminal": status in TERMINAL_WORKER_STATES,
            "phases": _execution_phases(status, link.get("execution_phases")),
        }

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": "across-aaa-worker-task-links/1.0", "tasks": {}}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"schema_version": "across-aaa-worker-task-links/1.0", "tasks": {}}
        if not isinstance(value, dict) or value.get("schema_version") != "across-aaa-worker-task-links/1.0":
            return {"schema_version": "across-aaa-worker-task-links/1.0", "tasks": {}}
        value.setdefault("tasks", {})
        return value

    def _write(self, value: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, self.path)


def _valid_evidence_receipt(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    receipt = dict(value)
    expected = str(receipt.pop("receipt_hash", ""))
    canonical = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return len(expected) == 64 and sha256(canonical).hexdigest() == expected


def _trusted_evidence_receipt(job: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Return a hash-verifiable receipt from a public Coordinator response.

    A Coordinator may redact usage counters in its top-level public Job
    projection after it has persisted the Worker-signed terminal event. That
    intentionally changes the public receipt bytes, so its original hash can no
    longer be recomputed by AAA. The durable terminal event still contains the
    exact signed receipt. Prefer the top-level receipt when it remains valid;
    otherwise recover only a valid receipt bound to the same Job, Run, Node,
    manifest and terminal state. This preserves verification without trusting a
    caller-supplied boolean or weakening the receipt hash contract.
    """
    current = job.get("evidence_receipt")
    if _valid_evidence_receipt(current):
        return dict(current)

    for event in reversed(list(job.get("events") or [])):
        if not isinstance(event, Mapping) or str(event.get("state") or "") not in TERMINAL_WORKER_STATES:
            continue
        payload = event.get("payload")
        candidate = payload.get("evidence_receipt") if isinstance(payload, Mapping) else None
        if _valid_evidence_receipt(candidate) and _receipt_matches_job(candidate, job):
            return dict(candidate)
    return dict(current) if isinstance(current, Mapping) else None


def _receipt_matches_job(receipt: Mapping[str, Any], job: Mapping[str, Any]) -> bool:
    if str(receipt.get("job_id") or "") != str(job.get("job_id") or ""):
        return False
    if str(receipt.get("run_id") or "") != str(job.get("run_id") or ""):
        return False
    if str(receipt.get("terminal_state") or "") != str(job.get("status") or ""):
        return False
    node = receipt.get("node")
    if not isinstance(node, Mapping) or str(node.get("node_id") or "") != str(job.get("node_id") or ""):
        return False
    manifest_hash = str(job.get("manifest_hash") or "")
    return not manifest_hash or str(receipt.get("manifest_hash") or "") == manifest_hash


def _task_status_for_worker_state(value: str) -> str:
    state = str(value or "").lower()
    if state == "completed":
        return "completed"
    if state == "cancelled":
        return "cancelled"
    if state in {"failed", "lost", "expired"}:
        return "failed"
    if state in {"leased", "starting", "running", "uploading", "waiting_review"}:
        return "running"
    return "pending"


def _worker_progress(value: str) -> float:
    return {
        "queued": 0.1,
        "leased": 0.2,
        "starting": 0.3,
        "running": 0.65,
        "uploading": 0.85,
        "waiting_review": 0.95,
        "completed": 1.0,
        "failed": 1.0,
        "cancelled": 1.0,
        "lost": 1.0,
        "expired": 1.0,
    }.get(str(value or "").lower(), 0.0)


def _validated_worker_job_plan(value: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, bytes]]:
    plan = dict(value or {})
    if plan.get("schema_version") != "across-workflow-worker-job-plan/1.0":
        raise WorkerControlError(
            "Autopilot returned an incompatible Worker Job plan.",
            code="worker_job_plan_incompatible",
            status_code=422,
        )
    workflow_id = str(plan.get("workflow_id") or "").strip()
    manifest = dict(plan.get("manifest") or {})
    if not workflow_id or manifest.get("schema_version") != "across-job-manifest/1.0":
        raise WorkerControlError("Worker Job plan is incomplete.", code="worker_job_plan_invalid", status_code=422)
    if str(manifest.get("workflow_id") or "") != workflow_id:
        raise WorkerControlError("Worker Job workflow identity does not match its plan.", code="worker_job_plan_invalid", status_code=422)
    if not str(manifest.get("job_id") or "") or not str(manifest.get("run_id") or ""):
        raise WorkerControlError("Worker Job plan has no durable identity.", code="worker_job_plan_invalid", status_code=422)

    raw_inputs = plan.get("inputs") if isinstance(plan.get("inputs"), Mapping) else {}
    if not raw_inputs or len(raw_inputs) > 64:
        raise WorkerControlError("Worker Job plan has no bounded inputs.", code="worker_job_plan_invalid", status_code=422)
    input_bytes = {str(name): _job_input_bytes(payload) for name, payload in raw_inputs.items()}
    descriptors = {
        str(item.get("logical_name") or ""): item
        for item in manifest.get("input_artifacts") or []
        if isinstance(item, Mapping)
    }
    if set(descriptors) != set(input_bytes):
        raise WorkerControlError("Worker Job input contract does not match its payloads.", code="worker_job_plan_invalid", status_code=422)
    for name, payload in input_bytes.items():
        expected_hash = str(descriptors[name].get("sha256") or "")
        if len(expected_hash) != 64 or sha256(payload).hexdigest() != expected_hash:
            raise WorkerControlError("Worker Job input hash verification failed.", code="worker_job_plan_invalid", status_code=422)

    expected_outputs = [str(item) for item in plan.get("expected_outputs") or manifest.get("expected_outputs") or () if str(item).strip()]
    if not expected_outputs or len(expected_outputs) > 64 or len(expected_outputs) != len(set(expected_outputs)):
        raise WorkerControlError("Worker Job output contract is invalid.", code="worker_job_plan_invalid", status_code=422)
    plan["workflow_id"] = workflow_id
    plan["expected_outputs"] = expected_outputs
    return plan, manifest, input_bytes


def _job_input_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _execution_phases(status: str, declared: Any = None) -> list[dict[str, Any]]:
    remote_started = status not in {"queued", "degraded"}
    remote_done = status in TERMINAL_WORKER_STATES
    success = status == "completed"
    phase_ids = [str(item) for item in declared or () if str(item).strip()]
    if not phase_ids:
        phase_ids = ["local-plan", "remote-run", "local-verify"]
    titles = {
        "local-plan": "Local plan",
        "remote-run": "Worker execution",
        "local-verify": "Local verification",
    }
    phases: list[dict[str, Any]] = []
    for phase_id in phase_ids:
        if phase_id == "local-plan":
            phase_status = "completed"
        elif phase_id == "remote-run":
            phase_status = "completed" if success else status if remote_done else "running" if remote_started else "queued"
        elif phase_id == "local-verify":
            phase_status = "completed" if success else "blocked" if remote_done else "waiting"
        else:
            phase_status = "completed" if success else "blocked" if remote_done else "waiting"
        phases.append({"id": phase_id, "title": titles.get(phase_id, phase_id.replace("-", " ").title()), "status": phase_status})
    return phases


def _memory_failure_category(job: Mapping[str, Any]) -> str:
    reason = str(job.get("reason_category") or job.get("cancel_reason") or "").lower()
    if "cancel" in reason:
        return "cancelled"
    if "provider" in reason or "model" in reason:
        return "provider"
    if "network" in reason or "transport" in reason or str(job.get("status")) == "lost":
        return "network"
    if "budget" in reason or "memory" in reason or "disk" in reason or "timeout" in reason:
        return "resource"
    if "artifact" in reason or "quality" in reason:
        return "quality_gate"
    if "security" in reason or "sandbox" in reason:
        return "security"
    return "worker"


_bridge: WorkerTaskBridge | None = None


def get_worker_task_bridge() -> WorkerTaskBridge:
    global _bridge
    if _bridge is None:
        _bridge = WorkerTaskBridge()
    return _bridge


def reset_worker_task_bridge_for_tests() -> None:
    global _bridge
    _bridge = None
