from fastapi.testclient import TestClient
from types import SimpleNamespace
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json

import across_agents_assistant.api_server as api_server
from across_agents_assistant import local_agent_health
from across_agents_assistant.autopilot_client import AutopilotClient, _long_run_timeout_seconds
from across_agents_assistant.autopilot_promotion_review import build_promotion_review_packet
from across_agents_assistant.autopilot_trigger_manager import AutopilotTriggerRegistry, AutopilotTriggerScheduler
from across_agents_assistant.api_server import app
from across_agents_assistant.plugin_runtime import PluginLifecycleError


def _assert_marker_upsert(patch, marker_start, marker_end):
    assert patch["mode"] == "upsert_between_markers"
    assert patch["marker_start"] == marker_start
    assert patch["marker_end"] == marker_end


class FakeAutopilotClient:
    def registry(self):
        return {
            "schema_version": "across-autopilot-loop-registry/1.0",
            "built_in": [{"id": "daily-news-brief", "title": "Daily News Brief"}],
            "registered": [],
        }

    def validate_spec(self, spec):
        return {"valid": True, "spec": {"id": spec}, "migration": {"changed": False}}

    def dry_run(self, spec):
        return {
            "valid": True,
            "spec": {"id": spec},
            "adapters": {"sources": ["manual_input"], "actions": ["report_generation"]},
            "autonomy": {"mode": "approval_required"},
        }

    def run(self, spec, *, trigger="aaa-user", model_policy_overrides=None):
        return {
            "run": {"run_id": "run-api-1", "spec_id": spec, "status": "completed", "trigger": trigger},
            "evidence": {
                "schema_version": "across-loop-evidence/1.0",
                "run_id": "run-api-1",
                "status": "completed",
                "model_policy_overrides": model_policy_overrides or {},
                "gates": {"quality": "passed"},
                "orchestrator": {"tasks": [{"task_id": "loop-api-1", "metadata_reflected": True}]},
                "memory": {"written": [{"status": "accepted_pending"}]},
            },
        }

    def status(self, run_id):
        return {"run_id": run_id, "status": "completed", "quality_status": "passed"}

    def evidence(self, run_id):
        return {
            "schema_version": "across-loop-evidence/1.0",
            "run_id": run_id,
            "spec_id": "aaa-autonomous-self-iteration",
            "status": "completed",
            "gates": [{"id": "candidate_validation_passed", "status": "passed", "required": True}],
            "candidate": {
                "candidate_id": "candidate-api-1",
                "promotion_ready": True,
                "changed_files": ["across-agents-assistant/backend/src/across_agents_assistant/example.py"],
                "validation": {"status": "passed", "commands": [{"status": "passed"}]},
                "semantic_alignment_status": "passed",
                "self_hosting_probe": {"required": True, "status": "passed"},
                "quality_findings": [],
                "independent_reviewer": {
                    "product_value_score": 90,
                    "maintainability_score": 92,
                    "risk_score": 8,
                    "merge_recommendation": "open_review_pr",
                    "model_separation": {"required": True, "status": "passed"},
                },
                "promotion_package": {
                    "candidate_id": "candidate-api-1",
                    "source_a_unchanged": True,
                    "source_ref_pins": {
                        "schema_version": "across-autopilot-source-ref-pins/1.0",
                        "status": "passed",
                        "repos": [
                            {"id": "across-agents-assistant", "source_head_pre": "aaa-head", "source_unchanged": True},
                            {"id": "across-orchestrator", "source_head_pre": "orch-head", "source_unchanged": True},
                            {"id": "across-context", "source_head_pre": "ctx-head", "source_unchanged": True},
                            {"id": "across-autopilot", "source_head_pre": "auto-head", "source_unchanged": True},
                        ],
                        "missing_required_repos": [],
                        "missing_pins": [],
                        "changed_sources": [],
                    },
                    "promotion_ready": True,
                    "reviewer_scores": {
                        "product_value_score": 90,
                        "maintainability_score": 92,
                        "risk_score": 8,
                        "merge_recommendation": "open_review_pr",
                    },
                    "recommended_pr": {"title": "Review: candidate-api-1"},
                    "known_risks": [],
                },
            },
            "outputs": [{"id": "markdown_report", "path": "/tmp/report.md"}],
        }

    def events(self, run_id, *, after_sequence=None):
        return [{"sequence": 2, "event": "run.completed", "run_id": run_id, "after": after_sequence}]

    def list_runs(self):
        return {"runs": [{"run_id": "run-api-1", "status": "completed"}]}

    def telemetry(self):
        return {"schema_version": "across-autopilot-telemetry/1.0", "runs": {"total": 1, "completed": 1}}

    def cancel(self, run_id, *, reason="cancelled by host"):
        return {"run_id": run_id, "status": "cancelled", "reason": reason}

    def retry(self, run_id):
        return {"run": {"run_id": "run-api-2", "previous_run_id": run_id, "status": "completed"}}

    def set_spec_paused(self, spec_id, paused):
        return {"spec_id": spec_id, "paused": paused}

    def set_adapter_paused(self, adapter_id, paused):
        return {"adapter_id": adapter_id, "paused": paused}

    def quarantine_output(self, run_id, output_id):
        return {"run_id": run_id, "output_id": output_id, "quarantined": True}

    def enqueue_trigger(
        self,
        spec,
        *,
        trigger_type="manual",
        payload=None,
        idempotency_key=None,
        not_before=None,
        source="aaa",
        actor="user",
    ):
        return {
            "trigger_id": "trg-api-1",
            "spec_id": spec,
            "status": "pending",
            "trigger_event": {
                "type": trigger_type,
                "payload": payload or {},
                "source": source,
                "actor": actor,
                "idempotency_key": idempotency_key,
                "not_before": not_before,
            },
        }

    def trigger_queue(self):
        return {"schema_version": "across-autopilot-trigger-queue/1.0", "items": [{"trigger_id": "trg-api-1"}]}

    def run_trigger(self, trigger_id=None):
        return {"status": "completed", "trigger": {"trigger_id": trigger_id or "trg-api-1"}}


def test_autopilot_code_iteration_prompt_blocks_token_shaped_test_fixtures():
    prompt = api_server._autopilot_code_iteration_system_prompt(direct_patches=True)

    assert "including tests or examples" in prompt
    assert "sk-" in prompt
    assert "ghp_" in prompt
    assert "token=" in prompt
    assert "api_key=" in prompt


class DispatchingFakeAutopilotClient:
    def __init__(self):
        self.items = []
        self.run_trigger_calls = []

    def enqueue_trigger(
        self,
        spec,
        *,
        trigger_type="manual",
        payload=None,
        idempotency_key=None,
        not_before=None,
        source="aaa",
        actor="user",
    ):
        item = {
            "trigger_id": f"trg-dispatch-{len(self.items) + 1}",
            "spec_id": spec,
            "status": "pending",
            "not_before": not_before,
            "trigger_event": {
                "type": trigger_type,
                "payload": payload or {},
                "source": source,
                "actor": actor,
                "idempotency_key": idempotency_key,
            },
        }
        self.items.append(item)
        return item

    def trigger_queue(self):
        return {"schema_version": "across-autopilot-trigger-queue/1.0", "items": list(self.items)}

    def run_trigger(self, trigger_id=None):
        self.run_trigger_calls.append(trigger_id)
        for item in self.items:
            if item["trigger_id"] == trigger_id:
                item["status"] = "completed"
                item["run_id"] = f"run-{trigger_id}"
                return {"status": "completed", "trigger": {"trigger_id": trigger_id}, "run": {"run_id": item["run_id"]}}
        return {"status": "idle", "trigger": {"trigger_id": trigger_id}}


def test_autopilot_trigger_scheduler_dispatches_due_queue_items(tmp_path):
    registry = AutopilotTriggerRegistry(tmp_path / "trigger-registry.json")
    registry.register(
        spec="aaa-autonomous-self-iteration",
        trigger_type="cron",
        schedule={"interval_seconds": 60},
        payload={"reason": "scheduler-dispatch"},
        actor="pytest",
        source="scheduler-test",
        trigger_id="daily-self-iteration",
    )
    fake_client = DispatchingFakeAutopilotClient()
    scheduler = AutopilotTriggerScheduler(
        registry,
        lambda: fake_client,
        run_queued_triggers=True,
        max_runs_per_tick=1,
    )

    tick = scheduler.tick_once()

    assert tick["status"] == "dispatched"
    assert tick["enqueued"][0]["trigger_id"] == "trg-dispatch-1"
    assert tick["dispatch"]["items"][0]["trigger_id"] == "trg-dispatch-1"
    assert tick["dispatch"]["items"][0]["run_id"] == "run-trg-dispatch-1"
    assert fake_client.items[0]["status"] == "completed"
    status = scheduler.status()
    assert status["last_tick_status"] == "dispatched"
    assert status["last_dispatch_count"] == 1


def test_autopilot_trigger_scheduler_skips_stale_due_queue_items(tmp_path):
    registry = AutopilotTriggerRegistry(tmp_path / "trigger-registry.json")
    fake_client = DispatchingFakeAutopilotClient()
    fake_client.items.append(
        {
            "trigger_id": "trg-stale-1",
            "spec_id": "aaa-platform-self-repair",
            "status": "pending",
            "not_before": "2000-01-01T00:00:00Z",
            "enqueued_at": "2000-01-01T00:00:00Z",
        }
    )
    scheduler = AutopilotTriggerScheduler(
        registry,
        lambda: fake_client,
        run_queued_triggers=True,
        max_runs_per_tick=1,
    )

    tick = scheduler.tick_once()

    assert tick["status"] == "idle"
    assert tick["dispatch"]["items"] == []
    assert tick["dispatch"]["skipped_stale"][0]["trigger_id"] == "trg-stale-1"
    assert fake_client.run_trigger_calls == []
    status = scheduler.status()
    assert status["last_dispatch_count"] == 0
    assert status["last_dispatch_status"] == "idle"


def test_daily_cron_trigger_runs_at_configured_local_time(tmp_path):
    registry = AutopilotTriggerRegistry(tmp_path / "trigger-registry.json")
    registry.register(
        spec="aaa-autonomous-self-iteration",
        trigger_type="cron",
        schedule={"interval_seconds": 86400, "daily_time": "10:00", "timezone": "Asia/Shanghai"},
        payload={"reason": "daily-self-iteration"},
        actor="pytest",
        source="scheduler-test",
        trigger_id="daily-self-iteration",
    )
    fake_client = DispatchingFakeAutopilotClient()

    before_due = registry.tick(fake_client, now=_local_ts(2026, 7, 4, 9, 59))

    assert before_due["status"] == "idle"
    assert before_due["inspected"][0]["status"] == "not_due"
    assert before_due["inspected"][0]["next_due_at"] == "2026-07-04T02:00:00Z"
    assert fake_client.items == []

    due = registry.tick(fake_client, now=_local_ts(2026, 7, 4, 10, 0))

    assert due["status"] == "enqueued"
    assert due["inspected"][0]["status"] == "due"
    assert due["inspected"][0]["scheduled_for"] == "2026-07-04T02:00:00Z"
    assert fake_client.items[0]["trigger_event"]["idempotency_key"] == "daily-self-iteration:daily:2026-07-04T10:00+0800"
    assert fake_client.items[0]["not_before"] == "2026-07-04T02:00:00Z"

    same_day = registry.tick(fake_client, now=_local_ts(2026, 7, 4, 10, 1))

    assert same_day["status"] == "idle"
    assert same_day["inspected"][0]["status"] == "not_due"
    assert same_day["inspected"][0]["next_due_at"] == "2026-07-05T02:00:00Z"
    assert len(fake_client.items) == 1


def test_daily_cron_trigger_catches_up_after_configured_time(tmp_path):
    registry = AutopilotTriggerRegistry(tmp_path / "trigger-registry.json")
    registry.register(
        spec="aaa-autonomous-self-iteration",
        trigger_type="cron",
        schedule={"interval_seconds": 86400, "daily_time": "10:00", "timezone": "Asia/Shanghai"},
        payload={"reason": "daily-self-iteration"},
        actor="pytest",
        source="scheduler-test",
        trigger_id="daily-self-iteration",
    )
    fake_client = DispatchingFakeAutopilotClient()

    late = registry.tick(fake_client, now=_local_ts(2026, 7, 4, 11, 30))

    assert late["status"] == "enqueued"
    assert late["inspected"][0]["scheduled_for"] == "2026-07-04T02:00:00Z"
    assert fake_client.items[0]["not_before"] == "2026-07-04T02:00:00Z"


def _local_ts(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()


def test_autopilot_control_plane_endpoints(monkeypatch, tmp_path):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "aaa-home"))
    monkeypatch.setattr(api_server, "get_autopilot_client", lambda: FakeAutopilotClient())
    monkeypatch.setattr(
        api_server,
        "get_source_mirror_status",
        lambda: {
            "schema_version": "across-source-mirror-status/1.0",
            "status": "passed",
            "root": str(tmp_path / "source-mirrors"),
            "missing_repos": [],
            "drifted_repos": [],
            "repos": [],
        },
    )
    client = TestClient(app)

    registry = client.get("/api/autopilot/registry")
    assert registry.status_code == 200
    assert registry.json()["built_in"][0]["id"] == "daily-news-brief"

    validate = client.post("/api/autopilot/specs/validate", json={"spec": "daily-news-brief"})
    assert validate.status_code == 200
    assert validate.json()["valid"] is True

    dry_run = client.post("/api/autopilot/specs/dry-run", json={"spec": "daily-news-brief"})
    assert dry_run.status_code == 200
    assert dry_run.json()["adapters"]["actions"] == ["report_generation"]

    trigger = client.post(
        "/api/autopilot/triggers",
        json={
            "spec": "daily-news-brief",
            "type": "cron",
            "payload": {"reason": "smoke"},
            "idempotency_key": "daily-news-brief:smoke",
        },
    )
    assert trigger.status_code == 200
    assert trigger.json()["trigger_event"]["type"] == "cron"
    assert client.get("/api/autopilot/triggers").json()["items"][0]["trigger_id"] == "trg-api-1"
    assert client.post("/api/autopilot/triggers/run", json={"trigger_id": "trg-api-1"}).json()["status"] == "completed"

    trigger_config = client.post(
        "/api/autopilot/trigger-configs",
        json={
            "spec": "daily-news-brief",
            "type": "cron",
            "payload": {"reason": "test"},
            "schedule": {"interval_seconds": 3600},
            "source": "test",
            "actor": "pytest",
        },
    )
    assert trigger_config.status_code == 200
    trigger_id = trigger_config.json()["trigger_id"]
    assert client.get("/api/autopilot/trigger-configs").json()["triggers"][0]["trigger_id"] == trigger_id
    tick = client.post("/api/autopilot/trigger-configs/tick")
    assert tick.status_code == 200
    assert tick.json()["status"] == "enqueued"
    assert tick.json()["enqueued"][0]["trigger_id"] == "trg-api-1"
    scheduler_status = client.get("/api/autopilot/trigger-scheduler")
    assert scheduler_status.status_code == 200
    assert scheduler_status.json()["running"] is False
    scheduler_started = client.post(
        "/api/autopilot/trigger-scheduler/start",
        json={"interval_seconds": 5, "run_queued_triggers": False, "max_runs_per_tick": 2},
    )
    assert scheduler_started.status_code == 200
    assert scheduler_started.json()["running"] is True
    assert scheduler_started.json()["run_queued_triggers"] is False
    assert scheduler_started.json()["max_runs_per_tick"] == 2
    scheduler_reconfigured = client.post(
        "/api/autopilot/trigger-scheduler/start",
        json={"run_queued_triggers": True, "max_runs_per_tick": 3},
    )
    assert scheduler_reconfigured.status_code == 200
    assert scheduler_reconfigured.json()["running"] is True
    assert scheduler_reconfigured.json()["run_queued_triggers"] is True
    assert scheduler_reconfigured.json()["max_runs_per_tick"] == 3
    scheduler_stopped = client.post("/api/autopilot/trigger-scheduler/stop")
    assert scheduler_stopped.status_code == 200
    assert scheduler_stopped.json()["running"] is False
    paused = client.patch(f"/api/autopilot/trigger-configs/{trigger_id}/pause", json={"paused": True})
    assert paused.status_code == 200
    assert paused.json()["paused"] is True

    webhook_config = client.post(
        "/api/autopilot/trigger-configs",
        json={
            "spec": "daily-news-brief",
            "type": "webhook",
            "payload": {"reason": "test-webhook"},
            "source": "test-webhook",
            "actor": "pytest",
        },
    ).json()
    webhook = client.post(
        f"/api/autopilot/webhooks/{webhook_config['trigger_id']}",
        json={"event": "push"},
        headers={"x-across-delivery": "delivery-1"},
    )
    assert webhook.status_code == 200
    assert webhook.json()["status"] == "accepted"
    assert webhook.json()["queued"]["trigger_id"] == "trg-api-1"

    self_plan_initial = client.get("/api/autopilot/self-iteration-plan")
    assert self_plan_initial.status_code == 200
    assert self_plan_initial.json()["schema_version"] == "across-aaa-self-iteration-plan/1.0"
    self_plan = client.post(
        "/api/autopilot/self-iteration-plan/ensure",
        json={"spec": "aaa-autonomous-self-iteration", "interval_seconds": 3600, "actor": "pytest"},
    )
    assert self_plan.status_code == 200
    assert self_plan.json()["status"] == "active"
    assert self_plan.json()["trigger"]["trigger_id"] == "aaa-continuous-self-iteration-daily"
    assert self_plan.json()["trigger"]["schedule"]["interval_seconds"] == 3600
    assert self_plan.json()["trigger"]["schedule"]["daily_time"] == "10:00"
    assert self_plan.json()["trigger"]["schedule"]["timezone"] == "Asia/Shanghai"
    assert self_plan.json()["ready"] is True
    assert self_plan.json()["platform_self_repair"]["spec"] == "aaa-platform-self-repair"
    assert self_plan.json()["platform_self_repair"]["promotion_review_required"] is True
    assert self_plan.json()["source_mirrors"]["status"] == "passed"
    assert self_plan.json()["runtime_controls"]["scheduler_dispatch_mode"] == "enqueue_and_run_one_due_trigger_per_tick"

    run = client.post(
        "/api/autopilot/runs",
        json={
            "spec": "daily-news-brief",
            "trigger": "user-e2e",
            "model_policy_overrides": {
                "builder": {"agent_id": "codex", "provider": "local-agent", "model": "codex"},
                "reviewer": {"agent_id": "codex", "provider": "local-agent", "model": "codex", "require_distinct_from_builder": False},
            },
        },
    )
    assert run.status_code == 200
    body = run.json()
    assert body["run"]["run_id"] == "run-api-1"
    assert body["evidence"]["orchestrator"]["tasks"][0]["metadata_reflected"] is True
    assert body["evidence"]["model_policy_overrides"]["builder"]["model"] == "codex"
    assert body["evidence"]["model_policy_overrides"]["reviewer"]["model"] == "codex"
    assert body["evidence"]["memory"]["written"][0]["status"] == "accepted_pending"

    assert client.get("/api/autopilot/runs").json()["runs"][0]["run_id"] == "run-api-1"
    assert client.get("/api/autopilot/runs/run-api-1").json()["quality_status"] == "passed"
    assert client.get("/api/autopilot/runs/run-api-1/evidence").json()["outputs"][0]["id"] == "markdown_report"
    promotion = client.get("/api/autopilot/runs/run-api-1/promotion-review").json()
    assert promotion["schema_version"] == "across-autopilot-promotion-review/1.0"
    assert promotion["status"] == "ready_for_human_review"
    assert promotion["source_ref_pins"]["status"] == "passed"
    assert promotion["promotion_attestation"]["schema_version"] == "across-autopilot-promotion-attestation/1.0"
    assert promotion["promotion_attestation"]["digest_status"] == "passed"
    assert promotion["promotion_attestation"]["merge_release_signing_blocked"] is True
    assert any(item["id"] == "source_refs_pinned" and item["status"] == "passed" for item in promotion["checklist"])
    assert any(item["id"] == "promotion_attestation_present" and item["status"] == "passed" for item in promotion["checklist"])
    assert promotion["allowed_actions"]["open_review_pr"] is True
    assert promotion["allowed_actions"]["merge"] is False
    assert client.get("/api/autopilot/runs/run-api-1/events", params={"after_sequence": 1}).json()[0]["after"] == 1
    assert client.get("/api/autopilot/telemetry").json()["runs"]["completed"] == 1
    ops = client.get("/api/autopilot/ops-dashboard")
    assert ops.status_code == 200
    assert ops.json()["schema_version"] == "across-aaa-loop-engineering-ops-dashboard/1.0"
    assert ops.json()["trigger_scheduler"]["running"] is False
    assert ops.json()["summary"]["capability_ready_count"] >= 41
    assert ops.json()["triggers"]["total"] >= 3
    assert ops.json()["self_iteration_plan"]["status"] == "active"

    cancelled = client.post("/api/autopilot/runs/run-api-1/cancel", json={"reason": "user request"})
    assert cancelled.json()["reason"] == "user request"
    assert client.post("/api/autopilot/runs/run-api-1/retry").json()["run"]["previous_run_id"] == "run-api-1"
    assert client.post("/api/autopilot/specs/daily-news-brief/pause").json()["paused"] is True
    assert client.post("/api/autopilot/specs/daily-news-brief/resume").json()["paused"] is False
    assert client.post("/api/autopilot/adapters/url/pause").json()["paused"] is True
    assert client.post("/api/autopilot/adapters/url/resume").json()["paused"] is False
    quarantined = client.post(
        "/api/autopilot/runs/run-api-1/outputs/quarantine",
        json={"outputId": "markdown_report"},
    )
    assert quarantined.json()["quarantined"] is True
    deleted = client.delete(f"/api/autopilot/trigger-configs/{trigger_id}")
    assert deleted.json()["deleted"] is True


def test_promotion_review_marks_source_boundary_not_evaluable_without_package():
    packet = build_promotion_review_packet(
        {
            "schema_version": "across-loop-evidence/1.0",
            "run_id": "run-missing-package",
            "spec_id": "aaa-autonomous-self-iteration",
            "gates": [{"id": "candidate_app_lifecycle_passed", "status": "failed", "required": True}],
            "candidate": {
                "candidate_id": "candidate-missing-package",
                "promotion_ready": False,
                "changed_files": ["across-agents-assistant/backend/src/across_agents_assistant/example.py"],
                "validation": {"status": "passed"},
                "self_hosting_probe": {"required": True, "status": "skipped"},
                "quality_findings": [],
            },
        }
    )

    checklist = {item["id"]: item for item in packet["checklist"]}
    assert packet["status"] == "needs_attention"
    assert checklist["promotion_package_present"]["status"] == "failed"
    assert checklist["source_a_unchanged"]["status"] == "not_evaluable"
    assert checklist["source_a_unchanged"]["details"]["reason"] == "not evaluated because no promotion package was generated"
    assert checklist["source_refs_pinned"]["status"] == "not_evaluable"


def test_trigger_registry_syncs_terminal_queue_status(tmp_path):
    registry = AutopilotTriggerRegistry(tmp_path / "registry.json")
    record = registry.ensure(
        spec="aaa-autonomous-self-iteration",
        trigger_type="cron",
        trigger_id="aaa-continuous-self-iteration-daily",
        payload={"scenario": "self"},
        schedule={"interval_seconds": 60},
    )
    state = registry._load()
    state["triggers"][0]["last_trigger_id"] = "trg-terminal"
    state["triggers"][0]["last_status"] = "pending"
    registry._save(state)

    synced = registry.list_synced(
        {
            "items": [
                {
                    "trigger_id": "trg-terminal",
                    "status": "failed",
                    "completed_at": "2026-06-30T18:24:12Z",
                    "failure": {
                        "adapter_id": "candidate_app_lifecycle",
                        "code": 1,
                        "message": "candidate app lifecycle failed",
                        "private": "ignored",
                    },
                }
            ]
        }
    )

    trigger = synced["triggers"][0]
    assert record["trigger_id"] == "aaa-continuous-self-iteration-daily"
    assert trigger["last_status"] == "failed"
    assert trigger["last_completed_at"] == "2026-06-30T18:24:12Z"
    assert trigger["last_failure"] == {
        "adapter_id": "candidate_app_lifecycle",
        "code": 1,
        "message": "candidate app lifecycle failed",
    }


def test_autopilot_client_prefers_source_mirrors(tmp_path, monkeypatch):
    across_home = tmp_path / "across"
    mirror_root = across_home / "data" / "across-autopilot" / "source-mirrors"
    for repo in ["across-agents-assistant", "across-orchestrator", "across-context", "across-autopilot"]:
        repo_root = mirror_root / repo
        (repo_root / ".git").mkdir(parents=True)
    monkeypatch.setenv("ACROSS_HOME", str(across_home))
    for key in [
        "ACROSS_AGENTS_ASSISTANT_SOURCE",
        "ACROSS_ORCHESTRATOR_SOURCE",
        "ACROSS_CONTEXT_SOURCE",
        "ACROSS_AUTOPILOT_SOURCE",
    ]:
        monkeypatch.delenv(key, raising=False)

    env = AutopilotClient()._runtime_env()

    assert env["ACROSS_AUTOPILOT_SOURCE_MIRRORS_ACTIVE"] == "across-agents-assistant,across-orchestrator,across-context,across-autopilot"
    assert Path(env["ACROSS_AGENTS_ASSISTANT_SOURCE"]) == mirror_root / "across-agents-assistant"
    assert Path(env["ACROSS_ORCHESTRATOR_SOURCE"]) == mirror_root / "across-orchestrator"
    assert Path(env["ACROSS_CONTEXT_SOURCE"]) == mirror_root / "across-context"
    assert Path(env["ACROSS_AUTOPILOT_SOURCE"]) == mirror_root / "across-autopilot"
    assert "autopilot-research-decision" in env["ACROSS_AAA_HOST_RESEARCH_COMMAND"]
    assert "autopilot-review-decision" in env["ACROSS_AAA_HOST_REVIEW_COMMAND"]
    lifecycle_command = json.loads(env["ACROSS_AAA_CANDIDATE_APP_LIFECYCLE_COMMAND"])
    assert lifecycle_command[0] == "bash"
    assert lifecycle_command[1].endswith("scripts/candidate_app_lifecycle.sh")


def test_autopilot_client_passes_candidate_model_lease_without_raw_keys(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "should-not-reach-autopilot")
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-reach-autopilot")
    monkeypatch.setenv("ACROSS_AAA_HOST_HTTP_URL", "http://127.0.0.1:45678")

    env = AutopilotClient()._runtime_env()
    lease = json.loads(env["ACROSS_AAA_CANDIDATE_MODEL_LEASE_JSON"])
    lease_text = json.dumps(lease, sort_keys=True)

    assert "MINIMAX_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    assert "should-not-reach-autopilot" not in lease_text
    assert lease["schema_version"] == "across-candidate-model-lease/1.0"
    assert lease["policy"]["secrets_included"] is False
    assert lease["policy"]["raw_credentials_allowed"] is False
    assert lease["host_http_url"] == "http://127.0.0.1:45678"
    assert "model.code_patch" in lease["scopes"]


def test_autopilot_host_requests_normalize_null_candidate_model_lease():
    assert api_server.AutopilotModelDecisionRequest(
        goal="Patch safely.",
        candidate_workspace="/tmp/candidate",
        candidate_model_lease=None,
    ).candidate_model_lease == {}
    assert api_server.AutopilotResearchDecisionRequest(
        goal="Pick direction.",
        candidate_workspace="/tmp/candidate",
        candidate_model_lease=None,
    ).candidate_model_lease == {}
    assert api_server.AutopilotCodeIterationRequest(
        goal="Implement direction.",
        candidate_workspace="/tmp/candidate",
        candidate_model_lease=None,
    ).candidate_model_lease == {}
    assert api_server.AutopilotReviewDecisionRequest(
        goal="Review candidate.",
        candidate_model_lease=None,
    ).candidate_model_lease == {}


def test_autopilot_client_passes_model_overrides(monkeypatch):
    observed = {}
    monkeypatch.setenv("ACROSS_AAA_SOURCE_MIRROR_REFRESH", "0")
    monkeypatch.setenv("ACROSS_AAA_CANDIDATE_RETENTION", "0")

    def fake_run_autopilot_cli_json(args, env=None, timeout=60):
        observed["args"] = args
        observed["timeout"] = timeout
        return {"run": {"status": "completed"}}

    monkeypatch.setattr(
        "across_agents_assistant.autopilot_client.run_autopilot_cli_json",
        fake_run_autopilot_cli_json,
    )

    AutopilotClient().run(
        "aaa-autonomous-self-iteration",
        trigger="test",
        model_policy_overrides={
            "builder": {"agent_id": "codex", "provider": "local-agent", "model": "codex"},
            "reviewer": {"agent_id": "codex", "provider": "local-agent", "model": "codex", "require_distinct_from_builder": False},
        },
    )

    assert "--model-overrides-json" in observed["args"]
    payload = json.loads(observed["args"][observed["args"].index("--model-overrides-json") + 1])
    assert payload["builder"]["agent_id"] == "codex"
    assert payload["builder"]["model"] == "codex"
    assert payload["reviewer"]["agent_id"] == "codex"
    assert payload["reviewer"]["model"] == "codex"
    assert payload["reviewer"]["require_distinct_from_builder"] is False
    assert observed["timeout"] == 7200


def test_autopilot_client_long_run_timeout_is_configurable(monkeypatch):
    monkeypatch.setenv("ACROSS_AAA_AUTOPILOT_RUN_TIMEOUT_SECONDS", "2400")
    assert _long_run_timeout_seconds() == 2400

    monkeypatch.setenv("ACROSS_AAA_AUTOPILOT_RUN_TIMEOUT_SECONDS", "not-a-number")
    assert _long_run_timeout_seconds() == 7200

    assert _long_run_timeout_seconds({"ACROSS_AAA_AUTOPILOT_RUN_TIMEOUT_SECONDS": "12"}) == 600
    assert _long_run_timeout_seconds({"ACROSS_AAA_AUTOPILOT_RUN_TIMEOUT_SECONDS": "99999"}) == 7200


def test_autopilot_unavailable_is_503(monkeypatch):
    class MissingAutopilot:
        def registry(self):
            raise PluginLifecycleError("across-autopilot plugin is not installed")

    monkeypatch.setattr(api_server, "get_autopilot_client", lambda: MissingAutopilot())

    response = TestClient(app).get("/api/autopilot/registry")

    assert response.status_code == 503
    assert response.json()["detail"] == "Across Autopilot plugin is not available"


def test_loop_engineering_capability_pack_endpoint():
    response = TestClient(app).get("/api/autopilot/capability-packs")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "across-aaa-loop-engineering-capability-pack/1.0"
    assert body["ready_count"] >= 43
    ids = {item["id"] for item in body["ready"]}
    assert "runtime_policy_contract" in ids
    assert "capability_preflight" in ids
    assert "runtime_budget_enforcement" in ids
    assert "trigger_registry_api" in ids
    assert "continuous_self_iteration_plan" in ids
    assert "webhook_receiver" in ids
    assert "dependency_security_review" in ids
    assert "license_policy_scan" in ids
    assert "repo_quality_inspection" in ids
    assert "source_research_digest" in ids
    assert "source_signal_synthesizer" in ids
    assert "model_generated_fallback_plan" in ids
    assert "multi_candidate_comparison" in ids
    assert "distinct_model_acceptance" in ids
    assert "promotion_attestation" in ids
    assert "promotion_human_review" in ids
    assert "ops_dashboard" in ids
    assert "loop_capability_audit_skill" in ids
    assert "e2e_failure_triage_skill" in ids
    assert "unified_capability_registry" in ids
    assert "mcp_tool_manifest_endpoint" in ids
    assert "a2a_capability_card_endpoint" in ids
    assert body["skill_candidate_count"] == 0
    assert "fallback" in body["policy"]
    assert body["policy"]["promotion"].startswith("commit")
    assert body["ai_ready_context"]["schema_version"] == "across-aaa-ai-ready-context/1.0"
    assert body["ai_ready_context"]["policy"]["raw_secrets_excluded"] is True


def test_autopilot_tool_manifest_endpoint_exposes_runtime_tools_and_resources():
    response = TestClient(app).get("/api/autopilot/tool-manifest")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "across-aaa-mcp-tool-manifest/1.0"
    assert body["policy"]["human_promotion_required"] is True
    assert body["summary"]["tool_count"] >= 1
    assert body["summary"]["resource_count"] >= 1
    resource_uris = {item["uri"] for item in body["resources"]}
    assert "across://capabilities/continuous_self_iteration_plan" in resource_uris
    assert "across://capabilities/mcp_tool_manifest_endpoint" in resource_uris
    assert body["prompts"][0]["name"] == "aaa_autonomous_self_iteration"


def test_autopilot_a2a_capability_card_endpoint_exposes_human_gated_agent_card():
    response = TestClient(app).get("/api/autopilot/a2a/capability-card")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "across-aaa-a2a-capability-card/1.0"
    assert body["agent"]["id"] == "aaa-autonomous-self-iteration"
    assert body["protocol_projection"]["endpoints"]["tool_manifest"] == "/api/autopilot/tool-manifest"
    assert body["safety"]["merge_release_signing_blocked"] is True
    assert body["summary"]["human_review_required"] is True
    capability_ids = {item["id"] for item in body["capabilities"]}
    assert "candidate_workspace" in capability_ids
    assert "promotion_attestation" in capability_ids


def test_agent_interop_e2e_endpoints(monkeypatch):
    payload = {
        "schema_version": "across-aaa-agent-interop-e2e/1.0",
        "status": "passed",
        "summary": {"passed_count": 11, "failed_count": 0, "host_target_count": 5, "mcp_server_count": 3},
        "checks": [{"id": "three_plugin_mcp_load", "status": "passed"}],
        "errors": [],
    }
    monkeypatch.setattr(api_server, "load_agent_interop_e2e_latest", lambda: payload)
    monkeypatch.setattr(api_server, "run_agent_interop_e2e", lambda: payload)
    client = TestClient(app)

    latest = client.get("/api/autopilot/agent-interop-e2e")
    assert latest.status_code == 200
    assert latest.json()["schema_version"] == "across-aaa-agent-interop-e2e/1.0"

    run = client.post("/api/autopilot/agent-interop-e2e")
    assert run.status_code == 200
    assert run.json()["status"] == "passed"
    assert run.json()["summary"]["mcp_server_count"] == 3


def test_unified_capability_registry_endpoint_preserves_product_boundaries(monkeypatch):
    monkeypatch.setattr(
        api_server,
        "_runtime_tool_schemas",
        lambda: [
            {
                "name": "read_file",
                "description": "Read a local file",
                "risk_level": "low",
            }
        ],
    )
    monkeypatch.setattr(
        api_server,
        "discover_across_plugins",
        lambda *args, **kwargs: [
            {
                "plugin_id": "across-autopilot",
                "display_name": "Across Autopilot",
                "kind": "autonomous-workflow",
                "status": "installed",
                "installed": True,
                "available": True,
                "capabilities": {
                    "loop_specs": {
                        "name": "LoopSpecs",
                        "description": "Run reusable autonomous workflows.",
                    }
                },
            }
        ],
    )
    monkeypatch.setattr(api_server, "_provider_has_backend_key", lambda provider_id: provider_id == "minimax")

    response = TestClient(app).get("/api/capability-registry")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "across-unified-capability-registry/1.0"
    assert body["security"]["secrets_included"] is False
    assert body["security"]["custom_instructions_included"] is False
    assert body["security"]["credential_fields_redacted"] is True
    assert body["security"]["execution_boundaries_preserved"] is True
    assert body["integration_policy"]["frontend_pages_can_remain_separate"] is True
    provider_ids = {provider["id"] for provider in body["providers"]}
    assert "across-agents-assistant" in provider_ids
    assert "across-autopilot" in provider_ids
    capabilities = {capability["id"]: capability for capability in body["capabilities"]}
    fallback = capabilities["autopilot.tool_pack.model_generated_fallback_plan"]
    assert fallback["executor"] == "across-autopilot"
    assert fallback["provider"] == "across-autopilot"
    assert fallback["loop_callable"] is True
    assert fallback["user_callable"] is False
    aaa_tool = capabilities["aaa.tool.read_file"]
    assert aaa_tool["executor"] == "across-agents-assistant"
    assert aaa_tool["user_callable"] is True
    assert any(model["provider"] == "minimax" and model["model"] == "MiniMax-M3" for model in body["models"])
    assert body["summary"]["kind_counts"]["tool_pack"] >= 1

    health = TestClient(app).get("/api/capability-registry/health")
    assert health.status_code == 200
    health_body = health.json()
    assert health_body["schema_version"] == "across-unified-capability-registry-health/1.0"
    assert health_body["status"] == "passed"
    assert health_body["compatibility"]["schema_family"] == "across-unified-capability-registry"


def test_autopilot_model_decision_endpoint_returns_structured_model_patch(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class FakeGateway:
        async def chat(self, **kwargs):
            return SimpleNamespace(
                text=(
                    '{"summary":"Improve self-iteration evidence","rationale":"Keep the change candidate-only",'
                    '"risk":"low","patches":[{"path":"docs/ITERATION.md","mode":"overwrite",'
                    '"content":"# Iteration\\nModel-backed patch\\n"}],'
                    '"validation_commands":[{"command":"git","args":["diff","--check"]}]}'
                ),
                provider="fake-provider",
                model="fake-model",
                finish_reason="stop",
                usage={"total_tokens": 42},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: FakeGateway())
    response = TestClient(app).post("/api/autopilot/model-decision", json={
        "goal": "Plan an AAA candidate-only iteration",
        "candidate_workspace": str(candidate),
        "allowed_patch_paths": ["docs/ITERATION.md"],
        "context_files": ["README.md"],
        "model_policy": {"required": True, "provider": "fake"},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "across-host-model-decision/1.0"
    assert body["model_backed"] is True
    assert body["provider"] == "fake-provider"
    assert body["model"] == "fake-model"
    assert body["patches"][0]["path"] == "docs/ITERATION.md"
    assert body["decision_hash"]
    assert body["repaired_json"] is False
    assert body["text_fallback"] is False
    assert body["context"]["file_count"] == 0
    assert body["context"]["files"] == []


def test_candidate_llm_chat_uses_model_lease_without_local_key(monkeypatch, tmp_path):
    socket_path = tmp_path / "stable-a.sock"
    socket_path.write_text("", encoding="utf-8")
    lease_path = tmp_path / "candidate-model-lease.json"
    lease_path.write_text(json.dumps({
        "schema_version": "across-candidate-model-lease/1.0",
        "lease_id": "lease-test",
        "candidate_id": "candidate-b",
        "host_socket": str(socket_path),
        "scopes": ["model.chat", "model.decide", "model.code_patch"],
        "expires_at_unix": 9999999999,
        "policy": {
            "secrets_included": False,
            "raw_credentials_allowed": False,
            "candidate_may_store_raw_credentials": False,
        },
    }), encoding="utf-8")
    monkeypatch.setenv("ACROSS_AAA_CANDIDATE_MODEL_LEASE", str(lease_path))

    class FakeAdapter:
        def is_available(self):
            return False

    class FakeGateway:
        _adapters = {"minimax": FakeAdapter()}

        def get_current_provider_id(self):
            return "minimax"

        def get_current_adapter(self):
            return self._adapters["minimax"]

        async def chat(self, **_kwargs):
            raise RuntimeError("No API key found for minimax")

    proxied = {}

    def fake_post(socket, path, payload, *, timeout=180.0):
        proxied["socket"] = socket
        proxied["path"] = path
        proxied["payload"] = payload
        return {
            "text": "lease-backed response",
            "model": "MiniMax-M3",
            "provider": "minimax",
            "finish_reason": "stop",
            "usage": {"total_tokens": 4},
        }

    monkeypatch.setattr(api_server, "get_gateway", lambda: FakeGateway())
    monkeypatch.setattr(api_server, "_post_json_to_unix_socket", fake_post)

    client = TestClient(app)
    status = client.get("/api/llm/status").json()
    chat = client.post("/api/llm/chat", json={"message": "ping", "provider_id": "minimax"}).json()

    assert status["available"] is True
    assert status["availability_source"] == "candidate_model_lease"
    assert status["candidate_model_lease"]["lease_id"] == "lease-test"
    assert chat["text"] == "lease-backed response"
    assert chat["provider"] == "minimax"
    assert proxied["socket"] == str(socket_path)
    assert proxied["path"] == "/api/llm/chat"
    assert proxied["payload"]["message"] == "ping"


def test_candidate_llm_status_prefers_http_model_lease_over_local_credentials(monkeypatch, tmp_path):
    lease_path = tmp_path / "candidate-model-lease.json"
    lease_path.write_text(json.dumps({
        "schema_version": "across-candidate-model-lease/1.0",
        "lease_id": "lease-http-test",
        "candidate_id": "candidate-b",
        "host_http_url": "http://127.0.0.1:45678",
        "scopes": ["model.chat"],
        "expires_at_unix": 9999999999,
        "policy": {
            "secrets_included": False,
            "raw_credentials_allowed": False,
            "candidate_may_store_raw_credentials": False,
        },
    }), encoding="utf-8")
    monkeypatch.setenv("ACROSS_AAA_CANDIDATE_MODEL_LEASE", str(lease_path))

    class AvailableAdapter:
        def is_available(self):
            return True

    class FakeGateway:
        _adapters = {"minimax": AvailableAdapter()}

        def get_current_provider_id(self):
            return "minimax"

        def get_current_adapter(self):
            return self._adapters["minimax"]

        async def chat(self, **_kwargs):
            raise AssertionError("candidate chat must not use local credentials when a lease exists")

    proxied = {}

    def fake_post(base_url, path, payload, *, timeout=180.0):
        proxied["base_url"] = base_url
        proxied["path"] = path
        proxied["payload"] = payload
        return {
            "text": "http lease response",
            "model": "MiniMax-M3",
            "provider": "minimax",
            "finish_reason": "stop",
        }

    monkeypatch.setattr(api_server, "get_gateway", lambda: FakeGateway())
    monkeypatch.setattr(api_server, "_post_json_to_http_url", fake_post)

    client = TestClient(app)
    status = client.get("/api/llm/status").json()
    chat = client.post("/api/llm/chat", json={"message": "ping"}).json()

    assert status["available"] is True
    assert status["availability_source"] == "candidate_model_lease"
    assert status["candidate_model_lease"]["host_http_configured"] is True
    assert chat["text"] == "http lease response"
    assert proxied["base_url"] == "http://127.0.0.1:45678"
    assert proxied["path"] == "/api/llm/chat"


def test_autopilot_review_decision_uses_distinct_model(monkeypatch):
    class ReviewGateway:
        async def chat(self, **kwargs):
            assert kwargs["model"] == "fake-review-model"
            return SimpleNamespace(
                text=json.dumps({
                    "status": "passed",
                    "recommendation": "review",
                    "merge_recommendation": "open_review_pr",
                    "product_value_score": 91,
                    "maintainability_score": 92,
                    "risk_score": 9,
                    "blocking_reasons": [],
                    "human_review_notes": ["human approval is still required before promotion"],
                }),
                provider="fake-provider",
                model="fake-review-model",
                finish_reason="stop",
                usage={"total_tokens": 44},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: ReviewGateway())
    response = TestClient(app).post("/api/autopilot/review-decision", json={
        "goal": "Review a candidate",
        "changed_files": ["across-agents-assistant/backend/src/across_agents_assistant/autopilot_product.py"],
        "validation": {"status": "passed", "command_count": 2},
        "deterministic_review": {"blocking_reasons": [], "warnings": []},
        "builder_model": {"provider": "fake-provider", "model": "fake-builder-model"},
        "model_policy": {"required": True, "provider": "fake-provider", "model": "fake-review-model"},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "across-host-review-decision/1.0"
    assert body["model_backed"] is True
    assert body["provider"] == "fake-provider"
    assert body["model"] == "fake-review-model"
    assert body["merge_recommendation"] == "open_review_pr"
    assert body["decision_hash"]


def test_autopilot_review_decision_allows_platform_replay_fixture_only(monkeypatch):
    class ReviewGateway:
        async def chat(self, **kwargs):
            assert "allow_replay_fixture_only" in kwargs["message"]
            return SimpleNamespace(
                text=json.dumps({
                    "status": "failed",
                    "recommendation": "reject",
                    "merge_recommendation": "repair_before_pr",
                    "product_value_score": 88,
                    "maintainability_score": 90,
                    "risk_score": 18,
                    "blocking_reasons": [
                        "candidate has no product source change",
                        "test-only change with no product source modification",
                    ],
                    "human_review_notes": ["Replay fixture covers the failed platform trigger."],
                }),
                provider="fake-provider",
                model="fake-review-model",
                finish_reason="stop",
                usage={"total_tokens": 55},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: ReviewGateway())
    response = TestClient(app).post("/api/autopilot/review-decision", json={
        "goal": "Review platform self-repair replay fixture",
        "selected_target_id": "autopilot-self-repair-replay-fixture",
        "selected_iteration": {
            "target_id": "autopilot-self-repair-replay-fixture",
            "target_repo": "across-autopilot",
            "semantic_review": {
                "allow_replay_fixture_only": True,
                "reject_test_only_change": False,
            },
        },
        "changed_files": ["across-autopilot/tests/platform-self-repair.test.js"],
        "validation": {"status": "passed", "command_count": 2},
        "deterministic_review": {"blocking_reasons": [], "warnings": []},
        "builder_model": {"provider": "fake-provider", "model": "fake-builder-model"},
        "model_policy": {"required": True, "provider": "fake-provider", "model": "fake-review-model"},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "passed"
    assert body["recommendation"] == "review"
    assert body["merge_recommendation"] == "open_review_pr"
    assert body["blocking_reasons"] == []


def test_autopilot_review_decision_rejects_builder_model(monkeypatch):
    class UnusedGateway:
        async def chat(self, **kwargs):
            raise AssertionError("same-model review should be rejected before gateway call")

    monkeypatch.setattr(api_server, "get_gateway", lambda: UnusedGateway())
    response = TestClient(app).post("/api/autopilot/review-decision", json={
        "goal": "Review a candidate",
        "changed_files": ["across-agents-assistant/backend/src/across_agents_assistant/autopilot_product.py"],
        "validation": {"status": "passed", "command_count": 2},
        "builder_model": {"provider": "fake-provider", "model": "fake-builder-model"},
        "model_policy": {"required": True, "provider": "fake-provider", "model": "fake-builder-model"},
    })

    assert response.status_code == 422
    assert "reviewer model must differ" in response.json()["detail"]


def test_autopilot_review_decision_routes_codex_local_agent(monkeypatch):
    captured = {}

    class LocalAgentClient:
        def send(self, message, *, target_agent=None, project_dir=None, timeout=None, **_kwargs):
            captured["message"] = message
            captured["target_agent"] = target_agent
            captured["project_dir"] = project_dir
            captured["timeout"] = timeout
            return SimpleNamespace(
                text=json.dumps({
                    "status": "passed",
                    "recommendation": "review",
                    "merge_recommendation": "open_review_pr",
                    "product_value_score": 92,
                    "maintainability_score": 91,
                    "risk_score": 8,
                    "blocking_reasons": [],
                    "human_review_notes": ["human approval is still required before promotion"],
                }),
                elapsed_sec=0.01,
                requires_approval=False,
            )

    class UnusedGateway:
        async def chat(self, **_kwargs):
            raise AssertionError("codex local agent policy must not use the gateway")

    monkeypatch.setattr(api_server, "get_local_agent_client", lambda: LocalAgentClient())
    monkeypatch.setattr(api_server, "get_gateway", lambda: UnusedGateway())
    response = TestClient(app).post("/api/autopilot/review-decision", json={
        "goal": "Review a candidate with the local Codex agent",
        "changed_files": ["across-agents-assistant/backend/src/across_agents_assistant/autopilot_product.py"],
        "validation": {"status": "passed", "command_count": 2},
        "builder_model": {"provider": "local-agent", "model": "codex"},
        "model_policy": {
            "required": True,
            "agent_id": "codex",
            "provider": "local-agent",
            "model": "codex",
            "require_distinct_from_builder": False,
            "timeout_ms": 900000,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "local-agent"
    assert body["model"] == "codex"
    assert body["merge_recommendation"] == "open_review_pr"
    assert captured["target_agent"] == "codex"
    assert captured["project_dir"] is None
    assert captured["timeout"] == 900.0
    assert "independent acceptance reviewer" in captured["message"]


def test_autopilot_research_decision_selects_catalog_target(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    class ResearchGateway:
        async def chat(self, **kwargs):
            assert "target_catalog" in kwargs["message"]
            assert "Choose from target_catalog only" in kwargs["system_prompt"]
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Adopt research-backed candidate scoring",
                    "rationale": "Agent platforms emphasize traces, evaluation, and bounded review before promotion.",
                    "decision": "implement",
                    "selected_target_id": "research_signal_quality",
                    "rejected_directions": ["auto-merge"],
                    "selected_iteration": {
                        "target_repo": "across-agents-assistant",
                        "goal": "Implement research candidate scoring",
                        "allowed_patch_paths": [
                            "backend/src/across_agents_assistant/autopilot_research_signal.py",
                            "backend/tests/test_autopilot_research_signal.py",
                        ],
                        "context_files": ["README.md"],
                        "validation_commands": [
                            {
                                "repo": "across-agents-assistant",
                                "command": "python3",
                                "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_research_signal.py"],
                            }
                        ],
                        "semantic_review": {"minimum_validation_commands": 1},
                        "source_refs": ["openhands"],
                        "risk": "low",
                    },
                }),
                provider="fake-provider",
                model="fake-research-model",
                finish_reason="stop",
                usage={"total_tokens": 77},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: ResearchGateway())
    response = TestClient(app).post("/api/autopilot/research-decision", json={
        "goal": "Choose next research-driven AAA iteration",
        "candidate_workspace": str(candidate),
        "sources": [{"id": "openhands", "status": "passed", "result": {"excerpt": "trace and evaluate agent work"}}],
        "target_catalog": [
            {
                "id": "research_signal_quality",
                "target_repo": "across-agents-assistant",
                "allowed_patch_paths": [
                    "backend/src/across_agents_assistant/autopilot_research_signal.py",
                    "backend/tests/test_autopilot_research_signal.py",
                ],
                "context_files": ["README.md"],
            }
        ],
        "model_policy": {"required": True, "provider": "fake"},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "across-host-research-decision/1.0"
    assert body["model_backed"] is True
    assert body["provider"] == "fake-provider"
    assert body["selected_target_id"] == "research_signal_quality"
    assert body["selected_iteration"]["allowed_patch_paths"] == [
        "backend/src/across_agents_assistant/autopilot_research_signal.py",
        "backend/tests/test_autopilot_research_signal.py",
    ]
    assert body["decision_hash"]


def test_autopilot_research_decision_prefers_trigger_target_id(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    class ResearchGateway:
        async def chat(self, **kwargs):
            raise AssertionError("explicit trigger target must not require model target selection")

    monkeypatch.setattr(api_server, "get_gateway", lambda: ResearchGateway())
    response = TestClient(app).post("/api/autopilot/research-decision", json={
        "goal": "Choose platform self-repair target",
        "candidate_workspace": str(candidate),
        "product_context": {
            "trigger_payload": {
                "target_id": "autopilot-self-repair-replay-fixture",
                "target_repo": "across-autopilot",
            }
        },
        "target_catalog": [
            {
                "id": "aaa-host-runtime-repair",
                "target_repo": "across-agents-assistant",
                "allowed_patch_paths": ["backend/main.py"],
                "context_files": ["backend/main.py"],
            },
            {
                "id": "autopilot-self-repair-replay-fixture",
                "target_repo": "across-autopilot",
                "allowed_patch_paths": [
                    "tests/platform-self-repair.test.js",
                ],
                "context_files": ["src/platform-self-repair.js"],
                "validation_commands": [
                    {"repo": "across-autopilot", "command": "node", "args": ["--test", "tests/platform-self-repair.test.js"]},
                    {"repo": "across-autopilot", "command": "node", "args": ["src/cli.js", "loop", "validate", "--spec", "aaa-platform-self-repair", "--json"]},
                ],
                "semantic_review": {"minimum_validation_commands": 2, "reject_test_only_change": False},
            },
        ],
        "model_policy": {"required": True, "provider": "fake"},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["model_backed"] is False
    assert body["provider"] == "deterministic"
    assert body["fallback_reason"] == "deterministic_trigger_target"
    assert body["selected_target_id"] == "autopilot-self-repair-replay-fixture"
    assert body["selected_iteration"]["target_repo"] == "across-autopilot"
    assert body["selected_iteration"]["allowed_patch_paths"] == [
        "tests/platform-self-repair.test.js",
    ]
    rendered_commands = [
        " ".join([command["command"], *(command.get("args") or [])])
        for command in body["selected_iteration"]["validation_commands"]
    ]
    assert any("node --test tests/platform-self-repair.test.js" in command for command in rendered_commands)
    assert all("npm test" not in command for command in rendered_commands)


def test_autopilot_research_decision_generates_open_backlog(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    class ResearchGateway:
        async def chat(self, **kwargs):
            assert "candidate_targets" in kwargs["system_prompt"]
            assert "must generate candidate_targets" in kwargs["system_prompt"]
            assert "target_generation" in kwargs["message"]
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Generate an autonomous backlog from research signals",
                    "rationale": "The current source signal points at review quality and tool stability.",
                    "decision": "implement",
                    "selected_target_id": "generated-review-quality",
                    "candidate_targets": [
                        {
                            "id": "generated-review-quality",
                            "target_repo": "across-agents-assistant",
                            "summary": "Add review-quality scoring for autonomous candidates",
                            "goal": "Implement a helper that scores candidate evidence before promotion review.",
                            "allowed_patch_paths": [
                                "backend/src/across_agents_assistant/autopilot_generated_review_quality.py",
                                "backend/tests/test_autopilot_generated_review_quality.py",
                            ],
                            "context_files": ["README.md"],
                            "source_refs": ["architecture-signal"],
                            "tool_packs": ["candidate_workspace", "validation_harness", "independent_review"],
                            "generated_from": "model_generated",
                            "risk": "low",
                        },
                        {
                            "id": "generated-tool-stability",
                            "target_repo": "across-agents-assistant",
                            "summary": "Add tool stability scoring",
                            "goal": "Implement a helper that checks whether a loop used deterministic tool packs.",
                            "allowed_patch_paths": [
                                "backend/src/across_agents_assistant/autopilot_generated_tool_stability.py",
                                "backend/tests/test_autopilot_generated_tool_stability.py",
                            ],
                            "tool_packs": ["source_research_digest", "validation_harness"],
                            "generated_from": "model_generated",
                            "risk": "low",
                        },
                    ],
                    "selected_iteration": {
                        "target_id": "generated-review-quality",
                        "target_repo": "across-agents-assistant",
                        "goal": "Implement a helper that scores candidate evidence before promotion review.",
                        "allowed_patch_paths": [
                            "backend/src/across_agents_assistant/autopilot_generated_review_quality.py",
                            "backend/tests/test_autopilot_generated_review_quality.py",
                        ],
                        "context_files": ["README.md"],
                        "source_refs": ["architecture-signal"],
                        "tool_packs": ["candidate_workspace", "validation_harness", "independent_review"],
                        "generated_from": "model_generated",
                        "risk": "low",
                    },
                }),
                provider="fake-provider",
                model="fake-research-model",
                finish_reason="stop",
                usage={"total_tokens": 88},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: ResearchGateway())
    response = TestClient(app).post("/api/autopilot/research-decision", json={
        "goal": "Choose an open autonomous AAA iteration",
        "candidate_workspace": str(candidate),
        "sources": [{"id": "architecture-signal", "status": "passed", "result": {"excerpt": "review quality and stable tool packs"}}],
        "product_context": {"autonomous_loop_state": {"backlog_count": 0}},
        "target_catalog": [],
        "target_generation": {
            "mode": "model_generated",
            "allow_model_generated_targets": True,
            "minimum_candidates": 2,
        },
        "model_policy": {"required": True, "provider": "fake"},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["selected_target_id"] == "generated-review-quality"
    assert len(body["candidate_targets"]) == 2


def test_autopilot_research_decision_accepts_readonly_across_home_context(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    across_home = tmp_path / ".across"
    source_signals = across_home / "data" / "across-autopilot" / "loop-state" / "artifacts" / "aaa-autonomous-self-iteration" / "source-signals.json"
    source_signals.parent.mkdir(parents=True)
    source_signals.write_text("{}", encoding="utf-8")
    source_signal_context = "loop-state/artifacts/aaa-autonomous-self-iteration/source-signals.json"
    monkeypatch.setenv("ACROSS_HOME", str(across_home))

    class ResearchGateway:
        async def chat(self, **kwargs):
            assert "context_file_policy" in kwargs["message"]
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Use read-only loop-state artifact context",
                    "rationale": "The model should not need to patch artifacts.",
                    "decision": "implement",
                    "selected_target_id": "generated-context-reader",
                    "candidate_targets": [
                        {
                            "id": "generated-context-reader",
                            "target_repo": "across-agents-assistant",
                            "summary": "Add context reader",
                            "goal": "Use ACROSS_HOME loop-state artifacts as read-only context.",
                            "allowed_patch_paths": [
                                "backend/src/across_agents_assistant/autopilot_context_reader.py",
                                "backend/tests/test_autopilot_context_reader.py",
                            ],
                            "context_files": [source_signal_context],
                            "validation_commands": [
                                {"repo": "across-agents-assistant", "command": "python3", "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_context_reader.py"]},
                                {"repo": "across-agents-assistant", "command": "git", "args": ["diff", "--check"]},
                            ],
                            "semantic_review": {"minimum_validation_commands": 2},
                            "source_refs": ["architecture-signal"],
                            "tool_packs": ["source_research_digest", "candidate_workspace", "validation_harness"],
                            "generated_from": "model_generated",
                            "risk": "low",
                        },
                        {
                            "id": "generated-context-fallback",
                            "target_repo": "across-agents-assistant",
                            "summary": "Add fallback",
                            "goal": "Fallback target.",
                            "allowed_patch_paths": [
                                "backend/src/across_agents_assistant/autopilot_context_fallback.py",
                                "backend/tests/test_autopilot_context_fallback.py",
                            ],
                            "validation_commands": [
                                {"repo": "across-agents-assistant", "command": "git", "args": ["diff", "--check"]},
                                {"repo": "across-agents-assistant", "command": "python3", "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_context_fallback.py"]},
                            ],
                            "semantic_review": {"minimum_validation_commands": 2},
                            "source_refs": ["architecture-signal"],
                            "tool_packs": ["validation_harness"],
                            "generated_from": "model_generated",
                            "risk": "low",
                        },
                    ],
                    "selected_iteration": {
                        "target_id": "generated-context-reader",
                        "target_repo": "across-agents-assistant",
                        "goal": "Use ACROSS_HOME loop-state artifacts as read-only context.",
                        "allowed_patch_paths": [
                            "backend/src/across_agents_assistant/autopilot_context_reader.py",
                            "backend/tests/test_autopilot_context_reader.py",
                        ],
                        "context_files": [source_signal_context],
                        "validation_commands": [
                            {"repo": "across-agents-assistant", "command": "python3", "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_context_reader.py"]},
                            {"repo": "across-agents-assistant", "command": "git", "args": ["diff", "--check"]},
                        ],
                        "semantic_review": {"minimum_validation_commands": 2},
                        "source_refs": ["architecture-signal"],
                        "tool_packs": ["source_research_digest", "candidate_workspace", "validation_harness"],
                        "generated_from": "model_generated",
                        "risk": "low",
                    },
                }),
                provider="fake-provider",
                model="fake-research-model",
                finish_reason="stop",
                usage={"total_tokens": 88},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: ResearchGateway())
    response = TestClient(app).post("/api/autopilot/research-decision", json={
        "goal": "Choose an open autonomous AAA iteration",
        "candidate_workspace": str(candidate),
        "sources": [{"id": "architecture-signal", "status": "passed", "result": {"excerpt": "read loop state artifact"}}],
        "product_context": {"autonomous_loop_state": {"root": str(across_home / "data" / "across-autopilot" / "loop-state")}},
        "target_catalog": [],
        "target_generation": {
            "mode": "model_generated",
            "allow_model_generated_targets": True,
            "minimum_candidates": 2,
        },
        "model_policy": {"required": True, "provider": "fake"},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["selected_iteration"]["context_files"] == [source_signal_context]
    assert all(not path.startswith(str(across_home)) for path in body["selected_iteration"]["allowed_patch_paths"])
    selected = body["selected_iteration"]
    assert selected["target_id"] == "generated-context-reader"
    assert selected["semantic_review"]["independent_reviewer_required"] is True
    assert len(selected["validation_commands"]) >= 2
    assert selected["tool_packs"] == ["source_research_digest", "candidate_workspace", "validation_harness"]


def test_autopilot_research_decision_moves_loop_state_context_out_of_patch_paths(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    across_home = tmp_path / ".across"
    loop_root = across_home / "data" / "across-autopilot" / "loop-state"
    contract_path = loop_root / "contracts" / "aaa-autonomous-self-iteration" / "contract.json"
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))

    class ResearchGateway:
        async def chat(self, **kwargs):
            target = {
                "id": "generated-contract-aware",
                "target_repo": "across-agents-assistant",
                "summary": "Add contract-aware target",
                "goal": "Use loop-state contracts as read-only context.",
                "allowed_patch_paths": [
                    "backend/src/across_agents_assistant/api_server.py",
                    "backend/src/across_agents_assistant/autopilot_contract_reader.py",
                    "backend/tests/test_autopilot_contract_reader.py",
                    str(contract_path),
                ],
                "validation_commands": [
                    {"repo": "across-agents-assistant", "command": "python3", "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_contract_reader.py"]},
                    {"repo": "across-agents-assistant", "command": "git", "args": ["diff", "--check"]},
                ],
                "semantic_review": {"minimum_validation_commands": 2},
                "source_refs": ["architecture-signal"],
                "tool_packs": ["candidate_workspace", "validation_harness"],
                "generated_from": "model_generated",
                "risk": "low",
            }
            fallback = {
                **target,
                "id": "generated-contract-fallback",
                "summary": "Fallback",
                "goal": "Fallback target.",
                "allowed_patch_paths": [
                    "backend/src/across_agents_assistant/api_server.py",
                    "backend/src/across_agents_assistant/autopilot_contract_fallback.py",
                    "backend/tests/test_autopilot_contract_fallback.py",
                ],
            }
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Move loop-state contract to context files",
                    "rationale": "Contracts are read-only context, not writable patch targets.",
                    "decision": "implement",
                    "selected_target_id": target["id"],
                    "candidate_targets": [target, fallback],
                    "selected_iteration": {**target, "target_id": target["id"]},
                }),
                provider="fake-provider",
                model="fake-research-model",
                finish_reason="stop",
                usage={"total_tokens": 101},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: ResearchGateway())
    response = TestClient(app).post("/api/autopilot/research-decision", json={
        "goal": "Choose an open autonomous AAA iteration",
        "candidate_workspace": str(candidate),
        "sources": [{"id": "architecture-signal", "status": "passed", "result": {"excerpt": "read loop state contract"}}],
        "product_context": {"autonomous_loop_state": {"root": str(loop_root)}},
        "target_catalog": [],
        "target_generation": {
            "mode": "model_generated",
            "allow_model_generated_targets": True,
            "minimum_candidates": 2,
        },
        "model_policy": {"required": True, "provider": "fake"},
    })

    assert response.status_code == 200
    body = response.json()
    assert str(contract_path) in body["selected_iteration"]["context_files"]
    assert str(contract_path) not in body["selected_iteration"]["allowed_patch_paths"]
    assert all(not path.startswith(str(across_home)) for path in body["selected_iteration"]["allowed_patch_paths"])


def test_autopilot_research_decision_repairs_generated_minimum(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    class ResearchGateway:
        def __init__(self):
            self.calls = 0

        async def chat(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(
                    text=json.dumps({
                        "summary": "Too few generated targets",
                        "decision": "implement",
                        "selected_target_id": "one",
                        "candidate_targets": [
                            {
                                "id": "one",
                                "target_repo": "across-agents-assistant",
                                "summary": "One target",
                                "goal": "Add one target",
                                "allowed_patch_paths": ["backend/src/across_agents_assistant/autopilot_one.py"],
                                "validation_commands": [{"repo": "across-agents-assistant", "command": "git", "args": ["diff", "--check"]}],
                            }
                        ],
                    }),
                    provider="fake-provider",
                    model="fake-research-model",
                    finish_reason="stop",
                    usage={},
                )
            assert "at least 3 safe generated targets" in kwargs["message"]
            targets = []
            for name in ["one", "two", "three"]:
                targets.append({
                    "id": name,
                    "target_repo": "across-agents-assistant",
                    "summary": f"Target {name}",
                    "goal": f"Add target {name}",
                    "allowed_patch_paths": [
                        f"backend/src/across_agents_assistant/autopilot_{name}.py",
                        f"backend/tests/test_autopilot_{name}.py",
                    ],
                    "validation_commands": [
                        {"repo": "across-agents-assistant", "command": "git", "args": ["diff", "--check"]},
                        {"repo": "across-agents-assistant", "command": "python3", "args": ["-m", "py_compile", f"backend/src/across_agents_assistant/autopilot_{name}.py"]},
                    ],
                    "semantic_review": {"minimum_validation_commands": 2},
                    "source_refs": ["architecture-signal"],
                    "tool_packs": ["candidate_workspace", "validation_harness"],
                    "generated_from": "model_generated",
                    "risk": "low",
                })
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Repair with the required generated backlog size",
                    "rationale": "The contract requires three options before selecting one.",
                    "decision": "implement",
                    "selected_target_id": "one",
                    "candidate_targets": targets,
                    "selected_iteration": {**targets[0], "target_id": "one"},
                }),
                provider="fake-provider",
                model="fake-research-model",
                finish_reason="stop",
                usage={},
            )

    gateway = ResearchGateway()
    monkeypatch.setattr(api_server, "get_gateway", lambda: gateway)
    response = TestClient(app).post("/api/autopilot/research-decision", json={
        "goal": "Choose an open autonomous AAA iteration",
        "candidate_workspace": str(candidate),
        "sources": [{"id": "architecture-signal", "status": "passed", "result": {"excerpt": "review quality and stable tool packs"}}],
        "product_context": {"autonomous_loop_state": {"backlog_count": 0}},
        "target_catalog": [],
        "target_generation": {
            "mode": "model_generated",
            "allow_model_generated_targets": True,
            "minimum_candidates": 3,
        },
        "model_policy": {"required": True, "provider": "fake"},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["repaired_json"] is True
    assert body["selected_target_id"] == "one"
    assert len(body["candidate_targets"]) == 3


def test_autopilot_research_decision_repairs_directory_patch_paths(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    class DirectoryPathGateway:
        def __init__(self):
            self.calls = 0

        async def chat(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                targets = []
                for name in ["one", "two", "three"]:
                    targets.append({
                        "id": name,
                        "target_repo": "across-agents-assistant",
                        "summary": f"Target {name}",
                        "goal": f"Add target {name}",
                        "allowed_patch_paths": ["backend/src/across_agents_assistant/"],
                        "validation_commands": [
                            {"repo": "across-agents-assistant", "command": "git", "args": ["diff", "--check"]},
                            {"repo": "across-agents-assistant", "command": "python3", "args": ["-m", "py_compile", "backend/src/across_agents_assistant/"]},
                        ],
                        "semantic_review": {"minimum_validation_commands": 2},
                        "source_refs": ["architecture-signal"],
                        "tool_packs": ["candidate_workspace", "validation_harness"],
                        "generated_from": "model_generated",
                        "risk": "low",
                    })
                return SimpleNamespace(
                    text=json.dumps({
                        "summary": "Invalid directory-level paths",
                        "rationale": "The first attempt used a package prefix.",
                        "decision": "implement",
                        "selected_target_id": "one",
                        "candidate_targets": targets,
                        "selected_iteration": {**targets[0], "target_id": "one"},
                    }),
                    provider="fake-provider",
                    model="fake-research-model",
                    finish_reason="stop",
                    usage={},
                )

            assert "concrete repository-relative files" in kwargs["message"]
            assert "Never return paths that end with '/'" in kwargs["message"]
            targets = []
            for name in ["one", "two", "three"]:
                targets.append({
                    "id": name,
                    "target_repo": "across-agents-assistant",
                    "summary": f"Target {name}",
                    "goal": f"Add target {name}",
                    "allowed_patch_paths": [
                        f"backend/src/across_agents_assistant/autopilot_{name}.py",
                        f"backend/tests/test_autopilot_{name}.py",
                    ],
                    "validation_commands": [
                        {"repo": "across-agents-assistant", "command": "python3", "args": ["-m", "py_compile", f"backend/src/across_agents_assistant/autopilot_{name}.py", f"backend/tests/test_autopilot_{name}.py"]},
                        {"repo": "across-agents-assistant", "command": "git", "args": ["diff", "--check"]},
                    ],
                    "semantic_review": {"minimum_validation_commands": 2},
                    "source_refs": ["architecture-signal"],
                    "tool_packs": ["candidate_workspace", "validation_harness"],
                    "generated_from": "model_generated_repair",
                    "risk": "low",
                })
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Repair directory paths into exact files",
                    "rationale": "Patch paths must be concrete files so B-only mutation stays bounded.",
                    "decision": "implement",
                    "selected_target_id": "one",
                    "candidate_targets": targets,
                    "selected_iteration": {**targets[0], "target_id": "one"},
                }),
                provider="fake-provider",
                model="fake-research-model",
                finish_reason="stop",
                usage={},
            )

    gateway = DirectoryPathGateway()
    monkeypatch.setattr(api_server, "get_gateway", lambda: gateway)
    response = TestClient(app).post("/api/autopilot/research-decision", json={
        "goal": "Choose an open autonomous AAA iteration",
        "candidate_workspace": str(candidate),
        "sources": [{"id": "architecture-signal", "status": "passed", "result": {"excerpt": "stable tool packs and review gates"}}],
        "product_context": {"autonomous_loop_state": {"backlog_count": 0}},
        "target_catalog": [],
        "target_generation": {
            "mode": "model_generated",
            "allow_model_generated_targets": True,
            "minimum_candidates": 3,
        },
        "model_policy": {"required": True, "provider": "fake"},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["repaired_json"] is True
    assert body["selected_iteration"]["allowed_patch_paths"] == [
        "backend/src/across_agents_assistant/autopilot_one.py",
        "backend/tests/test_autopilot_one.py",
    ]
    assert gateway.calls == 2


def test_autopilot_research_decision_production_rejects_host_target_fallback(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    class BrokenResearchGateway:
        async def chat(self, **kwargs):
            return SimpleNamespace(
                text="<think>no valid JSON</think>",
                provider="fake-provider",
                model="fake-research-model",
                finish_reason="length",
                usage={"total_tokens": 12},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: BrokenResearchGateway())
    response = TestClient(app).post("/api/autopilot/research-decision", json={
        "goal": "Choose an open autonomous AAA iteration",
        "candidate_workspace": str(candidate),
        "sources": [{"id": "architecture-signal", "status": "passed", "result": {"excerpt": "review quality and stable tool packs"}}],
        "product_context": {"autonomous_loop_state": {"backlog_count": 0}},
        "target_catalog": [],
        "target_generation": {
            "mode": "model_generated",
            "allow_model_generated_targets": True,
            "minimum_candidates": 2,
        },
        "model_policy": {"required": True, "provider": "fake"},
    })

    assert response.status_code == 422
    assert "host target fallback is disabled" in response.json()["detail"]


def test_autopilot_research_decision_local_agent_timeout_uses_timeout_fallback(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    captured = {}

    class LocalAgentClient:
        def send(self, message, *, target_agent=None, project_dir=None, timeout=None, **_kwargs):
            captured["message"] = message
            captured["target_agent"] = target_agent
            captured["project_dir"] = project_dir
            captured["timeout"] = timeout
            return SimpleNamespace(
                text="抱歉，codex 执行超时（超过 540 秒），已自动终止。",
                elapsed_sec=540.0,
                requires_approval=False,
                timed_out=True,
                error_code="timeout",
            )

    class UnusedGateway:
        async def chat(self, **_kwargs):
            raise AssertionError("codex local agent policy must not use the gateway")

    monkeypatch.setattr(api_server, "get_local_agent_client", lambda: LocalAgentClient())
    monkeypatch.setattr(api_server, "get_gateway", lambda: UnusedGateway())
    response = TestClient(app).post("/api/autopilot/research-decision", json={
        "goal": "Choose an open autonomous AAA iteration",
        "candidate_workspace": str(candidate),
        "sources": [{"id": "architecture-signal", "status": "passed", "result": {"excerpt": "review quality and stable tool packs"}}],
        "product_context": {"autonomous_loop_state": {"backlog_count": 0}},
        "target_catalog": [],
        "target_generation": {
            "mode": "model_generated",
            "allow_model_generated_targets": True,
            "minimum_candidates": 3,
        },
        "model_policy": {
            "required": True,
            "agent_id": "codex",
            "provider": "local-agent",
            "model": "codex",
            "timeout_ms": 600000,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["model_backed"] is False
    assert body["provider"] == "local-agent"
    assert body["model"] == "codex"
    assert "timed out" in body["fallback_reason"]
    assert body["selected_target_id"] == "autonomous-research-timeout-recovery"
    assert len(body["candidate_targets"]) == 3
    assert body["selected_iteration"]["allowed_patch_paths"][0] == "backend/src/across_agents_assistant/api_server.py"
    assert body["selected_iteration"]["semantic_review"]["independent_reviewer_required"] is True
    assert captured["target_agent"] == "codex"
    assert captured["project_dir"] == str(candidate)
    assert captured["timeout"] == 600.0


def test_autopilot_research_decision_local_agent_missing_returns_structured_failure(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    class LocalAgentClient:
        def send(self, message, *, target_agent=None, project_dir=None, timeout=None, **_kwargs):
            return SimpleNamespace(
                text="本地未找到 codex 可执行文件，请在菜单栏点击【配置智能体】进行设置。",
                elapsed_sec=0.01,
                requires_approval=False,
                error_code="agent_not_found",
            )

    monkeypatch.setattr(api_server, "get_local_agent_client", lambda: LocalAgentClient())
    response = TestClient(app).post("/api/autopilot/research-decision", json={
        "goal": "Choose an open autonomous AAA iteration",
        "candidate_workspace": str(candidate),
        "product_context": {"autonomous_loop_state": {"backlog_count": 0}},
        "target_generation": {
            "mode": "model_generated",
            "allow_model_generated_targets": True,
            "minimum_candidates": 3,
        },
        "model_policy": {
            "required": True,
            "agent_id": "codex",
            "provider": "local-agent",
            "model": "codex",
            "timeout_ms": 600000,
        },
    })

    assert response.status_code == 503
    assert "executable was not found" in response.json()["detail"]


def test_autopilot_research_decision_preserves_autonomous_catalog_metadata(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    class ResearchGateway:
        async def chat(self, **kwargs):
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Select Tool Pack policy",
                    "rationale": "Tool Pack usage should be first-class evidence.",
                    "decision": "implement",
                    "selected_target_id": "tool_pack_policy",
                    "selected_iteration": {
                        "target_id": "tool_pack_policy",
                        "target_repo": "across-agents-assistant",
                        "goal": "Add Tool Pack policy helper",
                        "allowed_patch_paths": [
                            "backend/src/across_agents_assistant/autopilot_tool_pack_policy.py",
                            "backend/tests/test_autopilot_tool_pack_policy.py",
                        ],
                        "context_files": ["AGENTS.md"],
                        "validation_commands": [
                            {
                                "repo": "across-agents-assistant",
                                "command": "python3",
                                "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_tool_pack_policy.py"],
                            }
                        ],
                        "semantic_review": {"minimum_validation_commands": 1},
                        "source_refs": ["tool-pack-signal"],
                        "risk": "low",
                    },
                }),
                provider="fake-provider",
                model="fake-research-model",
                finish_reason="stop",
                usage={},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: ResearchGateway())
    response = TestClient(app).post("/api/autopilot/research-decision", json={
        "goal": "Choose an autonomous self-iteration target",
        "candidate_workspace": str(candidate),
        "sources": [{"id": "tool-pack-signal", "result": {"excerpt": "Tool Pack Registry"}}],
        "product_context": {
            "autonomous_loop_state": {"backlog_count": 3}
        },
        "target_catalog": [
            {
                "id": "tool_pack_policy",
                "target_repo": "across-agents-assistant",
                "goal": "Add Tool Pack policy helper",
                "allowed_patch_paths": [
                    "backend/src/across_agents_assistant/autopilot_tool_pack_policy.py",
                    "backend/tests/test_autopilot_tool_pack_policy.py",
                ],
                "context_files": ["AGENTS.md"],
                "validation_commands": [
                    {
                        "repo": "across-agents-assistant",
                        "command": "python3",
                        "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_tool_pack_policy.py"],
                    }
                ],
                "semantic_review": {"minimum_validation_commands": 1},
                "tool_packs": ["candidate_workspace", "validation_harness"],
                "generated_from": "source_signals",
                "score": 24,
                "risk": "low",
            }
        ],
        "model_policy": {"required": True, "provider": "fake"},
    })

    assert response.status_code == 200
    body = response.json()
    selected = body["selected_iteration"]
    assert selected["target_id"] == "tool_pack_policy"
    assert selected["tool_packs"] == ["candidate_workspace", "validation_harness"]
    assert selected["generated_from"] == "source_signals"
    assert selected["score"] == 24


def test_autopilot_research_decision_repairs_malformed_json(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    class RepairingGateway:
        def __init__(self):
            self.calls = 0

        async def chat(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(
                    text="<think>Use research signal quality.</think>",
                    provider="minimax",
                    model="MiniMax-M3",
                    finish_reason="length",
                    usage={"total_tokens": 55},
                )
            assert "Repair the prior research decision" in kwargs["message"]
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Repair selected research scoring",
                    "rationale": "Traceable agents need evaluation before promotion.",
                    "decision": "implement",
                    "selected_target_id": "research_signal_quality",
                    "selected_iteration": {
                        "target_repo": "across-agents-assistant",
                        "goal": "Implement research candidate scoring",
                        "allowed_patch_paths": [
                            "backend/src/across_agents_assistant/autopilot_research_signal.py",
                            "backend/tests/test_autopilot_research_signal.py",
                        ],
                        "context_files": ["README.md"],
                    },
                }),
                provider="minimax",
                model="MiniMax-M3",
                finish_reason="stop",
                usage={"total_tokens": 88},
            )

    gateway = RepairingGateway()
    monkeypatch.setattr(api_server, "get_gateway", lambda: gateway)
    response = TestClient(app).post("/api/autopilot/research-decision", json={
        "goal": "Choose next research-driven AAA iteration",
        "candidate_workspace": str(candidate),
        "sources": [{"id": "openhands", "status": "passed", "result": {"excerpt": "trace and evaluate agent work"}}],
        "target_catalog": [
            {
                "id": "research_signal_quality",
                "target_repo": "across-agents-assistant",
                "allowed_patch_paths": [
                    "backend/src/across_agents_assistant/autopilot_research_signal.py",
                    "backend/tests/test_autopilot_research_signal.py",
                ],
                "context_files": ["README.md"],
            }
        ],
        "model_policy": {"required": True, "provider": "minimax"},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["repaired_json"] is True
    assert body["rationale"] == "Traceable agents need evaluation before promotion."
    assert body["selected_target_id"] == "research_signal_quality"


def test_autopilot_research_decision_generated_selected_iteration_overrides_same_id(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    class GeneratedGateway:
        async def chat(self, **kwargs):
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Wire trace capability into AAA",
                    "rationale": "Selected iteration is the concrete bounded target.",
                    "decision": "implement",
                    "selected_target_id": "trace-capability",
                    "candidate_targets": [
                        {
                            "id": "trace-capability",
                            "target_repo": "across-agents-assistant",
                            "summary": "Trace helper",
                            "goal": "Add trace helper",
                            "allowed_patch_paths": [
                                "backend/src/across_agents_assistant/autopilot_trace_capability.py",
                                "backend/tests/test_autopilot_trace_capability.py",
                            ],
                            "validation_commands": [
                                {"repo": "across-agents-assistant", "command": "git", "args": ["diff", "--check"]},
                                {"repo": "across-agents-assistant", "command": "python3", "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_trace_capability.py"]},
                            ],
                            "semantic_review": {"minimum_validation_commands": 2},
                            "source_refs": ["mcp-tooling"],
                            "tool_packs": ["validation_harness"],
                            "generated_from": "model",
                            "risk": "low",
                        }
                    ],
                    "selected_iteration": {
                        "target_id": "trace-capability",
                        "target_repo": "across-agents-assistant",
                        "goal": "Wire trace capability into an existing AAA API surface",
                        "allowed_patch_paths": [
                            "backend/src/across_agents_assistant/api_server.py",
                            "backend/src/across_agents_assistant/autopilot_trace_capability.py",
                            "backend/tests/test_autopilot_trace_capability.py",
                        ],
                        "validation_commands": [
                            {"repo": "across-agents-assistant", "command": "git", "args": ["diff", "--check"]},
                            {"repo": "across-agents-assistant", "command": "python3", "args": ["-m", "py_compile", "backend/src/across_agents_assistant/api_server.py"]},
                        ],
                        "semantic_review": {"minimum_validation_commands": 2},
                        "source_refs": ["mcp-tooling"],
                        "tool_packs": ["validation_harness"],
                        "generated_from": "model",
                        "risk": "low",
                    },
                }),
                provider="minimax",
                model="MiniMax-M3",
                finish_reason="stop",
                usage={"total_tokens": 100},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: GeneratedGateway())
    response = TestClient(app).post("/api/autopilot/research-decision", json={
        "goal": "Choose generated AAA target",
        "candidate_workspace": str(candidate),
        "sources": [{"id": "mcp-tooling", "status": "passed", "result": {"excerpt": "tools"}}],
        "target_catalog": [],
        "target_generation": {"allow_model_generated_targets": True, "minimum_candidates": 1},
        "model_policy": {"required": True, "provider": "minimax"},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["selected_iteration"]["target_id"] == "trace-capability"
    assert body["selected_iteration"]["allowed_patch_paths"] == [
        "backend/src/across_agents_assistant/api_server.py",
        "backend/src/across_agents_assistant/autopilot_trace_capability.py",
        "backend/tests/test_autopilot_trace_capability.py",
    ]
    assert body["candidate_targets"][0]["allowed_patch_paths"] == body["selected_iteration"]["allowed_patch_paths"]


def test_autopilot_research_target_policy_allows_host_runtime_entrypoints():
    assert api_server._autopilot_path_allowed_for_repo("across-agents-assistant", "backend/main.py") is True
    assert api_server._autopilot_path_allowed_for_repo("across-agents-assistant", "build_app.sh") is True
    assert api_server._autopilot_path_allowed_for_repo("across-agents-assistant", "scripts/run_platform_self_repair_e2e.sh") is True
    assert api_server._autopilot_path_allowed_for_repo("across-agents-assistant", ".github/workflows/quality.yml") is False


def test_autopilot_model_decision_repairs_malformed_model_json(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class RepairingGateway:
        def __init__(self):
            self.calls = 0

        async def chat(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(
                    text='{"summary":"broken","patches":[{"path":"docs/ITERATION.md","content":"unterminated}',
                    provider="fake-provider",
                    model="fake-model",
                    finish_reason="stop",
                    usage={"total_tokens": 11},
                )
            return SimpleNamespace(
                text=(
                    '{"summary":"Repair JSON","rationale":"Recovered valid structure","risk":"low",'
                    '"patches":[{"path":"docs/ITERATION.md","mode":"overwrite",'
                    '"content":"# Iteration\\nRepaired model-backed patch\\n"}]}'
                ),
                provider="fake-provider",
                model="fake-model",
                finish_reason="stop",
                usage={"total_tokens": 22},
            )

    gateway = RepairingGateway()
    monkeypatch.setattr(api_server, "get_gateway", lambda: gateway)
    response = TestClient(app).post("/api/autopilot/model-decision", json={
        "goal": "Plan an AAA candidate-only iteration",
        "candidate_workspace": str(candidate),
        "allowed_patch_paths": ["docs/ITERATION.md"],
        "context_files": ["README.md"],
        "model_policy": {"required": True, "provider": "fake"},
    })

    assert response.status_code == 200
    body = response.json()
    assert gateway.calls == 2
    assert body["repaired_json"] is True
    assert body["text_fallback"] is False
    assert body["patches"][0]["path"] == "docs/ITERATION.md"


def test_autopilot_model_decision_accepts_patch_plan(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    class PlanGateway:
        async def chat(self, **kwargs):
            return SimpleNamespace(
                text=(
                    '{"summary":"Improve traceability","rationale":"Keep mutation deterministic",'
                    '"risk":"low","patch_plan":{"path":"LOOP_ENGINEERING_SELF_ITERATION.md",'
                    '"title":"AAA Self Iteration Traceability",'
                    '"sections":[{"heading":"Evidence","bullets":["Record provider/model/hash",'
                    '"Keep source read-only"]}]}}'
                ),
                provider="fake-provider",
                model="fake-model",
                finish_reason="stop",
                usage={"total_tokens": 9},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: PlanGateway())
    response = TestClient(app).post("/api/autopilot/model-decision", json={
        "goal": "Plan an AAA candidate-only iteration",
        "candidate_workspace": str(candidate),
        "allowed_patch_paths": ["LOOP_ENGINEERING_SELF_ITERATION.md"],
        "model_policy": {"required": True, "provider": "fake"},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["text_fallback"] is False
    assert body["patches"][0]["path"] == "LOOP_ENGINEERING_SELF_ITERATION.md"
    assert "# AAA Self Iteration Traceability" in body["patches"][0]["content"]
    assert "Record provider/model/hash" in body["patches"][0]["content"]


def test_autopilot_model_decision_accepts_decision_card(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    class CardGateway:
        async def chat(self, **kwargs):
            return SimpleNamespace(
                text=(
                    '{"summary":"Add promotion evidence","rationale":"Keep the candidate reviewable",'
                    '"risk":"low","decision_card":{"path":"LOOP_ENGINEERING_SELF_ITERATION.md",'
                    '"title":"AAA Self Iteration Decision",'
                    '"key_changes":["Record model provenance","Keep source read-only"],'
                    '"validation":["Check candidate-only diff","Run gate evidence"]}}'
                ),
                provider="fake-provider",
                model="fake-model",
                finish_reason="stop",
                usage={"total_tokens": 8},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: CardGateway())
    response = TestClient(app).post("/api/autopilot/model-decision", json={
        "goal": "Plan an AAA candidate-only iteration",
        "candidate_workspace": str(candidate),
        "allowed_patch_paths": ["LOOP_ENGINEERING_SELF_ITERATION.md"],
        "model_policy": {"required": True, "provider": "fake"},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["text_fallback"] is False
    assert body["patches"][0]["path"] == "LOOP_ENGINEERING_SELF_ITERATION.md"
    assert "# AAA Self Iteration Decision" in body["patches"][0]["content"]
    assert "Record model provenance" in body["patches"][0]["content"]
    assert "Promotion to the source repository requires separate human approval." in body["patches"][0]["content"]


def test_autopilot_model_decision_uses_safe_text_fallback_for_markdown(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    class TextGateway:
        async def chat(self, **kwargs):
            return SimpleNamespace(
                text="The next candidate iteration should record model provenance and promotion evidence.",
                provider="fake-provider",
                model="fake-model",
                finish_reason="stop",
                usage={"total_tokens": 12},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: TextGateway())
    response = TestClient(app).post("/api/autopilot/model-decision", json={
        "goal": "Plan an AAA candidate-only iteration",
        "candidate_workspace": str(candidate),
        "allowed_patch_paths": ["LOOP_ENGINEERING_SELF_ITERATION.md"],
        "model_policy": {"required": True, "provider": "fake"},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["model_backed"] is True
    assert body["text_fallback"] is True
    assert body["patches"][0]["path"] == "LOOP_ENGINEERING_SELF_ITERATION.md"
    assert "Model Output" in body["patches"][0]["content"]


def test_autopilot_model_decision_text_fallback_rejects_code_paths(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    class TextGateway:
        async def chat(self, **kwargs):
            return SimpleNamespace(
                text="Change Python code.",
                provider="fake-provider",
                model="fake-model",
                finish_reason="stop",
                usage=None,
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: TextGateway())
    response = TestClient(app).post("/api/autopilot/model-decision", json={
        "goal": "Plan an unsafe code fallback",
        "candidate_workspace": str(candidate),
        "allowed_patch_paths": ["backend/main.py"],
        "model_policy": {"required": True},
    })

    assert response.status_code == 422
    assert "text fallback" in response.json()["detail"]


def test_autopilot_code_iteration_returns_bounded_code_and_test_patches(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class CodeGateway:
        async def chat(self, **kwargs):
            return SimpleNamespace(
                text=(
                    '{"summary":"Expose candidate status for promotion evidence",'
                    '"capability_name":"candidate_loop_status","status_label":"candidate-ready",'
                    '"key_behaviors":["Return bounded status","Require human promotion"],'
                    '"validation":["Import helper","Assert approval flag"],"risk":"low"}'
                ),
                provider="fake-provider",
                model="fake-code-model",
                finish_reason="stop",
                usage={"total_tokens": 33},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: CodeGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Add a candidate-only self-iteration status helper",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-1",
        "run_id": "run-1",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/loop_engineering_candidate.py",
            "backend/tests/test_loop_engineering_candidate.py",
        ],
        "context_files": ["README.md"],
        "model_policy": {"required": True, "provider": "fake"},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "across-host-code-iteration/1.0"
    assert body["model_backed"] is True
    assert body["provider"] == "fake-provider"
    assert body["model"] == "fake-code-model"
    assert body["decision_hash"]
    paths = {patch["path"] for patch in body["patches"]}
    assert "backend/src/across_agents_assistant/loop_engineering_candidate.py" in paths
    assert "backend/tests/test_loop_engineering_candidate.py" in paths
    module = next(patch for patch in body["patches"] if patch["path"].endswith("loop_engineering_candidate.py"))
    assert "candidate_self_iteration_status" in module["content"]
    assert "candidate-ready" in module["content"]
    assert body["validation_commands"]


def test_autopilot_code_iteration_routes_codex_local_agent(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")
    captured = {}

    class LocalAgentClient:
        def send(self, message, *, target_agent=None, project_dir=None, timeout=None, model=None, **_kwargs):
            captured["message"] = message
            captured["target_agent"] = target_agent
            captured["project_dir"] = project_dir
            captured["timeout"] = timeout
            captured["model"] = model
            return SimpleNamespace(
                text=(
                    "OpenAI Codex v0.142.5\n"
                    "user\n"
                    "{\"schema_version\":\"request-json-that-must-not-be-parsed\"}\n"
                    "codex\n"
                    + json.dumps({
                        "summary": "Add Codex local-agent proof",
                        "risk": "low",
                        "patches": [{
                            "path": "backend/src/across_agents_assistant/codex_local_agent_probe.py",
                            "mode": "overwrite",
                            "content": "CODEX_LOCAL_AGENT_READY = True\n",
                        }],
                        "validation_commands": [{
                            "command": "python3",
                            "args": ["-m", "py_compile", "backend/src/across_agents_assistant/codex_local_agent_probe.py"],
                        }],
                    })
                    + "\ntokens used\n123\n"
                ),
                elapsed_sec=0.01,
                requires_approval=False,
            )

    class UnusedGateway:
        async def chat(self, **_kwargs):
            raise AssertionError("codex local agent policy must not use the gateway")

    monkeypatch.setattr(api_server, "get_local_agent_client", lambda: LocalAgentClient())
    monkeypatch.setattr(api_server, "get_gateway", lambda: UnusedGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Use the local Codex agent for candidate development",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-codex",
        "run_id": "run-codex",
        "allowed_patch_paths": ["backend/src/across_agents_assistant/codex_local_agent_probe.py"],
        "context_files": ["README.md"],
        "model_policy": {
            "required": True,
            "agent_id": "codex",
            "provider": "local-agent",
            "model": "codex",
            "direct_patches": True,
            "timeout_ms": 900000,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "local-agent"
    assert body["model"] == "codex"
    assert body["patches"][0]["path"] == "backend/src/across_agents_assistant/codex_local_agent_probe.py"
    assert captured["target_agent"] == "codex"
    assert captured["project_dir"] == str(candidate)
    assert captured["timeout"] == 900.0
    assert captured["model"] is None
    assert "Return JSON only" in captured["message"]


def test_autopilot_code_iteration_local_agent_falls_back_to_model_override(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")
    calls = []

    class LocalAgentClient:
        def send(self, message, *, target_agent=None, project_dir=None, timeout=None, model=None, **_kwargs):
            calls.append({
                "target_agent": target_agent,
                "project_dir": project_dir,
                "timeout": timeout,
                "model": model,
            })
            if len(calls) == 1:
                return SimpleNamespace(
                    text="抱歉，codex 执行超时（超过 180 秒），已自动终止。",
                    elapsed_sec=180.0,
                    requires_approval=False,
                    timed_out=True,
                    error_code="timeout",
                )
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Add fallback model proof",
                    "risk": "low",
                    "patches": [{
                        "path": "backend/src/across_agents_assistant/codex_fallback_probe.py",
                        "mode": "overwrite",
                        "content": "CODEX_FALLBACK_MODEL_READY = True\n",
                    }],
                    "validation_commands": [{
                        "command": "python3",
                        "args": ["-m", "py_compile", "backend/src/across_agents_assistant/codex_fallback_probe.py"],
                    }],
                }),
                elapsed_sec=0.01,
                requires_approval=False,
            )

    class UnusedGateway:
        async def chat(self, **_kwargs):
            raise AssertionError("codex local agent policy must not use the gateway")

    monkeypatch.setattr(api_server, "get_local_agent_client", lambda: LocalAgentClient())
    monkeypatch.setattr(api_server, "get_gateway", lambda: UnusedGateway())
    monkeypatch.setattr(local_agent_health, "discover_codex_models", lambda: {
        "available": True,
        "available_models": ["gpt-5.4-mini"],
    })
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Use a fallback local Codex model for candidate development",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-codex-fallback",
        "run_id": "run-codex-fallback",
        "allowed_patch_paths": ["backend/src/across_agents_assistant/codex_fallback_probe.py"],
        "context_files": ["README.md"],
        "model_policy": {
            "required": True,
            "agent_id": "codex",
            "provider": "local-agent",
            "model": "codex",
            "fallback_models": ["gpt-5-codex", "gpt-5.4-mini"],
            "direct_patches": True,
            "timeout_ms": 240000,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["patches"][0]["path"] == "backend/src/across_agents_assistant/codex_fallback_probe.py"
    assert [call["model"] for call in calls] == [None, "gpt-5.4-mini"]
    assert [call["timeout"] for call in calls] == [240.0, 240.0]


def test_autopilot_code_iteration_local_agent_timeout_returns_structured_failure(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class LocalAgentClient:
        def send(self, message, *, target_agent=None, project_dir=None, timeout=None, model=None, **_kwargs):
            return SimpleNamespace(
                text="抱歉，codex 执行超时（超过 180 秒），已自动终止。",
                elapsed_sec=180.0,
                requires_approval=False,
                timed_out=True,
                error_code="timeout",
            )

    class UnusedGateway:
        async def chat(self, **_kwargs):
            raise AssertionError("codex local agent policy must not use the gateway")

    monkeypatch.setattr(api_server, "get_local_agent_client", lambda: LocalAgentClient())
    monkeypatch.setattr(api_server, "get_gateway", lambda: UnusedGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Use the local Codex agent for candidate development",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-codex-timeout",
        "run_id": "run-codex-timeout",
        "allowed_patch_paths": ["backend/src/across_agents_assistant/codex_timeout_probe.py"],
        "context_files": ["README.md"],
        "model_policy": {
            "required": True,
            "agent_id": "codex",
            "provider": "local-agent",
            "model": "codex",
            "direct_patches": True,
            "timeout_ms": 240000,
        },
    })

    assert response.status_code == 504
    assert "local agent codex timed out" in response.json()["detail"]


def test_autopilot_code_iteration_accepts_direct_product_patches(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    module_content = (
        "from __future__ import annotations\n\n"
        "SELF_PROOF_ONLY_PATHS = {'loop_engineering_candidate.py', 'test_loop_engineering_candidate.py'}\n\n"
        "def evaluate_candidate_product_alignment(evidence):\n"
        "    changed = list(evidence.get('changed_files') or [])\n"
        "    blocking_reasons = []\n"
        "    if not changed:\n"
        "        blocking_reasons.append('candidate has no changed files')\n"
        "    if changed and all(any(token in path for token in SELF_PROOF_ONLY_PATHS) for path in changed):\n"
        "        blocking_reasons.append('candidate only proves loop execution')\n"
        "    return {\n"
        "        'promotion_recommendation': 'reject' if blocking_reasons else 'review',\n"
        "        'blocking_reasons': blocking_reasons,\n"
        "        'changed_file_count': len(changed),\n"
        "    }\n"
    )
    test_content = (
        "from across_agents_assistant.autopilot_candidate_quality import evaluate_candidate_product_alignment\n\n\n"
        "def test_alignment_reviews_product_change():\n"
        "    result = evaluate_candidate_product_alignment({'changed_files': ['backend/src/across_agents_assistant/autopilot_candidate_quality.py']})\n"
        "    assert result['promotion_recommendation'] == 'review'\n\n\n"
        "def test_alignment_rejects_self_proof_only_change():\n"
        "    result = evaluate_candidate_product_alignment({'changed_files': ['backend/src/across_agents_assistant/loop_engineering_candidate.py']})\n"
        "    assert result['promotion_recommendation'] == 'reject'\n"
    )

    class DirectPatchGateway:
        async def chat(self, **kwargs):
            assert "allowed_patch_paths" in kwargs["message"]
            assert "complete file content" in kwargs["system_prompt"]
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Add semantic product quality review helper",
                    "risk": "low",
                    "patches": [
                        {
                            "path": "backend/src/across_agents_assistant/autopilot_candidate_quality.py",
                            "mode": "overwrite",
                            "content": module_content,
                        },
                        {
                            "path": "backend/tests/test_autopilot_candidate_quality.py",
                            "mode": "overwrite",
                            "content": test_content,
                        },
                    ],
                    "validation_commands": [
                        {
                            "command": "python3",
                            "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_candidate_quality.py"],
                        }
                    ],
                }),
                provider="fake-provider",
                model="fake-code-model",
                finish_reason="stop",
                usage={"total_tokens": 66},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: DirectPatchGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Add a semantic candidate product quality helper",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-2",
        "run_id": "run-2",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_candidate_quality.py",
            "backend/tests/test_autopilot_candidate_quality.py",
        ],
        "context_files": ["README.md"],
        "model_policy": {
            "required": True,
            "provider": "fake",
            "direct_patches": True,
            "allow_host_code_fallback": True,
            "conformance_fixture": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "across-host-code-iteration/1.0"
    assert body["model_backed"] is True
    assert body["repaired_json"] is False
    assert body["text_fallback"] is False
    paths = {patch["path"] for patch in body["patches"]}
    assert paths == {
        "backend/src/across_agents_assistant/autopilot_candidate_quality.py",
        "backend/tests/test_autopilot_candidate_quality.py",
    }
    assert all(not patch["path"].endswith("loop_engineering_candidate.py") for patch in body["patches"])
    assert body["decision"]["patch_paths"] == [
        "backend/src/across_agents_assistant/autopilot_candidate_quality.py",
        "backend/tests/test_autopilot_candidate_quality.py",
    ]
    assert body["validation_commands"][0]["args"][-1].endswith("autopilot_candidate_quality.py")


def test_autopilot_code_iteration_downgrades_markerless_doc_upsert_to_append(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class DirectPatchGateway:
        async def chat(self, **kwargs):
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Add capability card note",
                    "risk": "low",
                    "patches": [
                        {
                            "path": "docs/loop_engineering_capability_cards.md",
                            "mode": "upsert_between_markers",
                            "content_lines": ["## Capability Cards", "", "- Keep cards evidence-backed."],
                        }
                    ],
                }),
                provider="fake-provider",
                model="fake-code-model",
                finish_reason="stop",
                usage={"total_tokens": 42},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: DirectPatchGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Add a small docs card.",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-doc-upsert",
        "run_id": "run-doc-upsert",
        "allowed_patch_paths": ["docs/loop_engineering_capability_cards.md"],
        "context_files": ["README.md"],
        "model_policy": {"required": True, "provider": "fake", "direct_patches": True},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["patches"][0]["path"] == "docs/loop_engineering_capability_cards.md"
    assert body["patches"][0]["mode"] == "append"
    assert "marker_start" not in body["patches"][0]
    assert body["text_fallback"] is False


def test_autopilot_code_iteration_repairs_markerless_code_upsert(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class MarkerRepairGateway:
        def __init__(self):
            self.calls = 0

        async def chat(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(
                    text=json.dumps({
                        "summary": "Bad markerless code upsert",
                        "risk": "low",
                        "patches": [
                            {
                                "path": "backend/src/across_agents_assistant/autopilot_code_marker.py",
                                "mode": "upsert_between_markers",
                                "content": "VALUE = 'bad'\n",
                            }
                        ],
                    }),
                    provider="fake-provider",
                    model="fake-code-model",
                    finish_reason="stop",
                    usage={"total_tokens": 25},
                )
            assert "without marker_start and marker_end" in kwargs["message"]
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Repair markerless code upsert",
                    "risk": "low",
                    "patches": [
                        {
                            "path": "backend/src/across_agents_assistant/autopilot_code_marker.py",
                            "mode": "overwrite",
                            "content": "VALUE = 'fixed'\n",
                        }
                    ],
                }),
                provider="fake-provider",
                model="fake-code-model",
                finish_reason="stop",
                usage={"total_tokens": 30},
            )

    gateway = MarkerRepairGateway()
    monkeypatch.setattr(api_server, "get_gateway", lambda: gateway)
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Add a small code helper.",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-code-upsert",
        "run_id": "run-code-upsert",
        "allowed_patch_paths": ["backend/src/across_agents_assistant/autopilot_code_marker.py"],
        "context_files": ["README.md"],
        "model_policy": {
            "required": True,
            "provider": "fake",
            "direct_patches": True,
            "direct_patch_repair_attempts": 1,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert gateway.calls == 2
    assert body["repaired_json"] is True
    assert body["patches"][0]["mode"] == "overwrite"
    assert body["patches"][0]["content"] == "VALUE = 'fixed'\n"


def test_autopilot_code_iteration_repairs_pytest_imports(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class PytestRepairGateway:
        def __init__(self):
            self.calls = 0

        async def chat(self, **kwargs):
            self.calls += 1
            test_content = (
                "import pytest\n\n\n"
                "def test_bad_pytest_dependency():\n"
                "    with pytest.raises(ValueError):\n"
                "        raise ValueError('x')\n"
            )
            if self.calls > 1:
                assert "standard-library only" in kwargs["system_prompt"]
                assert "pytest imports/usages" in kwargs["message"]
                test_content = (
                    "from across_agents_assistant.autopilot_candidate_quality import candidate_quality_status\n\n\n"
                    "def test_candidate_quality_status():\n"
                    "    assert candidate_quality_status()['status'] == 'reviewable'\n"
                )
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Add candidate quality status",
                    "risk": "low",
                    "patches": [
                        {
                            "path": "backend/src/across_agents_assistant/autopilot_candidate_quality.py",
                            "mode": "overwrite",
                            "content": "def candidate_quality_status():\n    return {'status': 'reviewable'}\n",
                        },
                        {
                            "path": "backend/tests/test_autopilot_candidate_quality.py",
                            "mode": "overwrite",
                            "content": test_content,
                        },
                    ],
                    "validation_commands": [
                        {
                            "command": "python3",
                            "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_candidate_quality.py"],
                        }
                    ],
                }),
                provider="fake-provider",
                model="fake-code-model",
                finish_reason="stop",
                usage={"total_tokens": 66},
            )

    gateway = PytestRepairGateway()
    monkeypatch.setattr(api_server, "get_gateway", lambda: gateway)
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Add a candidate quality helper",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-pytest-repair",
        "run_id": "run-pytest-repair",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_candidate_quality.py",
            "backend/tests/test_autopilot_candidate_quality.py",
        ],
        "context_files": ["README.md"],
        "model_policy": {
            "required": True,
            "provider": "fake",
            "direct_patches": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert gateway.calls == 2
    assert body["repaired_json"] is True
    test_patch = next(patch for patch in body["patches"] if patch["path"].startswith("backend/tests/"))
    assert "pytest" not in test_patch["content"]


def test_autopilot_code_iteration_repairs_flat_autopilot_imports(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class FlatImportRepairGateway:
        def __init__(self):
            self.calls = 0

        async def chat(self, **kwargs):
            self.calls += 1
            test_content = (
                "from autopilot_tool_pack_catalog import parse_tool_packs\n\n\n"
                "def test_parse_tool_packs():\n"
                "    assert parse_tool_packs([]) == []\n"
            )
            if self.calls > 1:
                assert "flat autopilot_* imports" in kwargs["message"]
                test_content = (
                    "from across_agents_assistant.autopilot_tool_pack_catalog import parse_tool_packs\n\n\n"
                    "def test_parse_tool_packs():\n"
                    "    assert parse_tool_packs([]) == []\n"
                )
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Add candidate tool pack catalog",
                    "risk": "low",
                    "patches": [
                        {
                            "path": "backend/src/across_agents_assistant/autopilot_tool_pack_catalog.py",
                            "mode": "overwrite",
                            "content": "def parse_tool_packs(items):\n    return list(items)\n",
                        },
                        {
                            "path": "backend/tests/test_autopilot_tool_pack_catalog.py",
                            "mode": "overwrite",
                            "content": test_content,
                        },
                    ],
                    "validation_commands": [
                        {
                            "command": "python3",
                            "args": [
                                "-m",
                                "py_compile",
                                "backend/src/across_agents_assistant/autopilot_tool_pack_catalog.py",
                                "backend/tests/test_autopilot_tool_pack_catalog.py",
                            ],
                        }
                    ],
                }),
                provider="fake-provider",
                model="fake-code-model",
                finish_reason="stop",
                usage={"total_tokens": 88},
            )

    gateway = FlatImportRepairGateway()
    monkeypatch.setattr(api_server, "get_gateway", lambda: gateway)
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Add a candidate tool pack catalog helper",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-flat-import-repair",
        "run_id": "run-flat-import-repair",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_tool_pack_catalog.py",
            "backend/tests/test_autopilot_tool_pack_catalog.py",
        ],
        "context_files": ["README.md"],
        "model_policy": {
            "required": True,
            "provider": "fake",
            "direct_patches": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert gateway.calls == 2
    assert body["repaired_json"] is True
    test_patch = next(patch for patch in body["patches"] if patch["path"].startswith("backend/tests/"))
    assert "from across_agents_assistant.autopilot_tool_pack_catalog import parse_tool_packs" in test_patch["content"]


def test_autopilot_code_iteration_conformance_can_fall_back_to_tool_pack_policy(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class InvalidJsonGateway:
        async def chat(self, **kwargs):
            return SimpleNamespace(
                text="not json",
                provider="fake-provider",
                model="fake-code-model",
                finish_reason="stop",
                usage={},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: InvalidJsonGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Add a Tool Pack policy helper",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-tool-pack",
        "run_id": "run-tool-pack",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_tool_pack_policy.py",
            "backend/tests/test_autopilot_tool_pack_policy.py",
        ],
        "context_files": ["README.md"],
        "model_policy": {
            "required": True,
            "provider": "fake",
            "direct_patches": True,
            "allow_host_code_fallback": True,
            "conformance_fixture": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    paths = {patch["path"] for patch in body["patches"]}
    assert paths == {
        "backend/src/across_agents_assistant/autopilot_tool_pack_policy.py",
        "backend/tests/test_autopilot_tool_pack_policy.py",
    }
    assert body["text_fallback"] is True
    assert body["decision"]["summary"] == "Add autonomous Tool Pack policy helper."
    module = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_tool_pack_policy.py"))
    assert "evaluate_tool_pack_candidate" in module["content"]


def test_autopilot_code_iteration_production_rejects_host_code_fallback(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class InvalidJsonGateway:
        async def chat(self, **kwargs):
            return SimpleNamespace(
                text="not json",
                provider="fake-provider",
                model="fake-code-model",
                finish_reason="stop",
                usage={},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: InvalidJsonGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Add a Tool Pack policy helper",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-tool-pack",
        "run_id": "run-tool-pack",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_tool_pack_policy.py",
            "backend/tests/test_autopilot_tool_pack_policy.py",
        ],
        "context_files": ["README.md"],
        "model_policy": {"required": True, "provider": "fake", "direct_patches": True},
    })

    assert response.status_code == 422
    assert "host code fallback is disabled" in response.json()["detail"]


def test_autopilot_code_iteration_validation_repair_can_use_whitelisted_host_fallback(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class BrokenRepairGateway:
        def __init__(self):
            self.calls = 0

        async def chat(self, **kwargs):
            self.calls += 1
            return SimpleNamespace(
                text="<think>invalid repair json</think>",
                provider="minimax",
                model="MiniMax-M3",
                finish_reason="length",
                usage={"total_tokens": 12},
            )

    gateway = BrokenRepairGateway()
    monkeypatch.setattr(api_server, "get_gateway", lambda: gateway)
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair autonomous backlog builder",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-backlog-fallback",
        "run_id": "run-backlog-fallback",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_backlog_builder.py",
            "backend/tests/test_autopilot_backlog_builder.py",
        ],
        "context_files": ["README.md"],
        "validation_feedback": [
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_backlog_builder.py"],
                "status": "failed",
                "stderr": "SyntaxError: EOL while scanning string literal",
            }
        ],
        "model_policy": {"required": True, "provider": "minimax", "model": "MiniMax-M3", "direct_patches": True},
    })

    assert response.status_code == 200
    body = response.json()
    assert gateway.calls >= 2
    assert body["host_validation_repair_fallback"] is True
    assert body["text_fallback"] is True
    paths = {patch["path"] for patch in body["patches"]}
    assert paths == {
        "backend/src/across_agents_assistant/autopilot_backlog_builder.py",
        "backend/tests/test_autopilot_backlog_builder.py",
    }
    test_patch = next(patch for patch in body["patches"] if patch["path"].startswith("backend/tests/"))
    assert "pytest" not in test_patch["content"]
    assert "rank_backlog_candidates" in test_patch["content"]


def test_autopilot_code_iteration_validation_repair_can_fallback_platform_self_repair_replay(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair platform self-repair replay coverage",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-platform-repair",
        "run_id": "run-platform-repair",
        "target_repo": "across-autopilot",
        "allowed_patch_paths": ["tests/platform-self-repair.test.js"],
        "context_files": ["src/platform-self-repair.js"],
        "validation_feedback": [
            {
                "repo": "across-autopilot",
                "command": "node",
                "args": ["--test", "tests/platform-self-repair.test.js"],
                "status": "failed",
                "stderr": "Unsupported schema_version: 1.0",
            }
        ],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "model": "MiniMax-M3",
            "direct_patches": True,
            "allow_host_validation_repair_fallback": True,
        },
        "validation_commands": [
            {"repo": "across-autopilot", "command": "node", "args": ["--test", "tests/platform-self-repair.test.js"]}
        ],
    })

    assert response.status_code == 200
    body = response.json()
    assert body["host_validation_repair_fallback"] is True
    assert body["text_fallback"] is True
    assert body["patches"][0]["path"] == "tests/platform-self-repair.test.js"
    assert body["decision"]["patch_paths"] == ["tests/platform-self-repair.test.js"]
    assert "autopilot-self-repair-replay-fixture" in body["patches"][0]["content"]
    assert "api_key: fakeKey" in body["patches"][0]["content"]


def test_autopilot_code_iteration_validation_repair_can_fallback_loop_backlog(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class BrokenRepairGateway:
        def __init__(self):
            self.calls = 0

        async def chat(self, **kwargs):
            self.calls += 1
            return SimpleNamespace(
                text="<think>invalid repair json</think>",
                provider="minimax",
                model="MiniMax-M3",
                finish_reason="length",
                usage={"total_tokens": 12},
            )

    gateway = BrokenRepairGateway()
    monkeypatch.setattr(api_server, "get_gateway", lambda: gateway)
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair autonomous loop backlog selector",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-loop-backlog-fallback",
        "run_id": "run-loop-backlog-fallback",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_loop_backlog.py",
            "backend/tests/test_autopilot_loop_backlog.py",
        ],
        "context_files": ["README.md"],
        "validation_feedback": [
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_loop_backlog.py"],
                "status": "failed",
                "stderr": "SyntaxError: closing parenthesis does not match opening bracket",
            }
        ],
        "model_policy": {"required": True, "provider": "minimax", "model": "MiniMax-M3", "direct_patches": True},
    })

    assert response.status_code == 200
    body = response.json()
    assert gateway.calls >= 2
    assert body["host_validation_repair_fallback"] is True
    assert body["text_fallback"] is True
    paths = {patch["path"] for patch in body["patches"]}
    assert paths == {
        "backend/src/across_agents_assistant/autopilot_loop_backlog.py",
        "backend/tests/test_autopilot_loop_backlog.py",
    }
    test_patch = next(patch for patch in body["patches"] if patch["path"].startswith("backend/tests/"))
    assert "pytest" not in test_patch["content"]
    assert "TemporaryDirectory" in test_patch["content"]
    assert "build_loop_backlog" in test_patch["content"]


def test_autopilot_code_iteration_explicit_validation_fallback_handles_source_quality(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class UnexpectedGateway:
        async def chat(self, **kwargs):
            raise AssertionError("explicit validation fallback should not call the model")

    monkeypatch.setattr(api_server, "get_gateway", lambda: UnexpectedGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair source quality triage helper",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-source-quality-fallback",
        "run_id": "run-source-quality-fallback",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_source_quality.py",
            "backend/tests/test_autopilot_source_quality.py",
        ],
        "context_files": ["README.md"],
        "validation_feedback": [
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": ["backend/tests/test_autopilot_source_quality.py"],
                "status": "failed",
                "stderr": "AssertionError: missing status should be failed",
            }
        ],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "model": "MiniMax-M3",
            "direct_patches": True,
            "allow_host_validation_repair_fallback": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["host_validation_repair_fallback"] is True
    assert body["text_fallback"] is True
    assert body["finish_reason"] == "host_validation_repair_fallback"
    paths = {patch["path"] for patch in body["patches"]}
    assert paths == {
        "backend/src/across_agents_assistant/autopilot_source_quality.py",
        "backend/tests/test_autopilot_source_quality.py",
    }
    module = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_source_quality.py"))
    test_patch = next(patch for patch in body["patches"] if patch["path"].startswith("backend/tests/"))
    assert "triage_sources" in module["content"]
    assert "test_triage_flags_missing_status_as_failed" in test_patch["content"]
    assert "pytest" not in test_patch["content"]


def test_autopilot_code_iteration_explicit_validation_fallback_handles_generic_autopilot_pair(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class UnexpectedGateway:
        async def chat(self, **kwargs):
            raise AssertionError("explicit validation fallback should not call the model")

    monkeypatch.setattr(api_server, "get_gateway", lambda: UnexpectedGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair context budget helper",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-context-budget-fallback",
        "run_id": "run-context-budget-fallback",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_context_budget.py",
            "backend/tests/test_autopilot_context_budget.py",
        ],
        "context_files": ["README.md"],
        "validation_feedback": [
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_context_budget.py"],
                "status": "failed",
                "stderr": "SyntaxError: unterminated string literal",
            }
        ],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "model": "MiniMax-M3",
            "direct_patches": True,
            "allow_host_validation_repair_fallback": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["host_validation_repair_fallback"] is True
    assert body["text_fallback"] is True
    paths = {patch["path"] for patch in body["patches"]}
    assert paths == {
        "backend/src/across_agents_assistant/autopilot_context_budget.py",
        "backend/tests/test_autopilot_context_budget.py",
    }
    module = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_context_budget.py"))
    test_patch = next(patch for patch in body["patches"] if patch["path"].startswith("backend/tests/"))
    assert "evaluate_candidate_signal" in module["content"]
    assert "from across_agents_assistant.autopilot_context_budget import evaluate_candidate_signal" in test_patch["content"]
    assert "pytest" not in test_patch["content"]


def test_autopilot_code_iteration_validation_fallback_repairs_iteration_telemetry_integration(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    source = tmp_path / "source"
    workbench_path = source / "backend/src/across_agents_assistant/autopilot_workbench.py"
    workbench_path.parent.mkdir(parents=True)
    workbench_path.write_text(
        "def build_autopilot_workbench_snapshot(*, registry=None):\n"
        "    return {'status': 'source', 'registry': registry}\n",
        encoding="utf-8",
    )

    class UnexpectedGateway:
        async def chat(self, **kwargs):
            raise AssertionError("iteration telemetry validation fallback should not call the model")

    monkeypatch.setattr(api_server, "get_gateway", lambda: UnexpectedGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair autonomous iteration telemetry integration",
        "candidate_workspace": str(candidate),
        "source_repository": str(source),
        "candidate_id": "cand-telemetry-fallback",
        "run_id": "run-telemetry-fallback",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_workbench.py",
            "backend/src/across_agents_assistant/autopilot_iteration_telemetry.py",
            "backend/tests/test_autopilot_iteration_telemetry.py",
        ],
        "context_files": ["backend/src/across_agents_assistant/autopilot_workbench.py"],
        "validation_feedback": [
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": ["-c", "from across_agents_assistant.autopilot_iteration_telemetry import IterationTelemetryRecord"],
                "status": "failed",
                "stderr": "AttributeError: 'str' object has no attribute 'to_dict'",
                "diagnostic": {"failure_kind": "candidate_exception"},
            },
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": ["-c", "AAA backend API import contract smoke"],
                "status": "failed",
                "stderr": "ImportError: missing internal API import(s): across_agents_assistant.autopilot_workbench.build_autopilot_workbench_snapshot",
                "diagnostic": {"failure_kind": "candidate_import_failure"},
            },
        ],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "model": "MiniMax-M3",
            "direct_patches": True,
            "allow_host_validation_repair_fallback": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["host_validation_repair_fallback"] is True
    assert body["text_fallback"] is True
    paths = {patch["path"] for patch in body["patches"]}
    assert paths == {
        "backend/src/across_agents_assistant/autopilot_workbench.py",
        "backend/src/across_agents_assistant/autopilot_iteration_telemetry.py",
        "backend/tests/test_autopilot_iteration_telemetry.py",
    }
    module = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_iteration_telemetry.py"))
    test_patch = next(patch for patch in body["patches"] if patch["path"].startswith("backend/tests/"))
    workbench = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_workbench.py"))
    assert "class IterationTelemetryRecord" in module["content"]
    assert "sources=['source-a']" in test_patch["content"]
    assert "pytest" not in test_patch["content"]
    assert "build_iteration_telemetry_snapshot" in workbench["content"]
    _assert_marker_upsert(workbench, "# ACROSS ITERATION TELEMETRY START", "# ACROSS ITERATION TELEMETRY END")


def test_autopilot_code_iteration_validation_fallback_repairs_capability_gap_manifest(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    source = tmp_path / "source"
    workbench_path = source / "backend/src/across_agents_assistant/autopilot_workbench.py"
    workbench_path.parent.mkdir(parents=True)
    workbench_path.write_text(
        "def build_autopilot_workbench_snapshot(*, registry=None):\n"
        "    return {'status': 'source', 'registry': registry}\n",
        encoding="utf-8",
    )

    class UnexpectedGateway:
        async def chat(self, **kwargs):
            raise AssertionError("capability-gap validation fallback should not call the model")

    monkeypatch.setattr(api_server, "get_gateway", lambda: UnexpectedGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair capability-gap manifest helper",
        "candidate_workspace": str(candidate),
        "source_repository": str(source),
        "candidate_id": "cand-capability-gap-fallback",
        "run_id": "run-capability-gap-fallback",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_workbench.py",
            "backend/src/across_agents_assistant/autopilot_capability_gap_manifest.py",
            "backend/tests/test_autopilot_capability_gap_manifest.py",
        ],
        "context_files": ["backend/src/across_agents_assistant/autopilot_workbench.py"],
        "validation_feedback": [
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": [
                    "-c",
                    "mod=runpy.run_path('backend/src/across_agents_assistant/autopilot_capability_gap_manifest.py'); "
                    "compute=mod['compute_gap_manifest']",
                ],
                "status": "failed",
                "stderr": "KeyError: 'compute_gap_manifest'",
                "diagnostic": {"failure_kind": "candidate_exception"},
            }
        ],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "model": "MiniMax-M3",
            "direct_patches": True,
            "allow_host_validation_repair_fallback": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["host_validation_repair_fallback"] is True
    assert body["text_fallback"] is True
    paths = {patch["path"] for patch in body["patches"]}
    assert paths == {
        "backend/src/across_agents_assistant/autopilot_workbench.py",
        "backend/src/across_agents_assistant/autopilot_capability_gap_manifest.py",
        "backend/tests/test_autopilot_capability_gap_manifest.py",
    }
    module = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_capability_gap_manifest.py"))
    test_patch = next(patch for patch in body["patches"] if patch["path"].startswith("backend/tests/"))
    workbench = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_workbench.py"))
    namespace = {}
    exec(compile(module["content"], module["path"], "exec"), namespace)
    manifest = namespace["compute_gap_manifest"](
        {"signals": [{"id": "loop-engineering-architecture-signal", "status": "passed", "excerpt": "manual", "keywords": ["tool", "review"]}]},
        {"candidate_targets": [{"id": "target", "source_refs": ["loop-engineering-architecture-signal"], "semantic_review": {"require_model_backed": True}}]},
    )
    assert manifest["entries"][0]["evidence_strength"] == "weak"
    assert "compute_gap_manifest" in module["content"]
    assert "test_compute_gap_manifest_demotes_for_required_model_backing" in test_patch["content"]
    assert "build_capability_gap_manifest_snapshot" in workbench["content"]
    _assert_marker_upsert(workbench, "# ACROSS CAPABILITY GAP MANIFEST START", "# ACROSS CAPABILITY GAP MANIFEST END")


def test_autopilot_code_iteration_validation_fallback_repairs_mcp_descriptors(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    source = tmp_path / "source"
    workbench_path = source / "backend/src/across_agents_assistant/autopilot_workbench.py"
    pack_path = source / "backend/src/across_agents_assistant/loop_engineering_capability_pack.py"
    workbench_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    workbench_path.write_text(
        "def build_autopilot_workbench_snapshot(*, registry=None):\n"
        "    return {'status': 'source', 'registry': registry}\n",
        encoding="utf-8",
    )
    pack_path.write_text(
        "def build_loop_engineering_capability_pack():\n"
        "    return {'ready': []}\n",
        encoding="utf-8",
    )

    class UnexpectedGateway:
        async def chat(self, **kwargs):
            raise AssertionError("mcp descriptor validation fallback should not call the model")

    monkeypatch.setattr(api_server, "get_gateway", lambda: UnexpectedGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair MCP descriptor registry integration",
        "candidate_workspace": str(candidate),
        "source_repository": str(source),
        "candidate_id": "cand-mcp-descriptor-fallback",
        "run_id": "run-mcp-descriptor-fallback",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_workbench.py",
            "backend/src/across_agents_assistant/loop_engineering_capability_pack.py",
            "backend/src/across_agents_assistant/autopilot_mcp_descriptors.py",
            "backend/tests/test_autopilot_mcp_descriptors.py",
        ],
        "context_files": [
            "backend/src/across_agents_assistant/autopilot_workbench.py",
            "backend/src/across_agents_assistant/loop_engineering_capability_pack.py",
        ],
        "validation_feedback": [
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": ["-c", "runpy.run_path('backend/tests/test_autopilot_mcp_descriptors.py')"],
                "status": "failed",
                "stderr": (
                    "ImportError: cannot import name 'describe_default_registry' "
                    "from 'across_agents_assistant.autopilot_mcp_descriptors'"
                ),
                "diagnostic": {"failure_kind": "candidate_import_failure"},
            }
        ],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "model": "MiniMax-M3",
            "direct_patches": True,
            "allow_host_validation_repair_fallback": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["host_validation_repair_fallback"] is True
    assert body["text_fallback"] is True
    paths = {patch["path"] for patch in body["patches"]}
    assert paths == {
        "backend/src/across_agents_assistant/autopilot_workbench.py",
        "backend/src/across_agents_assistant/loop_engineering_capability_pack.py",
        "backend/src/across_agents_assistant/autopilot_mcp_descriptors.py",
        "backend/tests/test_autopilot_mcp_descriptors.py",
    }
    module = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_mcp_descriptors.py"))
    workbench = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_workbench.py"))
    pack = next(patch for patch in body["patches"] if patch["path"].endswith("loop_engineering_capability_pack.py"))
    test_patch = next(patch for patch in body["patches"] if patch["path"].startswith("backend/tests/"))
    namespace = {}
    exec(compile(module["content"], module["path"], "exec"), namespace)
    registry = namespace["describe_default_registry"]()
    assert registry.render()["summary"] == {"tool_count": 1, "prompt_count": 1, "resource_count": 1}
    assert namespace["default_registry"]().list_tools()[0]["name"] == "loop_status"
    _assert_marker_upsert(workbench, "# ACROSS MCP DESCRIPTORS WORKBENCH START", "# ACROSS MCP DESCRIPTORS WORKBENCH END")
    _assert_marker_upsert(pack, "# ACROSS MCP DESCRIPTORS CAPABILITY PACK START", "# ACROSS MCP DESCRIPTORS CAPABILITY PACK END")
    assert "test_workbench_and_capability_pack_surface" in test_patch["content"]


def test_autopilot_code_iteration_validation_fallback_repairs_mcp_tool_manifest(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    source = tmp_path / "source"
    api_path = source / "backend/src/across_agents_assistant/api_server.py"
    api_path.parent.mkdir(parents=True, exist_ok=True)
    api_path.write_text(
        "from fastapi import FastAPI\n\n"
        "app = FastAPI()\n",
        encoding="utf-8",
    )

    class UnexpectedGateway:
        async def chat(self, **kwargs):
            raise AssertionError("mcp tool manifest validation fallback should not call the model")

    monkeypatch.setattr(api_server, "get_gateway", lambda: UnexpectedGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair MCP tool manifest validator integration",
        "candidate_workspace": str(candidate),
        "source_repository": str(source),
        "candidate_id": "cand-mcp-tool-manifest-fallback",
        "run_id": "run-mcp-tool-manifest-fallback",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/api_server.py",
            "backend/src/across_agents_assistant/autopilot_mcp_tool_manifest.py",
            "backend/tests/test_autopilot_mcp_tool_manifest.py",
        ],
        "context_files": ["backend/src/across_agents_assistant/api_server.py"],
        "validation_feedback": [
            {
                "repo": "across-agents-assistant",
                "command": "candidate_quality",
                "args": [],
                "status": "failed",
                "stderr": "unintegrated_candidate_helper: autopilot_mcp_tool_manifest.py adds isolated helper",
                "diagnostic": {"failure_kind": "candidate_quality_failure"},
            },
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": ["-c", "runpy.run_path('backend/tests/test_autopilot_mcp_tool_manifest.py')"],
                "status": "failed",
                "stderr": "ModuleNotFoundError: No module named 'uvicorn'",
                "diagnostic": {"failure_kind": "candidate_import_failure"},
            },
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": ["-c", "AAA backend API import contract smoke"],
                "status": "failed",
                "stderr": (
                    "ImportError: missing internal API import(s): "
                    "across_agents_assistant.autopilot_mcp_tool_manifest.TOOL_DESCRIPTORS, "
                    "across_agents_assistant.autopilot_mcp_tool_manifest.validate_tool_manifests"
                ),
                "diagnostic": {"failure_kind": "candidate_import_failure"},
            },
        ],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "model": "MiniMax-M3",
            "direct_patches": True,
            "allow_host_validation_repair_fallback": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["host_validation_repair_fallback"] is True
    assert body["text_fallback"] is True
    paths = {patch["path"] for patch in body["patches"]}
    assert paths == {
        "backend/src/across_agents_assistant/api_server.py",
        "backend/src/across_agents_assistant/autopilot_mcp_tool_manifest.py",
        "backend/tests/test_autopilot_mcp_tool_manifest.py",
    }
    module = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_mcp_tool_manifest.py"))
    api_patch = next(patch for patch in body["patches"] if patch["path"].endswith("api_server.py"))
    test_patch = next(patch for patch in body["patches"] if patch["path"].startswith("backend/tests/"))
    namespace = {}
    exec(compile(module["content"], module["path"], "exec"), namespace)
    tools = namespace["get_registered_tools"]()
    assert tools[0]["name"] == "loop_engineering_manifest_validate"
    assert namespace["mcp_tool_manifest_snapshot"]()["promotion_requires_human_review"] is True
    _assert_marker_upsert(api_patch, "# ACROSS MCP TOOL MANIFEST REGISTRATION START", "# ACROSS MCP TOOL MANIFEST REGISTRATION END")
    assert "ACROSS_MCP_TOOL_DESCRIPTORS" in api_patch["content"]
    assert "test_api_server_registration_marker_is_lightweight" in test_patch["content"]
    assert "import_module(\"across_agents_assistant.api_server\")" not in test_patch["content"]


def test_autopilot_code_iteration_validation_fallback_accepts_tool_manifest_alias(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    source = tmp_path / "source"
    api_path = source / "backend/src/across_agents_assistant/api_server.py"
    api_path.parent.mkdir(parents=True, exist_ok=True)
    api_path.write_text("from fastapi import FastAPI\n\napp = FastAPI()\n", encoding="utf-8")

    class UnexpectedGateway:
        async def chat(self, **kwargs):
            raise AssertionError("tool manifest alias fallback should not call the model")

    monkeypatch.setattr(api_server, "get_gateway", lambda: UnexpectedGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair AAA MCP tool manifest endpoint",
        "candidate_workspace": str(candidate),
        "source_repository": str(source),
        "candidate_id": "cand-tool-manifest-alias-fallback",
        "run_id": "run-tool-manifest-alias-fallback",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/api_server.py",
            "backend/src/across_agents_assistant/loop_engineering_capability_pack.py",
            "backend/src/across_agents_assistant/autopilot_tool_manifest.py",
            "backend/tests/test_autopilot_tool_manifest.py",
        ],
        "context_files": ["backend/src/across_agents_assistant/api_server.py"],
        "validation_feedback": [
            {
                "repo": "across-agents-assistant",
                "command": "candidate_quality",
                "args": [],
                "status": "failed",
                "stderr": (
                    "destructive_product_entrypoint_rewrite: "
                    "backend/src/across_agents_assistant/api_server.py: line 1: destructive rewrite"
                ),
                "diagnostic": {"failure_kind": "candidate_quality_failure"},
            },
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": ["-m", "py_compile", "backend/tests/test_autopilot_tool_manifest.py"],
                "status": "failed",
                "stderr": "SyntaxError: unterminated string literal in test_autopilot_tool_manifest.py",
                "diagnostic": {"failure_kind": "validation_command_failed"},
            },
        ],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "model": "MiniMax-M3",
            "direct_patches": True,
            "allow_host_validation_repair_fallback": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["host_validation_repair_fallback"] is True
    paths = {patch["path"] for patch in body["patches"]}
    assert paths == {
        "backend/src/across_agents_assistant/api_server.py",
        "backend/src/across_agents_assistant/autopilot_tool_manifest.py",
        "backend/tests/test_autopilot_tool_manifest.py",
    }
    module = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_tool_manifest.py"))
    api_patch = next(patch for patch in body["patches"] if patch["path"].endswith("api_server.py"))
    test_patch = next(patch for patch in body["patches"] if patch["path"].startswith("backend/tests/"))
    namespace = {}
    exec(compile(module["content"], module["path"], "exec"), namespace)
    assert namespace["mcp_tool_manifest_snapshot"]()["summary"]["tool_count"] == 1
    _assert_marker_upsert(api_patch, "# ACROSS MCP TOOL MANIFEST REGISTRATION START", "# ACROSS MCP TOOL MANIFEST REGISTRATION END")
    assert "autopilot_tool_manifest" in api_patch["content"]
    assert "from across_agents_assistant.autopilot_tool_manifest import" in test_patch["content"]


def test_autopilot_code_iteration_validation_fallback_repairs_mcp_tool_registry(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    source = tmp_path / "source"
    workbench_path = source / "backend/src/across_agents_assistant/autopilot_workbench.py"
    workbench_path.parent.mkdir(parents=True, exist_ok=True)
    workbench_path.write_text(
        "def build_autopilot_workbench_snapshot(*, registry=None):\n"
        "    return {'status': 'source', 'registry': registry}\n",
        encoding="utf-8",
    )

    class UnexpectedGateway:
        async def chat(self, **kwargs):
            raise AssertionError("mcp tool registry validation fallback should not call the model")

    monkeypatch.setattr(api_server, "get_gateway", lambda: UnexpectedGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair MCP tool registry integration",
        "candidate_workspace": str(candidate),
        "source_repository": str(source),
        "candidate_id": "cand-mcp-tool-registry-fallback",
        "run_id": "run-mcp-tool-registry-fallback",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_workbench.py",
            "backend/src/across_agents_assistant/autopilot_mcp_tool_registry.py",
            "backend/tests/test_autopilot_mcp_tool_registry.py",
        ],
        "context_files": ["backend/src/across_agents_assistant/autopilot_workbench.py"],
        "validation_feedback": [
            {
                "repo": "across-agents-assistant",
                "command": "candidate_app_lifecycle",
                "args": [],
                "status": "failed",
                "stderr": (
                    "ImportError: cannot import name 'MCPToolRegistry' from "
                    "'across_agents_assistant.autopilot_mcp_tool_registry'"
                ),
                "diagnostic": {"failure_kind": "candidate_import_failure"},
            }
        ],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "model": "MiniMax-M3",
            "direct_patches": True,
            "allow_host_validation_repair_fallback": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["host_validation_repair_fallback"] is True
    assert body["text_fallback"] is True
    paths = {patch["path"] for patch in body["patches"]}
    assert paths == {
        "backend/src/across_agents_assistant/autopilot_workbench.py",
        "backend/src/across_agents_assistant/autopilot_mcp_tool_registry.py",
        "backend/tests/test_autopilot_mcp_tool_registry.py",
    }
    module = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_mcp_tool_registry.py"))
    workbench = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_workbench.py"))
    test_patch = next(patch for patch in body["patches"] if patch["path"].startswith("backend/tests/"))
    namespace = {}
    exec(compile(module["content"], module["path"], "exec"), namespace)
    snapshot = namespace["describe_default_registry"]()
    assert snapshot["schema_version"] == "across-aaa-mcp-tool-registry/1.0"
    assert snapshot["summary"]["tool_count"] == 1
    assert namespace["DEFAULT_REGISTRY"].get_tool("loop_engineering_manifest_validate")["annotations"]["readOnlyHint"] is True
    _assert_marker_upsert(workbench, "# ACROSS MCP TOOL REGISTRY WORKBENCH START", "# ACROSS MCP TOOL REGISTRY WORKBENCH END")
    assert "def get_mcp_tool_registry()" in workbench["content"]
    assert "from .autopilot_mcp_tool_registry import DEFAULT_REGISTRY" in workbench["content"]
    assert "test_integration_marker_uses_delayed_imports" in test_patch["content"]
    assert "import across_agents_assistant.api_server" not in test_patch["content"]


def test_autopilot_code_iteration_validation_fallback_repairs_mcp_tool_registry_api_capability_pack(
    monkeypatch, tmp_path
):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    source = tmp_path / "source"
    api_path = source / "backend/src/across_agents_assistant/api_server.py"
    capability_path = source / "backend/src/across_agents_assistant/loop_engineering_capability_pack.py"
    api_path.parent.mkdir(parents=True, exist_ok=True)
    api_path.write_text(
        "from fastapi import FastAPI\n\n"
        "app = FastAPI()\n\n\n"
        "def start_api_server():\n"
        "    return None\n",
        encoding="utf-8",
    )
    capability_path.write_text(
        "def loop_engineering_capability_pack():\n"
        "    return {'status': 'source'}\n",
        encoding="utf-8",
    )

    class UnexpectedGateway:
        async def chat(self, **kwargs):
            raise AssertionError("mcp tool registry validation fallback should not call the model")

    monkeypatch.setattr(api_server, "get_gateway", lambda: UnexpectedGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair MCP tool descriptor registry integration",
        "candidate_workspace": str(candidate),
        "source_repository": str(source),
        "candidate_id": "cand-mcp-tool-registry-api-capability-fallback",
        "run_id": "run-mcp-tool-registry-api-capability-fallback",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/loop_engineering_capability_pack.py",
            "backend/src/across_agents_assistant/api_server.py",
            "backend/src/across_agents_assistant/autopilot_mcp_tool_registry.py",
            "backend/tests/test_autopilot_mcp_tool_registry.py",
        ],
        "context_files": ["backend/src/across_agents_assistant/loop_engineering_capability_pack.py"],
        "validation_feedback": [
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": ["-c", "runpy.run_path('backend/tests/test_autopilot_mcp_tool_registry.py')"],
                "status": "failed",
                "stderr": (
                    "AssertionError: expected ACROSS MCP TOOL REGISTRY integration marker "
                    "for across_agents_assistant.autopilot_mcp_tool_registry"
                ),
                "diagnostic": {"failure_kind": "candidate_test_assertion"},
            }
        ],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "model": "MiniMax-M3",
            "direct_patches": True,
            "allow_host_validation_repair_fallback": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["host_validation_repair_fallback"] is True
    paths = {patch["path"] for patch in body["patches"]}
    assert paths == {
        "backend/src/across_agents_assistant/loop_engineering_capability_pack.py",
        "backend/src/across_agents_assistant/api_server.py",
        "backend/src/across_agents_assistant/autopilot_mcp_tool_registry.py",
        "backend/tests/test_autopilot_mcp_tool_registry.py",
    }
    api_patch = next(patch for patch in body["patches"] if patch["path"].endswith("api_server.py"))
    capability_patch = next(
        patch for patch in body["patches"] if patch["path"].endswith("loop_engineering_capability_pack.py")
    )
    test_patch = next(patch for patch in body["patches"] if patch["path"].startswith("backend/tests/"))
    module = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_mcp_tool_registry.py"))
    namespace = {}
    exec(compile(module["content"], module["path"], "exec"), namespace)
    assert "Union[ToolDescriptor, Mapping[str, Any]]" in module["content"]
    assert "|" not in module["content"].split("def _coerce_tool_descriptor", 1)[0]
    _assert_marker_upsert(api_patch, "# ACROSS MCP TOOL REGISTRY API START", "# ACROSS MCP TOOL REGISTRY API END")
    assert "def autopilot_mcp_tool_registry_snapshot()" in api_patch["content"]
    _assert_marker_upsert(
        capability_patch,
        "# ACROSS MCP TOOL REGISTRY CAPABILITY PACK START",
        "# ACROSS MCP TOOL REGISTRY CAPABILITY PACK END",
    )
    assert "def describe_mcp_tool_registry_capability()" in capability_patch["content"]
    assert "test_integration_marker_uses_delayed_imports" in test_patch["content"]
    assert "ACROSS MCP TOOL REGISTRY WORKBENCH START' in source" not in test_patch["content"]


def test_autopilot_code_iteration_validation_fallback_repairs_target_backlog(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    source = tmp_path / "source"
    api_path = source / "backend/src/across_agents_assistant/api_server.py"
    workbench_path = source / "backend/src/across_agents_assistant/autopilot_workbench.py"
    capability_path = source / "backend/src/across_agents_assistant/loop_engineering_capability_pack.py"
    api_path.parent.mkdir(parents=True, exist_ok=True)
    api_path.write_text(
        "from fastapi import FastAPI\n\n"
        "app = FastAPI()\n\n\n"
        "def start_api_server():\n"
        "    return None\n",
        encoding="utf-8",
    )
    workbench_path.write_text(
        "def build_autopilot_workbench_snapshot():\n"
        "    return {'status': 'source'}\n",
        encoding="utf-8",
    )
    capability_path.write_text(
        "def loop_engineering_capability_pack():\n"
        "    return {'status': 'source'}\n",
        encoding="utf-8",
    )

    class UnexpectedGateway:
        async def chat(self, **kwargs):
            raise AssertionError("target backlog validation fallback should not call the model")

    monkeypatch.setattr(api_server, "get_gateway", lambda: UnexpectedGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair target backlog integration",
        "candidate_workspace": str(candidate),
        "source_repository": str(source),
        "candidate_id": "cand-target-backlog-fallback",
        "run_id": "run-target-backlog-fallback",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_target_backlog.py",
            "backend/src/across_agents_assistant/autopilot_workbench.py",
            "backend/src/across_agents_assistant/loop_engineering_capability_pack.py",
            "backend/src/across_agents_assistant/api_server.py",
            "backend/tests/test_autopilot_target_backlog.py",
            "macOS-Client/Sources/AutopilotTargetBacklogView.swift",
        ],
        "context_files": [
            "backend/src/across_agents_assistant/autopilot_workbench.py",
            "backend/src/across_agents_assistant/loop_engineering_capability_pack.py",
            "backend/src/across_agents_assistant/api_server.py",
        ],
        "validation_feedback": [
            {
                "repo": "across-agents-assistant",
                "command": "candidate_quality",
                "args": [],
                "status": "failed",
                "stderr": (
                    "destructive_product_entrypoint_rewrite: backend/src/across_agents_assistant/api_server.py; "
                    "ImportError: cannot import name 'TargetBacklog' from "
                    "'across_agents_assistant.autopilot_target_backlog'; missing find_target and to_artifact_envelope"
                ),
                "diagnostic": {"failure_kind": "candidate_import_failure"},
            }
        ],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "model": "MiniMax-M3",
            "direct_patches": True,
            "allow_host_validation_repair_fallback": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["host_validation_repair_fallback"] is True
    paths = {patch["path"] for patch in body["patches"]}
    assert paths == {
        "backend/src/across_agents_assistant/autopilot_target_backlog.py",
        "backend/src/across_agents_assistant/autopilot_workbench.py",
        "backend/src/across_agents_assistant/loop_engineering_capability_pack.py",
        "backend/src/across_agents_assistant/api_server.py",
        "backend/tests/test_autopilot_target_backlog.py",
        "macOS-Client/Sources/AutopilotTargetBacklogView.swift",
    }
    module = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_target_backlog.py"))
    workbench = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_workbench.py"))
    capability = next(patch for patch in body["patches"] if patch["path"].endswith("loop_engineering_capability_pack.py"))
    api_patch = next(patch for patch in body["patches"] if patch["path"].endswith("api_server.py"))
    test_patch = next(patch for patch in body["patches"] if patch["path"].startswith("backend/tests/"))
    swift_patch = next(patch for patch in body["patches"] if patch["path"].endswith("AutopilotTargetBacklogView.swift"))
    namespace = {}
    exec(compile(module["content"], module["path"], "exec"), namespace)
    snapshot = namespace["target_backlog_snapshot"](
        selected_iteration={"target_id": "aaa-target-backlog-autopilot", "goal": "Expose backlog."}
    )
    assert snapshot["schema_version"] == "across-aaa-autopilot-target-backlog/1.0"
    assert namespace["find_target"](snapshot, "aaa-target-backlog-autopilot")["goal"] == "Expose backlog."
    assert namespace["to_artifact_envelope"](snapshot)["promotion_requires_human_review"] is True
    _assert_marker_upsert(workbench, "# ACROSS TARGET BACKLOG WORKBENCH START", "# ACROSS TARGET BACKLOG WORKBENCH END")
    _assert_marker_upsert(
        capability,
        "# ACROSS TARGET BACKLOG CAPABILITY PACK START",
        "# ACROSS TARGET BACKLOG CAPABILITY PACK END",
    )
    _assert_marker_upsert(api_patch, "# ACROSS TARGET BACKLOG API START", "# ACROSS TARGET BACKLOG API END")
    assert "test_integration_markers_use_delayed_imports" in test_patch["content"]
    assert "from across_agents_assistant.api_server import" not in test_patch["content"]
    assert "struct AutopilotTargetBacklogView" in swift_patch["content"]
    assert "AutopilotTargetBacklogItem" in swift_patch["content"]


def test_autopilot_code_iteration_validation_fallback_repairs_capability_classifier_api(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    source = tmp_path / "source"
    api_path = source / "backend/src/across_agents_assistant/api_server.py"
    api_path.parent.mkdir(parents=True, exist_ok=True)
    original_api = (
        "from fastapi import FastAPI\n\n"
        "app = FastAPI()\n\n\n"
        "@app.get('/api/health')\n"
        "async def health():\n"
        "    return {'status': 'ok'}\n"
    )
    api_path.write_text(original_api, encoding="utf-8")

    class UnexpectedGateway:
        async def chat(self, **kwargs):
            raise AssertionError("capability classifier validation fallback should not call the model")

    monkeypatch.setattr(api_server, "get_gateway", lambda: UnexpectedGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair capability classifier api integration",
        "candidate_workspace": str(candidate),
        "source_repository": str(source),
        "candidate_id": "cand-capability-classifier-fallback",
        "run_id": "run-capability-classifier-fallback",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/api_server.py",
            "backend/src/across_agents_assistant/autopilot_capability_classifier.py",
            "backend/tests/test_autopilot_capability_classifier.py",
        ],
        "context_files": ["backend/src/across_agents_assistant/api_server.py"],
        "validation_feedback": [
            {
                "repo": "across-agents-assistant",
                "command": "candidate_quality",
                "args": [],
                "status": "failed",
                "stderr": (
                    "destructive_product_entrypoint_rewrite: backend/src/across_agents_assistant/api_server.py "
                    "candidate rewrites a critical product entrypoint"
                ),
                "diagnostic": {"failure_kind": "candidate_quality_failure"},
            },
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": ["-c", "AAA backend API import contract smoke"],
                "status": "failed",
                "stderr": (
                    "ImportError: missing internal API import(s): "
                    "backend/src/across_agents_assistant/api_server.py: "
                    "across_agents_assistant.autopilot_capability_classifier.DEFAULT_RANKED, "
                    "across_agents_assistant.autopilot_capability_classifier.classify_goal, "
                    "across_agents_assistant.autopilot_capability_classifier.render_classification"
                ),
                "diagnostic": {"failure_kind": "candidate_import_failure"},
            },
        ],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "model": "MiniMax-M3",
            "direct_patches": True,
            "allow_host_validation_repair_fallback": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["host_validation_repair_fallback"] is True
    assert body["text_fallback"] is True
    paths = {patch["path"] for patch in body["patches"]}
    assert paths == {
        "backend/src/across_agents_assistant/api_server.py",
        "backend/src/across_agents_assistant/autopilot_capability_classifier.py",
        "backend/tests/test_autopilot_capability_classifier.py",
    }
    module = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_capability_classifier.py"))
    api_patch = next(patch for patch in body["patches"] if patch["path"].endswith("api_server.py"))
    test_patch = next(patch for patch in body["patches"] if patch["path"].startswith("backend/tests/"))
    namespace = {}
    exec(compile(module["content"], module["path"], "exec"), namespace)
    assert namespace["classify_goal"]("")["primary"] == namespace["DEFAULT_RANKED"][0]
    assert namespace["classify_capability"]("retrieve long-term memory") == "memory_retrieval"
    assert namespace["render_classification"]("route tool calls")["primary"] == "tool_routing"
    _assert_marker_upsert(api_patch, "# ACROSS CAPABILITY CLASSIFIER API START", "# ACROSS CAPABILITY CLASSIFIER API END")
    assert "def autopilot_classify_capability_detail" in api_patch["content"]
    assert "DEFAULT_RANKED" in module["content"]
    assert "test_api_server_marker_restores_full_entrypoint" in test_patch["content"]
    assert "from across_agents_assistant.api_server import" not in test_patch["content"]


def test_autopilot_code_iteration_validation_fallback_repairs_tool_registry_manifest(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    source = tmp_path / "source"
    api_path = source / "backend/src/across_agents_assistant/api_server.py"
    api_path.parent.mkdir(parents=True, exist_ok=True)
    api_path.write_text(
        "from fastapi import FastAPI\n\n"
        "app = FastAPI()\n\n\n"
        "@app.get('/api/health')\n"
        "async def health():\n"
        "    return {'status': 'ok'}\n",
        encoding="utf-8",
    )

    class UnexpectedGateway:
        async def chat(self, **kwargs):
            raise AssertionError("tool registry manifest validation fallback should not call the model")

    monkeypatch.setattr(api_server, "get_gateway", lambda: UnexpectedGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair AAA MCP tool registry manifest route",
        "candidate_workspace": str(candidate),
        "source_repository": str(source),
        "candidate_id": "cand-tool-registry-manifest-fallback",
        "run_id": "run-tool-registry-manifest-fallback",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/api_server.py",
            "backend/src/across_agents_assistant/tool_registry_manifest.py",
            "backend/tests/test_tool_registry_manifest.py",
        ],
        "context_files": ["backend/src/across_agents_assistant/api_server.py"],
        "validation_feedback": [
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": ["-c", "from across_agents_assistant.tool_registry_manifest import build_manifest"],
                "status": "failed",
                "stderr": (
                    "ImportError: cannot import name 'LIST_CAPABILITIES' "
                    "from 'across_agents_assistant.loop_engineering_capability_pack'"
                ),
                "diagnostic": {"failure_kind": "candidate_import_failure"},
            },
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": ["backend/tests/test_tool_registry_manifest.py"],
                "status": "failed",
                "stderr": "AssertionError: assert '/health' in endpoints",
                "diagnostic": {"failure_kind": "candidate_quality"},
            },
        ],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "model": "MiniMax-M3",
            "direct_patches": True,
            "allow_host_validation_repair_fallback": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["host_validation_repair_fallback"] is True
    assert body["text_fallback"] is True
    paths = {patch["path"] for patch in body["patches"]}
    assert paths == {
        "backend/src/across_agents_assistant/api_server.py",
        "backend/src/across_agents_assistant/tool_registry_manifest.py",
        "backend/tests/test_tool_registry_manifest.py",
    }
    module = next(patch for patch in body["patches"] if patch["path"].endswith("tool_registry_manifest.py"))
    api_patch = next(patch for patch in body["patches"] if patch["path"].endswith("api_server.py"))
    test_patch = next(patch for patch in body["patches"] if patch["path"].startswith("backend/tests/"))
    namespace = {}
    exec(compile(module["content"], module["path"], "exec"), namespace)

    class FakePack:
        def build_loop_engineering_capability_pack(self):
            return {"ready": [{"id": "repo-quality", "label": "Repo quality"}]}

    fake_app = SimpleNamespace(routes=[SimpleNamespace(path="/api/health", methods={"GET", "HEAD"})])
    manifest = namespace["build_manifest"](fake_app, FakePack())
    assert manifest["schema_version"] == "across-aaa-tool-registry-manifest/1.0"
    assert manifest["tools"] == [{"name": "api_health", "path": "/api/health", "methods": ["GET"]}]
    assert manifest["resources"][0]["uri"] == "across://capabilities/repo-quality"
    assert manifest["promotion_requires_human_review"] is True
    _assert_marker_upsert(api_patch, "# ACROSS TOOL REGISTRY MANIFEST ROUTE START", "# ACROSS TOOL REGISTRY MANIFEST ROUTE END")
    assert "get_autopilot_capabilities_manifest" in api_patch["content"]
    assert "test_register_capability_manifest_route_is_idempotent" in test_patch["content"]


def test_autopilot_code_iteration_repairs_validation_feedback_with_model(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class RepairGateway:
        async def chat(self, **kwargs):
            assert "validation_feedback" in kwargs["message"]
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Repair research-backed candidate scoring",
                    "risk": "low",
                    "patches": [
                        {
                            "path": "backend/src/across_agents_assistant/autopilot_research_signal.py",
                            "mode": "overwrite",
                            "content": (
                                "def score_research_iteration_candidate(research_brief):\n"
                                "    sources = list(research_brief.get('sources') or [])\n"
                                "    validation = list(research_brief.get('validation_commands') or [])\n"
                                "    if not sources:\n"
                                "        return {'recommendation': 'reject', 'evidence_count': 0}\n"
                                "    return {'recommendation': 'implement' if validation else 'review', 'evidence_count': len(sources)}\n"
                            ),
                        },
                        {
                            "path": "backend/tests/test_autopilot_research_signal.py",
                            "mode": "overwrite",
                            "content": (
                                "from across_agents_assistant.autopilot_research_signal import score_research_iteration_candidate\n\n\n"
                                "def test_scores_repaired_research_candidate():\n"
                                "    result = score_research_iteration_candidate({'sources': [{'id': 'source'}], 'validation_commands': ['pytest']})\n"
                                "    assert result['recommendation'] == 'implement'\n"
                            ),
                        },
                    ],
                    "validation_commands": [
                        {"command": "python3", "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_research_signal.py"]}
                    ],
                }),
                provider="minimax",
                model="MiniMax-M3",
                finish_reason="stop",
                usage={"total_tokens": 96},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: RepairGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair research-backed candidate scoring",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-repair",
        "run_id": "run-repair",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_research_signal.py",
            "backend/tests/test_autopilot_research_signal.py",
        ],
        "context_files": ["README.md"],
        "validation_feedback": [
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": ["backend/tests/test_autopilot_research_signal.py"],
                "status": "failed",
                "stderr": "AssertionError: 'reject' not found in {'implement', 'review'}",
            }
        ],
        "model_policy": {"required": True, "provider": "minimax", "model": "MiniMax-M3", "direct_patches": True},
    })

    assert response.status_code == 200
    body = response.json()
    assert body["host_validation_repair_fallback"] is False
    assert body["finish_reason"] == "stop"
    assert body["provider"] == "minimax"
    assert body["model"] == "MiniMax-M3"
    paths = {patch["path"] for patch in body["patches"]}
    assert paths == {
        "backend/src/across_agents_assistant/autopilot_research_signal.py",
        "backend/tests/test_autopilot_research_signal.py",
    }
    module = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_research_signal.py"))
    assert "score_research_iteration_candidate" in module["content"]
    assert "recommendation" in module["content"]


def test_autopilot_code_iteration_import_contract_feedback_bypasses_host_fallback(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class RepairGateway:
        def __init__(self):
            self.calls = 0

        async def chat(self, **kwargs):
            self.calls += 1
            assert "missing internal API import" in kwargs["message"]
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Repair API import contract by restoring exported runtime functions",
                    "risk": "low",
                    "patches": [
                        {
                            "path": "backend/src/across_agents_assistant/autopilot_tool_pack_runtime.py",
                            "mode": "overwrite",
                            "content": (
                                "def register_pack(name, descriptor=None):\n"
                                "    return {'name': name, 'descriptor': descriptor or {}}\n\n"
                                "def resolve_pack(name):\n"
                                "    return {'name': name}\n\n"
                                "def list_packs():\n"
                                "    return []\n\n"
                                "def describe_pack(name):\n"
                                "    return {'name': name}\n"
                            ),
                        },
                        {
                            "path": "backend/tests/test_autopilot_tool_pack_runtime.py",
                            "mode": "overwrite",
                            "content": (
                                "from across_agents_assistant.autopilot_tool_pack_runtime import register_pack, describe_pack\n\n\n"
                                "def test_runtime_exports_api_contract_symbols():\n"
                                "    assert register_pack('validation')['name'] == 'validation'\n"
                                "    assert describe_pack('validation')['name'] == 'validation'\n"
                            ),
                        },
                    ],
                }),
                provider="minimax",
                model="MiniMax-M3",
                finish_reason="stop",
                usage={"total_tokens": 120},
            )

    gateway = RepairGateway()
    monkeypatch.setattr(api_server, "get_gateway", lambda: gateway)
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair API import contract for tool pack runtime",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-import-contract",
        "run_id": "run-import-contract",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_tool_pack_runtime.py",
            "backend/tests/test_autopilot_tool_pack_runtime.py",
        ],
        "context_files": ["README.md"],
        "validation_feedback": [
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": ["-c", "api_server.py contract smoke"],
                "summary": "AAA backend API import contract smoke",
                "status": "failed",
                "stderr": (
                    "ImportError: missing internal API import(s): "
                    "across_agents_assistant.autopilot_tool_pack_runtime.describe_pack"
                ),
            }
        ],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "model": "MiniMax-M3",
            "direct_patches": True,
            "allow_host_validation_repair_fallback": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert gateway.calls == 1
    assert body["host_validation_repair_fallback"] is False
    assert body["text_fallback"] is False
    assert body["finish_reason"] == "stop"
    module = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_tool_pack_runtime.py"))
    assert "def describe_pack" in module["content"]
    assert "evaluate_candidate_signal" not in module["content"]


def test_autopilot_code_iteration_validation_fallback_repairs_tool_pack_registry(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    source = tmp_path / "source"
    workbench_path = source / "backend/src/across_agents_assistant/autopilot_workbench.py"
    pack_path = source / "backend/src/across_agents_assistant/loop_engineering_capability_pack.py"
    workbench_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    workbench_path.write_text(
        "def build_autopilot_workbench_snapshot(*, registry=None):\n"
        "    return {'status': 'source', 'registry': registry}\n",
        encoding="utf-8",
    )
    pack_path.write_text(
        "def build_loop_engineering_capability_pack():\n"
        "    return {'ready': []}\n",
        encoding="utf-8",
    )

    class UnexpectedGateway:
        async def chat(self, **kwargs):
            raise AssertionError("tool-pack registry validation fallback should not call the model")

    monkeypatch.setattr(api_server, "get_gateway", lambda: UnexpectedGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair Tool Pack registry integration",
        "candidate_workspace": str(candidate),
        "source_repository": str(source),
        "candidate_id": "cand-tool-pack-registry-fallback",
        "run_id": "run-tool-pack-registry-fallback",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_workbench.py",
            "backend/src/across_agents_assistant/autopilot_tool_pack_registry.py",
            "backend/src/across_agents_assistant/loop_engineering_capability_pack.py",
            "backend/tests/test_autopilot_tool_pack_registry.py",
        ],
        "context_files": [
            "backend/src/across_agents_assistant/autopilot_workbench.py",
            "backend/src/across_agents_assistant/loop_engineering_capability_pack.py",
        ],
        "validation_feedback": [
            {
                "repo": "across-agents-assistant",
                "command": "candidate_quality",
                "args": [],
                "status": "failed",
                "stderr": "excessive_blank_lines: backend/src/across_agents_assistant/autopilot_tool_pack_registry.py",
                "diagnostic": {"failure_kind": "candidate_quality_failure"},
                "quality_findings": [
                    {"id": "excessive_blank_lines", "severity": "error", "path": "backend/src/across_agents_assistant/autopilot_tool_pack_registry.py"}
                ],
            },
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": ["-c", "runpy.run_path('backend/src/across_agents_assistant/autopilot_tool_pack_registry.py')"],
                "status": "failed",
                "stderr": "TypeError: unsupported operand type(s) for |: '_GenericAlias' and 'NoneType'",
                "diagnostic": {"failure_kind": "python_version_incompatible"},
            },
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": ["-c", "AAA backend API import contract smoke"],
                "status": "failed",
                "stderr": (
                    "ImportError: missing internal API import(s): "
                    "backend/src/across_agents_assistant/autopilot_workbench.py: "
                    "across_agents_assistant.autopilot_tool_pack_registry.ALL_PACKS, "
                    "backend/src/across_agents_assistant/autopilot_workbench.py: "
                    "across_agents_assistant.autopilot_tool_pack_registry.evaluate, "
                    "backend/src/across_agents_assistant/autopilot_workbench.py: "
                    "across_agents_assistant.loop_engineering_capability_pack.advise_with_capability"
                ),
                "diagnostic": {"failure_kind": "candidate_import_failure"},
            },
        ],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "model": "MiniMax-M3",
            "direct_patches": True,
            "allow_host_validation_repair_fallback": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["host_validation_repair_fallback"] is True
    assert body["text_fallback"] is True
    assert {patch["path"] for patch in body["patches"]} == {
        "backend/src/across_agents_assistant/autopilot_workbench.py",
        "backend/src/across_agents_assistant/autopilot_tool_pack_registry.py",
        "backend/src/across_agents_assistant/loop_engineering_capability_pack.py",
        "backend/tests/test_autopilot_tool_pack_registry.py",
    }
    module = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_tool_pack_registry.py"))
    workbench = next(patch for patch in body["patches"] if patch["path"].endswith("autopilot_workbench.py"))
    pack = next(patch for patch in body["patches"] if patch["path"].endswith("loop_engineering_capability_pack.py"))
    test_patch = next(patch for patch in body["patches"] if patch["path"].startswith("backend/tests/"))
    namespace = {}
    exec(compile(module["content"], module["path"], "exec"), namespace)
    assert [item.id for item in namespace["ALL_PACKS"]] == ["intake", "research", "build", "validate", "review"]
    assert namespace["evaluate"]({"tool_packs": ["intake"]})["status"] == "attention"
    assert namespace["advise_tool_packs"]("validate loop", {"tool_packs": ["intake", "research", "build", "validate", "review"]})["status"] == "passed"
    _assert_marker_upsert(workbench, "# ACROSS TOOL PACK REGISTRY WORKBENCH START", "# ACROSS TOOL PACK REGISTRY WORKBENCH END")
    assert "def tool_pack_registry_snapshot()" in workbench["content"]
    _assert_marker_upsert(
        pack,
        "# ACROSS TOOL PACK REGISTRY CAPABILITY PACK START",
        "# ACROSS TOOL PACK REGISTRY CAPABILITY PACK END",
    )
    assert "def advise_with_capability" in pack["content"]
    assert "test_workbench_and_capability_pack_markers_use_delayed_imports" in test_patch["content"]
    assert "Mapping[str, Any] | None" not in module["content"]


def test_autopilot_code_iteration_integration_feedback_bypasses_host_fallback(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class RepairGateway:
        def __init__(self):
            self.calls = 0

        async def chat(self, **kwargs):
            self.calls += 1
            assert "loop_engineering_capability_pack" in kwargs["message"]
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Wire capability descriptor into the product pack entrypoint",
                    "risk": "low",
                    "patches": [
                        {
                            "path": "backend/src/across_agents_assistant/loop_engineering_capability_pack.py",
                            "mode": "overwrite",
                            "content": (
                                "def register_capability(descriptor):\n"
                                "    return {'registered': descriptor}\n\n"
                                "def list_capabilities():\n"
                                "    return []\n"
                            ),
                        },
                        {
                            "path": "backend/tests/test_autopilot_capability_descriptor.py",
                            "mode": "overwrite",
                            "content": (
                                "import across_agents_assistant.loop_engineering_capability_pack as lep\n\n\n"
                                "def test_loop_engineering_pack_export():\n"
                                "    assert hasattr(lep, 'register_capability')\n"
                                "    assert hasattr(lep, 'list_capabilities')\n"
                            ),
                        },
                    ],
                }),
                provider="minimax",
                model="MiniMax-M3",
                finish_reason="stop",
                usage={"total_tokens": 80},
            )

    gateway = RepairGateway()
    monkeypatch.setattr(api_server, "get_gateway", lambda: gateway)
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Repair capability descriptor integration",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-integration-contract",
        "run_id": "run-integration-contract",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/loop_engineering_capability_pack.py",
            "backend/tests/test_autopilot_capability_descriptor.py",
        ],
        "context_files": ["README.md"],
        "validation_feedback": [
            {
                "repo": "across-agents-assistant",
                "command": "python3",
                "args": [
                    "-c",
                    "import across_agents_assistant.loop_engineering_capability_pack as p; "
                    "assert hasattr(p,'register_capability') and hasattr(p,'list_capabilities')",
                ],
                "status": "failed",
                "stderr": "AssertionError: loop_engineering_capability_pack missing register_capability/list_capabilities",
            }
        ],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "model": "MiniMax-M3",
            "direct_patches": True,
            "allow_host_validation_repair_fallback": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert gateway.calls == 1
    assert body["host_validation_repair_fallback"] is False
    assert body["finish_reason"] == "stop"
    assert {patch["path"] for patch in body["patches"]} == {
        "backend/src/across_agents_assistant/loop_engineering_capability_pack.py",
        "backend/tests/test_autopilot_capability_descriptor.py",
    }


def test_autopilot_code_iteration_direct_mode_repairs_to_content_lines(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class RepairGateway:
        def __init__(self):
            self.calls = 0

        async def chat(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(
                    text="<think>Need a research signal helper.</think>",
                    provider="minimax",
                    model="MiniMax-M3",
                    finish_reason="length",
                    usage={"total_tokens": 20},
                )
            assert "content_lines" in kwargs["message"]
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Add research-backed candidate scoring",
                    "risk": "low",
                    "patches": [
                        {
                            "path": "backend/src/across_agents_assistant/autopilot_research_signal.py",
                            "mode": "overwrite",
                            "content_lines": [
                                "def score_research_iteration_candidate(research_brief):",
                                "    sources = list(research_brief.get('sources') or [])",
                                "    return {'recommendation': 'implement' if sources else 'reject', 'evidence_count': len(sources)}",
                            ],
                        },
                        {
                            "path": "backend/tests/test_autopilot_research_signal.py",
                            "mode": "overwrite",
                            "content_lines": [
                                "from across_agents_assistant.autopilot_research_signal import score_research_iteration_candidate",
                                "",
                                "",
                                "def test_scores_research_candidate():",
                                "    assert score_research_iteration_candidate({'sources': [{'id': 'openhands'}]})['recommendation'] == 'implement'",
                            ],
                        },
                    ],
                    "validation_commands": [
                        {
                            "command": "python3",
                            "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_research_signal.py"],
                        }
                    ],
                }),
                provider="minimax",
                model="MiniMax-M3",
                finish_reason="stop",
                usage={"total_tokens": 55},
            )

    gateway = RepairGateway()
    monkeypatch.setattr(api_server, "get_gateway", lambda: gateway)
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Add research-backed candidate scoring",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-repair",
        "run_id": "run-repair",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_research_signal.py",
            "backend/tests/test_autopilot_research_signal.py",
        ],
        "context_files": ["README.md"],
        "validation_commands": [
            {"repo": "across-agents-assistant", "command": "python3", "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_research_signal.py"]},
            {"repo": "across-agents-assistant", "command": "python3", "args": ["-c", "print('strategy validation')"]},
        ],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "direct_patches": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert gateway.calls == 2
    assert body["repaired_json"] is True
    assert body["text_fallback"] is False
    assert body["patches"][0]["content"].endswith("\n")
    assert "score_research_iteration_candidate" in body["patches"][0]["content"]
    assert len(body["validation_commands"]) == 2
    assert body["validation_commands"][1]["args"] == ["-c", "print('strategy validation')"]


def test_autopilot_code_iteration_direct_mode_uses_multiple_json_repairs(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class MultiRepairGateway:
        def __init__(self):
            self.calls = 0

        async def chat(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(
                    text="<think>Need a patch, but no JSON yet.</think>",
                    provider="minimax",
                    model="MiniMax-M3",
                    finish_reason="length",
                    usage={"total_tokens": 20},
                )
            if self.calls == 2:
                assert "raw_model_output" in kwargs["message"]
                return SimpleNamespace(
                    text=json.dumps({"summary": "Still missing patches", "risk": "low", "patches": []}),
                    provider="minimax",
                    model="MiniMax-M3",
                    finish_reason="stop",
                    usage={"total_tokens": 30},
                )
            assert "Model decision did not include any valid patches" in kwargs["message"]
            return SimpleNamespace(
                text=json.dumps({
                    "summary": "Add source signal digest helper",
                    "risk": "low",
                    "patches": [
                        {
                            "path": "backend/src/across_agents_assistant/autopilot_source_signal_digest.py",
                            "mode": "overwrite",
                            "content_lines": [
                                "def digest_source_signals(payload):",
                                "    signals = list((payload or {}).get('signals') or [])",
                                "    return {'signal_count': len(signals)}",
                            ],
                        },
                        {
                            "path": "backend/tests/test_autopilot_source_signal_digest.py",
                            "mode": "overwrite",
                            "content_lines": [
                                "from across_agents_assistant.autopilot_source_signal_digest import digest_source_signals",
                                "",
                                "",
                                "def test_digest_counts_signals():",
                                "    assert digest_source_signals({'signals': [{}, {}]})['signal_count'] == 2",
                            ],
                        },
                    ],
                    "validation_commands": [
                        {
                            "command": "python3",
                            "args": ["-m", "py_compile", "backend/src/across_agents_assistant/autopilot_source_signal_digest.py"],
                        }
                    ],
                }),
                provider="minimax",
                model="MiniMax-M3",
                finish_reason="stop",
                usage={"total_tokens": 80},
            )

    gateway = MultiRepairGateway()
    monkeypatch.setattr(api_server, "get_gateway", lambda: gateway)
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Add a source signal digest helper",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-multi-repair",
        "run_id": "run-multi-repair",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_source_signal_digest.py",
            "backend/tests/test_autopilot_source_signal_digest.py",
        ],
        "context_files": ["README.md"],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "model": "MiniMax-M3",
            "direct_patches": True,
            "direct_patch_repair_attempts": 2,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert gateway.calls == 3
    assert body["repaired_json"] is True
    assert body["text_fallback"] is False
    assert {patch["path"] for patch in body["patches"]} == {
        "backend/src/across_agents_assistant/autopilot_source_signal_digest.py",
        "backend/tests/test_autopilot_source_signal_digest.py",
    }


def test_autopilot_code_iteration_direct_mode_falls_back_to_quality_helper(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class ThinkingGateway:
        async def chat(self, **kwargs):
            assert kwargs["extra_body"] == {"reasoning_split": True, "thinking": {"type": "disabled"}}
            return SimpleNamespace(
                text="<think>Design a product quality helper, but do not emit JSON.</think>",
                provider="minimax",
                model="MiniMax-M3",
                finish_reason="length",
                usage={"total_tokens": 128},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: ThinkingGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Add a semantic candidate product quality helper",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-3",
        "run_id": "run-3",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_candidate_quality.py",
            "backend/tests/test_autopilot_candidate_quality.py",
        ],
        "context_files": ["README.md"],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "direct_patches": True,
            "allow_host_code_fallback": True,
            "conformance_fixture": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["model_backed"] is True
    assert body["provider"] == "minimax"
    assert body["repaired_json"] is False
    assert body["text_fallback"] is True
    paths = [patch["path"] for patch in body["patches"]]
    assert paths == [
        "backend/src/across_agents_assistant/autopilot_candidate_quality.py",
        "backend/tests/test_autopilot_candidate_quality.py",
    ]
    module = body["patches"][0]["content"]
    assert "def evaluate_candidate_product_alignment" in module
    assert "candidate only proves loop execution" in module
    test_file = body["patches"][1]["content"]
    assert "test_alignment_rejects_self_proof_only_candidate" in test_file


def test_autopilot_code_iteration_direct_mode_falls_back_to_research_signal(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "README.md").write_text("# Candidate\n", encoding="utf-8")

    class ThinkingGateway:
        async def chat(self, **kwargs):
            assert kwargs["extra_body"] == {"reasoning_split": True, "thinking": {"type": "disabled"}}
            return SimpleNamespace(
                text="<think>Design a research signal helper, but do not emit JSON.</think>",
                provider="minimax",
                model="MiniMax-M3",
                finish_reason="length",
                usage={"total_tokens": 144},
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: ThinkingGateway())
    response = TestClient(app).post("/api/autopilot/code-iteration", json={
        "goal": "Add research-backed candidate scoring",
        "candidate_workspace": str(candidate),
        "candidate_id": "cand-4",
        "run_id": "run-4",
        "allowed_patch_paths": [
            "backend/src/across_agents_assistant/autopilot_research_signal.py",
            "backend/tests/test_autopilot_research_signal.py",
        ],
        "context_files": ["README.md"],
        "model_policy": {
            "required": True,
            "provider": "minimax",
            "direct_patches": True,
            "allow_host_code_fallback": True,
            "conformance_fixture": True,
        },
    })

    assert response.status_code == 200
    body = response.json()
    assert body["model_backed"] is True
    assert body["repaired_json"] is False
    assert body["text_fallback"] is True
    paths = [patch["path"] for patch in body["patches"]]
    assert paths == [
        "backend/src/across_agents_assistant/autopilot_research_signal.py",
        "backend/tests/test_autopilot_research_signal.py",
    ]
    assert "def score_research_iteration_candidate" in body["patches"][0]["content"]
    assert "test_scores_research_backed_candidate_as_implementable" in body["patches"][1]["content"]


def test_autopilot_model_decision_endpoint_rejects_unallowed_patch_path(monkeypatch, tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    class FakeGateway:
        async def chat(self, **kwargs):
            return SimpleNamespace(
                text='{"patches":[{"path":"../source/README.md","mode":"overwrite","content":"bad"}]}',
                provider="fake-provider",
                model="fake-model",
                finish_reason="stop",
                usage=None,
            )

    monkeypatch.setattr(api_server, "get_gateway", lambda: FakeGateway())
    response = TestClient(app).post("/api/autopilot/model-decision", json={
        "goal": "Plan an unsafe patch",
        "candidate_workspace": str(candidate),
        "allowed_patch_paths": ["docs/ITERATION.md"],
        "model_policy": {"required": True},
    })

    assert response.status_code == 422
    assert "Unsafe relative path" in response.json()["detail"]
