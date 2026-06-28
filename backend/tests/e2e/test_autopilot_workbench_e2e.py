from fastapi.testclient import TestClient

import across_agents_assistant.api_server as api_server
from across_agents_assistant.api_server import app


class WorkbenchFakeAutopilotClient:
    def __init__(self):
        self.queue = []
        self.runs = []
        self.evidence_by_run = {}
        self.trigger_index = 0

    def registry(self):
        return {
            "schema_version": "across-autopilot-loop-registry/1.0",
            "built_in": [{"id": "aaa-autonomous-self-iteration"}],
        }

    def enqueue_trigger(
        self,
        spec,
        trigger_type="manual",
        payload=None,
        idempotency_key=None,
        not_before=None,
        source="aaa",
        actor="user",
    ):
        self.trigger_index += 1
        trigger = {
            "trigger_id": f"trg-e2e-{self.trigger_index}",
            "spec": spec,
            "type": trigger_type,
            "status": "queued",
            "payload": payload or {},
            "idempotency_key": idempotency_key,
            "not_before": not_before,
            "source": source,
            "actor": actor,
        }
        self.queue.append(trigger)
        return trigger

    def trigger_queue(self):
        return {"schema_version": "across-autopilot-trigger-queue/1.0", "items": list(self.queue)}

    def run_trigger(self, trigger_id=None):
        selected = self.queue[0] if self.queue else {"trigger_id": trigger_id or "trg-e2e-empty"}
        self.queue = [item for item in self.queue if item.get("trigger_id") != selected.get("trigger_id")]
        return {"status": "completed", "trigger": selected}

    def run(self, spec, trigger="aaa-user", model_policy_overrides=None):
        run_id = f"run-e2e-{len(self.runs) + 1}"
        record = {
            "run_id": run_id,
            "spec_id": spec,
            "status": "completed",
            "quality_status": "passed",
            "promotion_ready": True,
            "trigger": trigger,
        }
        evidence = _promotion_ready_evidence(run_id, spec)
        self.runs.insert(0, record)
        self.evidence_by_run[run_id] = evidence
        return {"run": record, "evidence": evidence}

    def list_runs(self):
        return {"runs": list(self.runs), "run_count": len(self.runs)}

    def status(self, run_id):
        for record in self.runs:
            if record["run_id"] == run_id:
                return record
        return {"run_id": run_id, "status": "missing", "quality_status": "failed"}

    def evidence(self, run_id):
        return self.evidence_by_run[run_id]

    def telemetry(self):
        completed = sum(1 for item in self.runs if item["status"] == "completed")
        failed = sum(1 for item in self.runs if item["status"] == "failed")
        return {
            "schema_version": "across-autopilot-telemetry/1.0",
            "runs": {"total": len(self.runs), "completed": completed, "failed": failed},
            "promotion_ready_by_spec": {
                item["spec_id"]: 1 for item in self.runs if item.get("promotion_ready")
            },
        }


def test_autopilot_workbench_api_e2e(monkeypatch, tmp_path):
    fake = WorkbenchFakeAutopilotClient()
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "aaa-home"))
    monkeypatch.setattr(api_server, "_autopilot_trigger_scheduler", None)
    monkeypatch.setattr(api_server, "get_autopilot_client", lambda: fake)
    monkeypatch.setattr(
        api_server,
        "discover_across_plugins",
        lambda probe=False, plugin_ids=None, env=None: [
            {"plugin_id": "across-context", "display_name": "Across Context", "kind": "memory-provider", "available": True, "installed": True, "status": "installed"},
            {"plugin_id": "across-orchestrator", "display_name": "Across Orchestrator", "kind": "task-runtime", "available": True, "installed": True, "status": "installed"},
            {"plugin_id": "across-autopilot", "display_name": "Across Autopilot", "kind": "autonomous-workflow", "available": True, "installed": True, "status": "installed"},
        ],
    )
    monkeypatch.setattr(
        api_server,
        "_build_unified_capability_registry_payload",
        lambda refresh=False: {
            "providers": [{"id": "across-agents-assistant"}, {"id": "across-autopilot"}],
            "capabilities": [
                {
                    "id": f"autopilot.tool_pack.pack_{i}",
                    "kind": "tool_pack",
                    "provider": "across-autopilot",
                    "executor": "across-autopilot",
                    "available": True,
                    "status": "ready",
                }
                for i in range(42)
            ],
        },
    )
    monkeypatch.setattr(
        api_server,
        "evaluate_unified_capability_registry_health",
        lambda payload: {"status": "passed", "checks": [{"id": "registry", "status": "passed"}]},
    )
    monkeypatch.setattr(
        api_server,
        "get_agent_loop_memory_metrics",
        lambda all_projects=True, project_root=None: {"totals": {"candidate_count": 0, "pending_count": 0, "approved_count": 0}},
    )
    monkeypatch.setattr(api_server, "list_context_memories", lambda status=None, **_: [])
    monkeypatch.setattr(
        api_server,
        "_build_agent_cards_payload",
        lambda: {
            "schema_version": "1.0",
            "protocol": "a2a-like",
            "cards": [{"agent_id": "owner", "name": "Owner", "capabilities": [{"id": "review"}]}],
        },
    )
    monkeypatch.setattr(api_server.mcp_manager, "get_safety_report", lambda: {"servers": []})
    monkeypatch.setattr(
        api_server,
        "probe_agent_plugin_runtime_status",
        lambda: {
            "status": "passed",
            "summary": {
                "downstream_count": 3,
                "downstream_ready_count": 3,
                "agent_plugin_count": 1,
                "ready_agent_plugin_count": 1,
                "external_agent_count": 1,
                "healthy_external_agent_count": 1,
                "context_pack_count": 1,
            },
            "sections": {
                "orchestrator_external_agents": {"id": "orchestrator_external_agents", "title": "Orchestrator External Agent Registry", "status": "passed", "summary": {"agent_count": 1}},
                "autopilot_agent_plugin_runtime": {"id": "autopilot_agent_plugin_runtime", "title": "Autopilot Generic Agent Plugin Runtime", "status": "passed", "summary": {"agent_plugin_count": 1, "ready_agent_plugin_count": 1}},
                "context_agent_packs": {"id": "context_agent_packs", "title": "Context Agent Plugin Packs", "status": "passed", "summary": {"context_pack_count": 1}},
            },
        },
    )
    monkeypatch.setattr(
        api_server,
        "load_agent_interop_e2e_latest",
        lambda: {
            "schema_version": "across-aaa-agent-interop-e2e/1.0",
            "status": "passed",
            "summary": {
                "passed_count": 11,
                "failed_count": 0,
                "host_target_count": 5,
                "mcp_server_count": 3,
                "evidence_node_count": 21,
            },
            "checks": [{"id": "three_plugin_mcp_load", "status": "passed", "summary": "tool_count=42"}],
        },
    )

    async def fake_release_evaluation_payload(limit=100):
        return {"release_readiness": "ready", "evaluated_task_count": 3}

    monkeypatch.setattr(api_server, "_release_evaluation_payload", fake_release_evaluation_payload)

    client = TestClient(app)

    roadmap = client.get("/api/ecosystem/roadmap")
    assert roadmap.status_code == 200
    assert roadmap.json()["schema_version"] == "across-aaa-ecosystem-roadmap/1.0"
    assert roadmap.json()["summary"]["route_count"] == 7
    for path in [
        "/api/ecosystem/protocol-gateway",
        "/api/ecosystem/tool-packs",
        "/api/ecosystem/trust-sandbox",
        "/api/ecosystem/evaluation-telemetry",
        "/api/ecosystem/context-packs",
        "/api/ecosystem/external-agents",
        "/api/ecosystem/agent-plugins",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()["id"]

    initial = client.get("/api/autopilot/workbench")
    assert initial.status_code == 200
    assert initial.json()["schema_version"] == "across-aaa-autopilot-workbench/1.0"
    assert initial.json()["summary"]["autopilot_available"] is True

    ensured = client.post(
        "/api/autopilot/self-iteration-plan/ensure",
        json={"spec": "aaa-autonomous-self-iteration", "interval_seconds": 60, "actor": "e2e"},
    )
    assert ensured.status_code == 200
    assert ensured.json()["status"] == "active"

    tick = client.post("/api/autopilot/trigger-configs/tick")
    assert tick.status_code == 200
    assert tick.json()["status"] == "enqueued"
    queued_id = tick.json()["enqueued"][0]["trigger_id"]

    trigger_run = client.post("/api/autopilot/triggers/run", json={"trigger_id": queued_id})
    assert trigger_run.status_code == 200
    assert trigger_run.json()["status"] == "completed"

    run = client.post("/api/autopilot/runs", json={"spec": "aaa-autonomous-self-iteration", "trigger": "e2e"})
    assert run.status_code == 200
    run_id = run.json()["run"]["run_id"]

    promotion = client.get(f"/api/autopilot/runs/{run_id}/promotion-review")
    assert promotion.status_code == 200
    assert promotion.json()["status"] == "ready_for_human_review"
    assert promotion.json()["allowed_actions"]["merge"] is False

    refreshed = client.post("/api/autopilot/workbench/refresh")
    assert refreshed.status_code == 200
    payload = refreshed.json()
    assert payload["summary"]["run_count"] == 1
    assert payload["summary"]["promotion_ready_count"] == 1
    assert payload["summary"]["self_iteration_status"] == "active"
    assert payload["summary"]["ecosystem_route_count"] == 7
    assert payload["summary"]["agent_plugin_count"] == 1
    assert payload["summary"]["agent_interop_e2e_status"] == "passed"
    for section_id in [
        "protocol_gateway",
        "tool_pack_registry",
        "trust_sandbox",
        "evaluation_telemetry",
        "context_packs",
        "external_agents",
        "agent_plugin_runtime",
        "agent_interop_e2e",
    ]:
        assert section_id in payload["sections"]
    assert payload["sections"]["agent_plugins"]["status"] == "passed"
    assert payload["sections"]["promotion"]["status"] == "attention"
    assert any(action["id"] == "open_promotion_review" for action in payload["actions"])


def _promotion_ready_evidence(run_id: str, spec: str):
    return {
        "run_id": run_id,
        "spec_id": spec,
        "candidate": {
            "candidate_id": "candidate-e2e",
            "promotion_ready": True,
            "changed_files": ["backend/src/across_agents_assistant/autopilot_workbench.py"],
            "semantic_alignment_status": "passed",
            "quality_findings": [],
            "validation": {"status": "passed"},
            "self_hosting_probe": {"required": False, "status": "skipped"},
            "independent_reviewer": {
                "model_separation": {"required": True, "status": "passed"},
                "product_value_score": 0.9,
                "maintainability_score": 0.9,
                "risk_score": 0.2,
                "merge_recommendation": "review_pr",
            },
            "promotion_package": {
                "candidate_id": "candidate-e2e",
                "source_a_unchanged": True,
                "known_risks": [],
                "changed_files": ["backend/src/across_agents_assistant/autopilot_workbench.py"],
                "reviewer_scores": {
                    "product_value_score": 0.9,
                    "maintainability_score": 0.9,
                    "risk_score": 0.2,
                    "merge_recommendation": "review_pr",
                },
                "recommended_pr": {"title": "Autopilot Workbench E2E"},
                "source_ref_pins": {
                    "status": "passed",
                    "repos": [
                        {"id": "across-agents-assistant", "source_head_pre": "aaa", "source_unchanged": True},
                        {"id": "across-orchestrator", "source_head_pre": "orch", "source_unchanged": True},
                        {"id": "across-autopilot", "source_head_pre": "auto", "source_unchanged": True},
                        {"id": "across-context", "source_head_pre": "ctx", "source_unchanged": True},
                    ],
                    "missing_required_repos": [],
                    "missing_pins": [],
                    "changed_sources": [],
                },
            },
        },
        "gates": [{"id": "validation", "status": "passed", "required": True}],
    }
