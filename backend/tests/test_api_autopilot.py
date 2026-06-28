from fastapi.testclient import TestClient
from types import SimpleNamespace
from pathlib import Path
import json

import across_agents_assistant.api_server as api_server
from across_agents_assistant.autopilot_client import AutopilotClient, _long_run_timeout_seconds
from across_agents_assistant.api_server import app
from across_agents_assistant.plugin_runtime import PluginLifecycleError


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


def test_autopilot_control_plane_endpoints(monkeypatch, tmp_path):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "aaa-home"))
    monkeypatch.setattr(api_server, "get_autopilot_client", lambda: FakeAutopilotClient())
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
    scheduler_started = client.post("/api/autopilot/trigger-scheduler/start", json={"interval_seconds": 5})
    assert scheduler_started.status_code == 200
    assert scheduler_started.json()["running"] is True
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
    assert self_plan.json()["ready"] is True

    run = client.post(
        "/api/autopilot/runs",
        json={
            "spec": "daily-news-brief",
            "trigger": "user-e2e",
            "model_policy_overrides": {
                "builder": {"agent_id": "minimax", "provider": "minimax", "model": "MiniMax-M3"},
                "reviewer": {"agent_id": "minimax", "provider": "minimax", "model": "MiniMax-M2.5"},
            },
        },
    )
    assert run.status_code == 200
    body = run.json()
    assert body["run"]["run_id"] == "run-api-1"
    assert body["evidence"]["orchestrator"]["tasks"][0]["metadata_reflected"] is True
    assert body["evidence"]["model_policy_overrides"]["builder"]["model"] == "MiniMax-M3"
    assert body["evidence"]["model_policy_overrides"]["reviewer"]["model"] == "MiniMax-M2.5"
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


def test_autopilot_client_passes_model_overrides(monkeypatch):
    observed = {}

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
            "builder": {"agent_id": "minimax", "provider": "minimax", "model": "MiniMax-M3"},
            "reviewer": {"agent_id": "minimax", "provider": "minimax", "model": "MiniMax-M2.5"},
        },
    )

    assert "--model-overrides-json" in observed["args"]
    payload = json.loads(observed["args"][observed["args"].index("--model-overrides-json") + 1])
    assert payload["builder"]["model"] == "MiniMax-M3"
    assert payload["reviewer"]["model"] == "MiniMax-M2.5"
    assert observed["timeout"] == 1800


def test_autopilot_client_long_run_timeout_is_configurable(monkeypatch):
    monkeypatch.setenv("ACROSS_AAA_AUTOPILOT_RUN_TIMEOUT_SECONDS", "2400")
    assert _long_run_timeout_seconds() == 2400

    monkeypatch.setenv("ACROSS_AAA_AUTOPILOT_RUN_TIMEOUT_SECONDS", "not-a-number")
    assert _long_run_timeout_seconds() == 1800

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
    assert body["ready_count"] >= 41
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
    assert "model_generated_fallback_plan" in ids
    assert "multi_candidate_comparison" in ids
    assert "distinct_model_acceptance" in ids
    assert "promotion_attestation" in ids
    assert "promotion_human_review" in ids
    assert "ops_dashboard" in ids
    assert "loop_capability_audit_skill" in ids
    assert "e2e_failure_triage_skill" in ids
    assert "unified_capability_registry" in ids
    assert body["skill_candidate_count"] == 0
    assert "fallback" in body["policy"]
    assert body["policy"]["promotion"].startswith("commit")


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
