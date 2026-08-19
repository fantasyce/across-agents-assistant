from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json

from fastapi.testclient import TestClient

from across_agents_assistant.api_server import app
from across_agents_assistant import api_server
from across_agents_assistant.paths import data_file

from across_agents_assistant.worker_task_bridge import WorkerTaskBridge
from across_agents_assistant.task_review.quality_benchmark import evaluate_delivery_benchmark


EXPECTED_OUTPUTS = ("report.md", "result.json", "evidence.json")


def _worker_job_plan(*, workflow_id="remote-analysis", timeout_seconds=90, quality_contract=None):
    input_payload = {"goal": "Complete a bounded remote analysis."}
    input_bytes = json.dumps(
        input_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    manifest = {
        "schema_version": "across-job-manifest/1.0",
        "job_id": "job-test",
        "run_id": "run-test",
        "project_id": "project-test",
        "workflow_id": workflow_id,
        "command_argv": ["across-generic-runner", "run"],
        "input_artifacts": [{
            "logical_name": "input.json",
            "sha256": sha256(input_bytes).hexdigest(),
        }],
        "expected_outputs": list(EXPECTED_OUTPUTS),
        "budgets": {"timeout_seconds": timeout_seconds},
        "required_capabilities": {"workflow_runtimes": [f"{workflow_id}/1.0"]},
    }
    plan = {
        "schema_version": "across-workflow-worker-job-plan/1.0",
        "workflow_id": workflow_id,
        "workflow_title": "Remote Analysis",
        "execution_contract": {
            "route": "worker",
            "phases": ["local-plan", "remote-run", "local-verify"],
            "generated_by": "across-autopilot",
        },
        "manifest": manifest,
        "inputs": {"input.json": input_payload},
        "expected_outputs": list(EXPECTED_OUTPUTS),
    }
    if quality_contract is not None:
        plan["quality_contract"] = quality_contract
    return plan


class FakeWorkerClient:
    def __init__(self):
        self.calls = []
        self.job = None

    def call(self, action, payload=None):
        payload = dict(payload or {})
        self.calls.append((action, payload))
        if action == "job.submit":
            manifest = payload["manifest"]
            self.job = {
                "job_id": manifest["job_id"],
                "run_id": manifest["run_id"],
                "manifest": manifest,
                "manifest_hash": "a" * 64,
                "status": "queued",
                "attempt": 0,
                "node_id": None,
                "events": [],
            }
            return dict(self.job)
        if action == "job.get":
            return dict(self.job)
        if action == "job.cancel":
            self.job["status"] = "cancelled"
            self.job["cancel_reason"] = payload["reason"]
            return dict(self.job)
        raise AssertionError(action)


def _seed_worker_link(bridge: WorkerTaskBridge, *, task_id: str = "task-read-only") -> None:
    bridge._write({
        "schema_version": "across-aaa-worker-task-links/1.0",
        "tasks": {
            task_id: {
                "schema_version": "across-aaa-worker-task-link/1.0",
                "task_id": task_id,
                "job_id": "job-read-only",
                "run_id": "run-read-only",
                "workflow_id": "remote-analysis",
                "workflow_title": "Remote Analysis",
                "expected_outputs": list(EXPECTED_OUTPUTS),
                "execution_phases": ["local-plan", "remote-run", "local-verify"],
                "created_at": 10.0,
                "updated_at": 11.0,
                "status": "queued",
                "project_dir": "/private/project",
                "goal_hash": "f" * 64,
            }
        },
    })


def _signed_worker_receipt(**extra):
    receipt = {
        "schema_version": "across-worker-evidence/1.0",
        "run_id": "run-read-only",
        "job_id": "job-read-only",
        "node": {"node_id": "node-read-only", "platform": "macos/arm64"},
        "terminal_state": "completed",
        "manifest_hash": "a" * 64,
        "artifacts": [],
        "cleanup_status": "complete",
        **extra,
    }
    receipt["receipt_hash"] = sha256(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return receipt


def _install_worker_artifact(logical_name: str, payload: bytes, *, artifact_id: str | None = None) -> dict:
    artifact_id = artifact_id or f"artifact-{sha256(logical_name.encode()).hexdigest()[:24]}"
    directory = data_file("worker-artifacts") / artifact_id
    directory.mkdir(parents=True)
    digest = sha256(payload).hexdigest()
    (directory / "artifact.bin").write_bytes(payload)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "across-worker-artifact/1.0",
                "artifact_id": artifact_id,
                "logical_name": logical_name,
                "media_type": "application/json" if logical_name.endswith(".json") else "text/markdown",
                "size": len(payload),
                "sha256": digest,
                "upload_status": "complete",
                "verification_status": "verified",
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return {
        "artifact_id": artifact_id,
        "logical_name": logical_name,
        "size": len(payload),
        "sha256": digest,
    }


def test_generic_bridge_submits_autopilot_planned_job_and_tracks_normal_task(tmp_path):
    client = FakeWorkerClient()
    bridge = WorkerTaskBridge(tmp_path / "links.json", client=client)
    result = bridge.submit_workflow(
        task_id="task-host",
        goal="Complete a bounded remote analysis",
        project_dir=str(tmp_path / "project"),
        job_plan=_worker_job_plan(),
    )
    assert result["status"] == "queued"
    action, payload = client.calls[0]
    assert action == "job.submit"
    manifest = payload["manifest"]
    assert manifest["command_argv"] == ["across-generic-runner", "run"]
    assert manifest["required_capabilities"]["workflow_runtimes"] == ["remote-analysis/1.0"]
    assert manifest["budgets"]["timeout_seconds"] == 90
    assert tuple(manifest["expected_outputs"]) == EXPECTED_OUTPUTS
    assert set(payload["inputs_base64"]) == {"input.json"}
    assert manifest["input_artifacts"][0]["sha256"] == sha256(__import__("base64").b64decode(payload["inputs_base64"]["input.json"])).hexdigest()
    assert [item["status"] for item in result["phases"]] == ["completed", "queued", "waiting"]
    assert "project_dir" not in result
    cancelled = bridge.cancel("task-host")
    assert cancelled["worker_cancelled"] is True
    assert client.calls[-1][0] == "job.cancel"


def test_terminal_worker_job_produces_one_pending_context_candidate(tmp_path, monkeypatch):
    client = FakeWorkerClient()
    bridge = WorkerTaskBridge(tmp_path / "links.json", client=client)
    submitted = bridge.submit_workflow(
        task_id="task-memory",
        goal="Bounded remote analysis",
        project_dir=str(tmp_path),
        job_plan=_worker_job_plan(),
    )
    recorded = []

    def remember(**kwargs):
        recorded.append(kwargs)
        return {"id": "memory-worker-1", "status": "pending"}

    monkeypatch.setattr("across_agents_assistant.worker_task_bridge.remember_worker_context_outcome", remember)
    client.job.update(
        {
            "status": "completed",
            "node_id": "node-test",
            "attempt": 1,
            "cleanup_status": "complete",
            "resource_usage": {"wall_seconds": 0.2},
            "evidence_receipt": {
                "receipt_hash": "b" * 64,
                "node": {"node_id": "node-test", "os": "macos", "architecture": "arm64", "os_version": "15"},
                "artifacts": [{"sha256": "c" * 64}],
            },
        }
    )
    terminal = bridge.status("task-memory")
    assert terminal["memory_id"] == "memory-worker-1"
    assert terminal["memory_status"] == "pending"
    assert recorded[0]["outcome"]["artifact_hash"] == sha256(("c" * 64).encode()).hexdigest()
    bridge.status("task-memory")
    assert len(recorded) == 1


def test_bridge_preserves_autopilot_worker_timeout_contract(tmp_path):
    client = FakeWorkerClient()
    bridge = WorkerTaskBridge(tmp_path / "links.json", client=client)
    bridge.submit_workflow(
        task_id="task-live-timeout",
        goal="Bounded remote analysis",
        project_dir=str(tmp_path),
        job_plan=_worker_job_plan(timeout_seconds=90),
    )
    manifest = client.calls[0][1]["manifest"]
    assert manifest["budgets"]["timeout_seconds"] == 90


def test_bridge_preserves_large_autopilot_worker_timeout_contract(tmp_path):
    client = FakeWorkerClient()
    bridge = WorkerTaskBridge(tmp_path / "links.json", client=client)
    bridge.submit_workflow(
        task_id="task-live-rounds",
        goal="Long bounded remote analysis",
        project_dir=str(tmp_path),
        job_plan=_worker_job_plan(timeout_seconds=750),
    )
    manifest = client.calls[0][1]["manifest"]
    assert manifest["budgets"]["timeout_seconds"] == 750


def test_bridge_rejects_a_worker_plan_whose_input_hash_does_not_match(tmp_path):
    client = FakeWorkerClient()
    bridge = WorkerTaskBridge(tmp_path / "links.json", client=client)
    plan = _worker_job_plan()
    plan["manifest"]["input_artifacts"][0]["sha256"] = "0" * 64

    try:
        bridge.submit_workflow(
            task_id="task-invalid-plan",
            goal="Bounded remote analysis",
            project_dir=str(tmp_path),
            job_plan=plan,
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "worker_job_plan_invalid"
    else:
        raise AssertionError("A mismatched Autopilot input contract must not reach a Worker")
    assert client.calls == []


def test_bridge_rejects_an_unbounded_or_unknown_quality_contract(tmp_path):
    client = FakeWorkerClient()
    bridge = WorkerTaskBridge(tmp_path / "links.json", client=client)
    plan = _worker_job_plan(quality_contract={
        "schema_version": "across-workflow-output-quality/1.0",
        "artifact": "unknown.json",
        "assertions": [{"kind": "equals", "path": ["status"], "value": "completed"}],
    })

    try:
        bridge.submit_workflow(
            task_id="task-invalid-quality-contract",
            goal="Bounded remote analysis",
            project_dir=str(tmp_path),
            job_plan=plan,
        )
    except Exception as exc:
        assert getattr(exc, "code", None) == "worker_job_plan_invalid"
    else:
        raise AssertionError("An unknown quality artifact must not reach a Worker")
    assert client.calls == []


def test_cached_status_never_contacts_worker_runtime(tmp_path):
    client = FakeWorkerClient()
    bridge = WorkerTaskBridge(tmp_path / "links.json", client=client)
    bridge.submit_workflow(
        task_id="task-cached",
        goal="Bounded remote analysis",
        project_dir=str(tmp_path),
        job_plan=_worker_job_plan(),
    )
    calls_before_read = list(client.calls)

    cached = bridge.cached_status("task-cached")

    assert cached is not None
    assert cached["status"] == "queued"
    assert cached["terminal"] is False
    assert client.calls == calls_before_read
    assert bridge.cached_status("missing-task") is None


def test_read_only_status_returns_none_for_an_unlinked_task_without_contacting_worker(tmp_path):
    client = FakeWorkerClient()
    bridge = WorkerTaskBridge(tmp_path / "links.json", client=client)

    assert bridge.read_only_status("missing-task") is None
    assert client.calls == []
    assert not bridge.path.exists()


def test_read_only_status_reads_one_running_job_without_changing_link_or_memory(tmp_path, monkeypatch):
    client = FakeWorkerClient()
    bridge = WorkerTaskBridge(tmp_path / "links.json", client=client)
    _seed_worker_link(bridge)
    client.job = {
        "job_id": "job-read-only",
        "run_id": "run-read-only",
        "manifest_hash": "a" * 64,
        "status": "running",
        "attempt": 1,
        "node_id": "node-read-only",
        "events": [{
            "event_id": "worker-event-1",
            "sequence": 1,
            "timestamp": 12.0,
            "type": "task.started",
            "task_id": "task-read-only",
        }],
    }
    before = (bridge.path.read_bytes(), bridge.path.stat().st_mtime_ns)
    memory_calls = []
    monkeypatch.setattr(
        bridge,
        "_record_terminal_memory",
        lambda *args, **kwargs: memory_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        bridge,
        "_write",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("read_only_status must not write")),
    )

    result = bridge.read_only_status("task-read-only")
    after = (bridge.path.read_bytes(), bridge.path.stat().st_mtime_ns)

    assert before == after
    assert client.calls == [("job.get", {"job_id": "job-read-only"})]
    assert memory_calls == []
    assert result is not None
    assert result["status"] == "running"
    assert result["terminal"] is False
    assert result["events"] == client.job["events"]
    assert result["evidence_receipt"] is None
    assert result["verified_evidence"] is False
    assert "project_dir" not in result
    assert "goal_hash" not in result


def test_read_only_status_returns_valid_terminal_receipt_without_recording_memory(tmp_path, monkeypatch):
    client = FakeWorkerClient()
    bridge = WorkerTaskBridge(tmp_path / "links.json", client=client)
    _seed_worker_link(bridge)
    receipt = _signed_worker_receipt()
    client.job = {
        "job_id": "job-read-only",
        "run_id": "run-read-only",
        "manifest_hash": "a" * 64,
        "status": "completed",
        "attempt": 2,
        "node_id": "node-read-only",
        "events": [],
        "evidence_receipt": receipt,
        "resource_usage": {"wall_seconds": 1.5},
        "cleanup_status": "complete",
    }
    before = (bridge.path.read_bytes(), bridge.path.stat().st_mtime_ns)
    memory_calls = []
    monkeypatch.setattr(
        bridge,
        "_record_terminal_memory",
        lambda *args, **kwargs: memory_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        bridge,
        "_write",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("read_only_status must not write")),
    )

    result = bridge.read_only_status("task-read-only")

    assert (bridge.path.read_bytes(), bridge.path.stat().st_mtime_ns) == before
    assert memory_calls == []
    assert result is not None
    assert result["status"] == "completed"
    assert result["terminal"] is True
    assert result["evidence_receipt"] == receipt
    assert result["verified_evidence"] is True
    assert result["resource_usage"] == {"wall_seconds": 1.5}


def test_read_only_status_recovers_only_a_job_bound_terminal_event_receipt(tmp_path, monkeypatch):
    client = FakeWorkerClient()
    bridge = WorkerTaskBridge(tmp_path / "links.json", client=client)
    _seed_worker_link(bridge)
    receipt = _signed_worker_receipt(summary="完成")
    event = {
        "event_id": "worker-event-terminal",
        "sequence": 9,
        "timestamp": 20.0,
        "type": "task.completed",
        "state": "completed",
        "task_id": "task-read-only",
        "payload": {"evidence_receipt": receipt},
    }
    client.job = {
        "job_id": "job-read-only",
        "run_id": "run-read-only",
        "manifest_hash": "a" * 64,
        "status": "completed",
        "attempt": 2,
        "node_id": "node-read-only",
        "events": [event],
        "evidence_receipt": {**receipt, "cleanup_status": "mutated"},
        "cleanup_status": "complete",
    }
    before = (bridge.path.read_bytes(), bridge.path.stat().st_mtime_ns)
    monkeypatch.setattr(
        bridge,
        "_record_terminal_memory",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not record memory")),
    )
    monkeypatch.setattr(
        bridge,
        "_write",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("read_only_status must not write")),
    )

    result = bridge.read_only_status("task-read-only")

    assert (bridge.path.read_bytes(), bridge.path.stat().st_mtime_ns) == before
    assert result is not None
    assert result["events"] == [event]
    assert result["evidence_receipt"] == receipt
    assert result["verified_evidence"] is True


def test_worker_status_reads_do_not_reorder_task_history(tmp_path):
    client = FakeWorkerClient()
    bridge = WorkerTaskBridge(tmp_path / "links.json", client=client)
    submitted = bridge.submit_workflow(
        task_id="task-stable-order",
        goal="Bounded remote analysis",
        project_dir=str(tmp_path),
        job_plan=_worker_job_plan(),
    )
    first_updated_at = submitted["updated_at"]

    second = bridge.status("task-stable-order")
    projected = bridge.project_task_summary(
        {"task_id": "task-stable-order", "status": "pending", "updated_at": 123.0, "total_count": 1},
        {**second, "updated_at": 999.0},
    )

    assert second["updated_at"] == first_updated_at
    assert projected["updated_at"] == 123.0


def test_worker_completion_projects_verified_status_and_artifacts_onto_parent_task(tmp_path, monkeypatch):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "across-home"))
    client = FakeWorkerClient()
    bridge = WorkerTaskBridge(tmp_path / "links.json", client=client)
    bridge.submit_workflow(
        task_id="task-parent",
        goal="Bounded remote analysis",
        project_dir=str(tmp_path),
        job_plan=_worker_job_plan(quality_contract={
            "schema_version": "across-workflow-output-quality/1.0",
            "artifact": "result.json",
            "assertions": [{"kind": "equals", "path": ["status"], "value": "completed"}],
        }),
    )
    monkeypatch.setattr(
        "across_agents_assistant.worker_task_bridge.remember_worker_context_outcome",
        lambda **kwargs: {"id": "memory-1", "status": "pending"},
    )
    artifacts = [
        _install_worker_artifact("report.md", b"# Report\n\nComplete delivery.\n"),
        _install_worker_artifact("result.json", json.dumps({"status": "completed"}, sort_keys=True).encode()),
        _install_worker_artifact("evidence.json", json.dumps({"quality_gates": {"required_artifacts_present": True}}, sort_keys=True).encode()),
    ]
    receipt = {
        "schema_version": "across-worker-evidence/1.0",
        "run_id": client.job["run_id"],
        "job_id": client.job["job_id"],
        "node": {"node_id": "node-test", "platform": "macos/arm64"},
        "terminal_state": "completed",
        "artifacts": artifacts,
        "quality_gates": {"required_artifacts_present": True},
        "cleanup_status": "complete",
    }
    receipt["receipt_hash"] = sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    client.job.update({
        "status": "completed",
        "node_id": "node-test",
        "attempt": 1,
        "cleanup_status": "complete",
        "evidence_receipt": receipt,
    })

    remote = bridge.status("task-parent")
    projected = bridge.project_task_info(
        {
            "task_id": "task-parent",
            "status": "pending",
            "progress": 0,
            "subtasks": [{"subtask_id": "sub-1", "status": "pending", "progress": 0}],
            "waves": [{"wave_id": "wave-1", "status": "pending", "subtasks": []}],
            "observability": {},
        },
        remote,
    )

    assert remote["verified_evidence"] is True
    assert projected["status"] == "completed"
    assert projected["progress"] == 1
    assert projected["quality_health"]["quality_gate"] == "passed"
    assert projected["delivery_report"]["checks"]["output_contract_satisfied"] is True
    assert {item["name"] for item in projected["artifacts"]} == set(EXPECTED_OUTPUTS)
    assert all(item["status"] == "accepted" for item in projected["artifacts"])
    assert projected["acceptance_records"][0]["decision"] == "approve"
    benchmark = evaluate_delivery_benchmark(
        [projected],
        benchmark_id="worker-evidence",
        expected_files=EXPECTED_OUTPUTS,
    )
    assert benchmark["status"] == "passed"
    assert benchmark["scenarios"][0]["quality_score"] == 100


def test_worker_completion_with_degraded_model_usage_requires_review(tmp_path, monkeypatch):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "across-home"))
    client = FakeWorkerClient()
    bridge = WorkerTaskBridge(tmp_path / "links.json", client=client)
    bridge.submit_workflow(
        task_id="task-degraded",
        goal="Bounded remote analysis",
        project_dir=str(tmp_path),
        job_plan=_worker_job_plan(),
    )
    monkeypatch.setattr(
        "across_agents_assistant.worker_task_bridge.remember_worker_context_outcome",
        lambda **kwargs: {"id": "memory-degraded", "status": "pending"},
    )
    result = {
        "status": "completed",
        "rounds": 2,
        "narrative_timeline": [
            {"round": 1, "summary": "Detailed result.", "role_states": [{"role": "A"}]},
            {"round": 2, "summary": "Round 2: 参与者 1 moved toward cooperation, 参与者 2 moved toward conflict.", "role_states": []},
        ],
        "model_usage": {"degraded": True, "failed_calls": 1, "fallback_rounds": [2]},
    }
    artifacts = [
        _install_worker_artifact("report.md", b"# Report\n\nRound 2: Participant 1 moved toward cooperation.\n"),
        _install_worker_artifact("result.json", json.dumps(result, ensure_ascii=False, sort_keys=True).encode()),
        _install_worker_artifact("evidence.json", json.dumps({"model_usage": result["model_usage"]}, sort_keys=True).encode()),
        _install_worker_artifact("model-usage.json", json.dumps(result["model_usage"], sort_keys=True).encode()),
    ]
    receipt = {
        "schema_version": "across-worker-evidence/1.0",
        "run_id": client.job["run_id"],
        "job_id": client.job["job_id"],
        "node": {"node_id": "node-test", "platform": "macos/arm64"},
        "terminal_state": "completed",
        "artifacts": artifacts,
        "quality_gates": {"required_artifacts_present": True},
        "cleanup_status": "complete",
    }
    receipt["receipt_hash"] = sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    client.job.update({
        "status": "completed",
        "node_id": "node-test",
        "attempt": 1,
        "cleanup_status": "complete",
        "evidence_receipt": receipt,
    })

    remote = bridge.status("task-degraded")
    projected = bridge.project_task_info(
        {
            "task_id": "task-degraded",
            "status": "pending",
            "progress": 0,
            "subtasks": [{"subtask_id": "sub-1", "status": "pending", "progress": 0}],
            "waves": [],
            "observability": {},
        },
        remote,
    )
    summary = bridge.project_task_summary(
        {"task_id": "task-degraded", "status": "completed", "progress": 1, "completed_count": 1, "total_count": 1},
        bridge.cached_status("task-degraded") or remote,
    )

    assert projected["status"] == "completed_with_failures"
    assert projected["completed_count"] == 1
    assert summary["status"] == "completed_with_failures"
    assert summary["completed_count"] == 1
    assert projected["quality_health"]["delivery_quality"] == "partial"
    assert projected["quality_health"]["quality_gate"] == "partial"
    assert projected["delivery_report"]["quality_score"] == 60
    assert "worker_model_degraded" in projected["delivery_report"]["failed_constraints"]
    assert "worker_report_placeholder_content" in projected["delivery_report"]["failed_constraints"]
    assert all(item["status"] == "verified" for item in projected["artifacts"])
    benchmark = evaluate_delivery_benchmark(
        [projected],
        benchmark_id="worker-degraded",
        expected_files=EXPECTED_OUTPUTS,
    )
    assert benchmark["status"] == "failed"


def test_worker_completion_requires_the_autopilot_declared_semantic_output_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "across-home"))
    client = FakeWorkerClient()
    bridge = WorkerTaskBridge(tmp_path / "links.json", client=client)
    contract = {
        "schema_version": "across-workflow-output-quality/1.0",
        "artifact": "result.json",
        "assertions": [
            {"kind": "equals", "path": ["runtime_version"], "value": "1.1.16"},
            {"kind": "collection_contains", "path": ["roles"], "field": "label", "values": ["居民代表林宁", "物业经理周凯", "施工负责人陈雨"]},
            {"kind": "not_equals", "path": ["conclusion"], "value": "The next round remains uncertain without a model annotation."},
        ],
    }
    bridge.submit_workflow(
        task_id="task-semantic-contract",
        goal="Bounded remote analysis",
        project_dir=str(tmp_path),
        job_plan=_worker_job_plan(quality_contract=contract),
    )
    monkeypatch.setattr(
        "across_agents_assistant.worker_task_bridge.remember_worker_context_outcome",
        lambda **kwargs: {"id": "memory-semantic", "status": "pending"},
    )
    artifacts = [
        _install_worker_artifact("report.md", b"# Report\n\nFiles exist, but the semantic output is stale.\n"),
        _install_worker_artifact("result.json", json.dumps({
            "status": "completed",
            "runtime_version": "1.1.14",
            "roles": [{"label": "参与者 1"}, {"label": "参与者 2"}],
            "conclusion": "The next round remains uncertain without a model annotation.",
        }, ensure_ascii=False, sort_keys=True).encode()),
        _install_worker_artifact("evidence.json", json.dumps({"quality_gates": {"required_artifacts_present": True}}, sort_keys=True).encode()),
    ]
    receipt = {
        "schema_version": "across-worker-evidence/1.0",
        "run_id": client.job["run_id"],
        "job_id": client.job["job_id"],
        "node": {"node_id": "node-test", "platform": "macos/arm64"},
        "terminal_state": "completed",
        "artifacts": artifacts,
        "quality_gates": {"required_artifacts_present": True},
        "cleanup_status": "complete",
    }
    receipt["receipt_hash"] = sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    client.job.update({
        "status": "completed",
        "node_id": "node-test",
        "attempt": 1,
        "cleanup_status": "complete",
        "evidence_receipt": receipt,
    })

    remote = bridge.status("task-semantic-contract")
    projected = bridge.project_task_info({
        "task_id": "task-semantic-contract",
        "status": "pending",
        "progress": 0,
        "subtasks": [{"subtask_id": "sub-1", "status": "pending", "progress": 0}],
        "waves": [],
        "observability": {},
    }, remote)

    assert projected["status"] == "completed_with_failures"
    assert projected["delivery_report"]["quality_score"] == 60
    assert projected["delivery_report"]["checks"]["output_contract_satisfied"] is False
    assert "worker_quality_contract_equals:runtime_version" in projected["delivery_report"]["failed_constraints"]
    assert "worker_quality_contract_collection:roles.label" in projected["delivery_report"]["failed_constraints"]
    assert "worker_quality_contract_not_equals:conclusion" in projected["delivery_report"]["failed_constraints"]


def test_public_usage_redaction_recovers_the_hash_valid_terminal_event_receipt(tmp_path, monkeypatch):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "across-home"))
    client = FakeWorkerClient()
    bridge = WorkerTaskBridge(tmp_path / "links.json", client=client)
    bridge.submit_workflow(
        task_id="task-redacted-receipt",
        goal="Bounded remote analysis",
        project_dir=str(tmp_path),
        job_plan=_worker_job_plan(),
    )
    monkeypatch.setattr(
        "across_agents_assistant.worker_task_bridge.remember_worker_context_outcome",
        lambda **kwargs: {"id": "memory-redacted", "status": "pending"},
    )
    artifacts = [
        _install_worker_artifact("report.md", b"# Report\n\nComplete delivery.\n"),
        _install_worker_artifact("result.json", json.dumps({"status": "completed"}, sort_keys=True).encode()),
        _install_worker_artifact("evidence.json", json.dumps({"quality_gates": {"required_artifacts_present": True}}, sort_keys=True).encode()),
    ]
    signed_receipt = {
        "schema_version": "across-worker-evidence/1.0",
        "run_id": client.job["run_id"],
        "job_id": client.job["job_id"],
        "node": {"node_id": "node-test", "platform": "macos/arm64"},
        "manifest_hash": client.job["manifest_hash"],
        "terminal_state": "completed",
        "artifacts": artifacts,
        "model_usage": {},
        "quality_gates": {},
        "cleanup_status": "complete",
    }
    signed_receipt["receipt_hash"] = sha256(
        json.dumps(signed_receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    redacted_receipt = {
        **signed_receipt,
        "model_usage": {"calls": 2, "tokens": "[redacted]"},
        "receipt_hash": "f" * 64,
    }
    client.job.update({
        "status": "completed",
        "node_id": "node-test",
        "attempt": 1,
        "cleanup_status": "complete",
        "evidence_receipt": redacted_receipt,
        "events": [{"state": "completed", "payload": {"evidence_receipt": signed_receipt}}],
    })

    remote = bridge.status("task-redacted-receipt")
    projected = bridge.project_task_info(
        {
            "task_id": "task-redacted-receipt",
            "status": "pending",
            "subtasks": [{"subtask_id": "sub-1", "status": "pending", "progress": 0}],
            "waves": [],
            "observability": {},
        },
        remote,
    )

    assert remote["verified_evidence"] is True
    assert remote["evidence_receipt"]["receipt_hash"] == signed_receipt["receipt_hash"]
    assert projected["quality_health"]["quality_gate"] == "passed"


def test_verified_worker_artifact_endpoint_rechecks_size_and_hash(tmp_path, monkeypatch):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "across-home"))
    artifact_id = "artifact-download-test"
    directory = data_file("worker-artifacts") / artifact_id
    directory.mkdir(parents=True)
    payload = b"verified worker report\n"
    (directory / "artifact.bin").write_bytes(payload)
    manifest = {
        "schema_version": "across-worker-artifact/1.0",
        "artifact_id": artifact_id,
        "logical_name": "report.md",
        "media_type": "text/markdown",
        "size": len(payload),
        "sha256": sha256(payload).hexdigest(),
        "upload_status": "complete",
        "verification_status": "verified",
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    client = TestClient(app)
    response = client.get(f"/api/workers/artifacts/{artifact_id}")
    assert response.status_code == 200
    assert response.content == payload
    assert "report.md" in response.headers["content-disposition"]

    (directory / "artifact.bin").write_bytes(b"tampered")
    rejected = client.get(f"/api/workers/artifacts/{artifact_id}")
    assert rejected.status_code == 404


def test_verified_worker_artifact_endpoint_rejects_symlink_members(tmp_path, monkeypatch):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "across-home"))
    artifact_id = "artifact-symlink-test"
    directory = data_file("worker-artifacts") / artifact_id
    directory.mkdir(parents=True)
    payload = b"outside worker report\n"
    outside = tmp_path / "outside.bin"
    outside.write_bytes(payload)
    (directory / "artifact.bin").symlink_to(outside)
    (directory / "manifest.json").write_text(
        json.dumps({
            "schema_version": "across-worker-artifact/1.0",
            "artifact_id": artifact_id,
            "logical_name": "report.md",
            "media_type": "text/markdown",
            "size": len(payload),
            "sha256": sha256(payload).hexdigest(),
            "upload_status": "complete",
            "verification_status": "verified",
        }),
        encoding="utf-8",
    )

    response = TestClient(app).get(f"/api/workers/artifacts/{artifact_id}")

    assert response.status_code == 404


def test_verified_worker_artifact_endpoint_rejects_symlink_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "across-home"))
    artifact_id = "artifact-directory-link"
    root = data_file("worker-artifacts")
    root.mkdir(parents=True)
    outside = tmp_path / "outside-artifact"
    outside.mkdir()
    (root / artifact_id).symlink_to(outside, target_is_directory=True)

    response = TestClient(app).get(f"/api/workers/artifacts/{artifact_id}")

    assert response.status_code == 404


def test_external_worker_evidence_bundle_uses_projected_worker_receipt(monkeypatch):
    class FakePlugin:
        def get_task(self, task_id):
            return {"task_id": task_id}

    delivery_report = {
        "quality_gate": "passed",
        "final_status": "completed",
        "status": "passed",
        "source": "remote_worker",
        "quality_score": 100,
        "final_quality_score": 100,
        "required_files": list(EXPECTED_OUTPUTS),
        "produced_files": list(EXPECTED_OUTPUTS),
        "produced_required": list(EXPECTED_OUTPUTS),
        "quality_report": {
            "quality_gate": "passed",
            "quality_score": 100,
            "final_quality_score": 100,
            "required_failed_count": 0,
            "manual_required_count": 0,
            "required_skipped_count": 0,
        },
    }

    async def projected_task(*_args, **_kwargs):
        return {
            "task_id": "task-worker-evidence",
            "description": "Remote Analysis",
            "status": "completed",
            "task_types": ["artifact", "functional"],
            "delivery_mode": "composite",
            "quality_health": {
                "quality_gate": "passed",
                "delivery_quality": "passed",
                "delivery_quality_report": delivery_report,
            },
            "delivery_report": delivery_report,
            "remote_execution": {
                "job_id": "job-worker",
                "verified_evidence": True,
                "expected_outputs": list(EXPECTED_OUTPUTS),
            },
            "artifacts": [{"name": name, "status": "accepted"} for name in EXPECTED_OUTPUTS],
            "requirement_manifest": {
                "deliverables": [{"path": name, "status": "accepted"} for name in EXPECTED_OUTPUTS]
            },
            "acceptance_records": [{"decision": "approve", "deterministic_passed": True}],
        }

    monkeypatch.setattr(api_server, "_is_external_orchestrator_task", lambda _task_id: True)
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakePlugin())
    monkeypatch.setattr(api_server, "_external_task_info_with_worker", projected_task)

    response = TestClient(app).get("/api/tasks/task-worker-evidence/evidence-bundle")
    assert response.status_code == 200
    payload = response.json()
    assert payload["benchmark"]["status"] == "passed"
    assert payload["audit"]["expected_files"] == sorted(EXPECTED_OUTPUTS)
    assert payload["delivery_report"]["source"] == "remote_worker"
    assert {item["name"] for item in payload["artifacts"]} == set(EXPECTED_OUTPUTS)
