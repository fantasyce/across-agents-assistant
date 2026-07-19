from across_agents_assistant.aaa_ecosystem_roadmap import (
    ECOSYSTEM_ROADMAP_SCHEMA_VERSION,
    build_aaa_ecosystem_roadmap,
    ecosystem_route_section,
)


def _capabilities():
    return [
        {
            "id": f"autopilot.tool_pack.pack_{index}",
            "kind": "tool_pack",
            "provider": "across-autopilot",
            "executor": "across-autopilot",
            "available": True,
            "status": "ready",
        }
        for index in range(12)
    ]


def test_ecosystem_roadmap_covers_all_route_directions():
    roadmap = build_aaa_ecosystem_roadmap(
        plugins=[
            {"plugin_id": "across-context", "available": True, "status": "installed"},
            {"plugin_id": "across-orchestrator", "available": True, "status": "installed"},
            {"plugin_id": "across-autopilot", "available": True, "status": "installed"},
        ],
        capability_registry={
            "providers": [{"id": "across-agents-assistant"}, {"id": "across-autopilot"}],
            "capabilities": _capabilities(),
        },
        registry_health={"status": "passed", "checks": [{"id": "non_secret", "status": "passed"}]},
        agent_cards={"cards": [{"agent_id": "owner", "name": "Owner", "capabilities": [{"id": "review"}]}]},
        mcp_safety={"servers": []},
        autopilot_registry={"built_in": [{"id": "aaa-autonomous-self-iteration"}]},
        autopilot_runs={"runs": [{"run_id": "run-1", "status": "completed"}], "run_count": 1},
        autopilot_telemetry={"runs": {"total": 1, "completed": 1, "failed": 0}},
        ops_dashboard={"status": "passed", "summary": {"capability_ready_count": 42}},
        release_evaluation={"release_readiness": "ready", "evaluated_task_count": 3},
        memory_metrics={"totals": {"candidate_count": 0, "pending_count": 0, "approved_count": 0}},
        pending_memories=[],
        agent_plugin_runtime=_agent_plugin_runtime(),
        generated_at="2026-06-23T00:00:00Z",
    )

    assert roadmap["schema_version"] == ECOSYSTEM_ROADMAP_SCHEMA_VERSION
    assert set(roadmap["sections"]) == {
        "protocol_gateway",
        "tool_pack_registry",
        "trust_sandbox",
        "evaluation_telemetry",
        "context_packs",
        "external_agents",
        "agent_plugin_runtime",
    }
    assert roadmap["summary"]["route_count"] == 7
    assert roadmap["summary"]["ready_route_count"] == 7
    assert roadmap["status"] == "passed"
    assert roadmap["sections"]["tool_pack_registry"]["summary"]["ready_tool_pack_count"] == 12
    assert ecosystem_route_section(roadmap, "protocol_gateway")["title"] == "Protocol Gateway"


def test_ecosystem_roadmap_marks_pending_memory_and_eval_gaps_attention():
    roadmap = build_aaa_ecosystem_roadmap(
        plugins=[{"plugin_id": "across-autopilot", "available": True, "status": "installed"}],
        capability_registry={"providers": [], "capabilities": _capabilities()[:2]},
        registry_health={"status": "failed"},
        agent_cards={"cards": []},
        mcp_safety={},
        autopilot_registry={},
        autopilot_runs={"runs": []},
        autopilot_telemetry={"runs": {"total": 0, "completed": 0, "failed": 0}},
        ops_dashboard={"status": "attention"},
        release_evaluation={"release_readiness": "no_evidence", "evaluated_task_count": 0},
        memory_metrics={"totals": {"candidate_count": 1, "pending_count": 1, "approved_count": 0}},
        pending_memories=[{"id": "mem-1", "scope": "global", "type": "note", "status": "pending"}],
        agent_plugin_runtime={},
    )

    assert roadmap["status"] == "failed"
    assert roadmap["sections"]["context_packs"]["status"] == "attention"
    assert roadmap["sections"]["context_packs"]["items"][0]["id"] == "global:note:pending"
    assert roadmap["sections"]["tool_pack_registry"]["status"] == "attention"
    assert any(action["id"] == "advance_context_packs" for action in roadmap["actions"])


def test_ecosystem_roadmap_accepts_agent_interop_e2e_as_release_evidence():
    roadmap = build_aaa_ecosystem_roadmap(
        plugins=[
            {"plugin_id": "across-context", "available": True, "status": "installed"},
            {"plugin_id": "across-orchestrator", "available": True, "status": "installed"},
            {"plugin_id": "across-autopilot", "available": True, "status": "installed"},
        ],
        capability_registry={
            "providers": [{"id": "across-agents-assistant"}, {"id": "across-autopilot"}],
            "capabilities": _capabilities(),
        },
        registry_health={"status": "passed", "checks": [{"id": "non_secret", "status": "passed"}]},
        agent_cards={"cards": [{"agent_id": "owner", "name": "Owner", "capabilities": [{"id": "review"}]}]},
        mcp_safety={"servers": []},
        autopilot_registry={"built_in": [{"id": "repo-quality-copilot"}]},
        autopilot_runs={
            "runs": [
                {"run_id": "run-new", "spec_id": "repo-quality-copilot", "status": "completed"},
                {"run_id": "run-old", "spec_id": "repo-quality-copilot", "status": "failed"},
            ],
            "run_count": 2,
        },
        autopilot_telemetry={"runs": {"total": 2, "completed": 1, "failed": 1}},
        ops_dashboard={"status": "passed", "summary": {"capability_ready_count": 42}},
        release_evaluation={"release_readiness": "no_evidence", "evaluated_task_count": 0},
        memory_metrics={"totals": {"candidate_count": 0, "pending_count": 0, "approved_count": 0}},
        pending_memories=[],
        agent_plugin_runtime=_agent_plugin_runtime(),
        agent_interop_e2e={"status": "passed", "summary": {"failed_count": 0, "passed_count": 11}},
        generated_at="2026-06-23T00:00:00Z",
    )

    assert roadmap["status"] == "passed"
    assert roadmap["sections"]["evaluation_telemetry"]["status"] == "passed"
    assert roadmap["sections"]["evaluation_telemetry"]["summary"]["failed_run_count"] == 0
    assert roadmap["sections"]["evaluation_telemetry"]["summary"]["historical_failed_run_count"] == 1
    assert roadmap["sections"]["evaluation_telemetry"]["summary"]["agent_interop_e2e_status"] == "passed"


def test_ecosystem_roadmap_does_not_require_eval_evidence_before_first_run():
    roadmap = build_aaa_ecosystem_roadmap(
        plugins=[
            {"plugin_id": "across-context", "available": True, "status": "installed"},
            {"plugin_id": "across-orchestrator", "available": True, "status": "installed"},
            {"plugin_id": "across-autopilot", "available": True, "status": "installed"},
        ],
        capability_registry={"providers": [], "capabilities": _capabilities()},
        registry_health={"status": "passed"},
        agent_cards={"cards": []},
        mcp_safety={},
        autopilot_registry={},
        autopilot_runs={"runs": [], "run_count": 0},
        autopilot_telemetry={"runs": {"total": 0, "failed": 0}},
        ops_dashboard={"status": "passed", "summary": {"capability_ready_count": 42}},
        release_evaluation={"release_readiness": "no_evidence", "evaluated_task_count": 0},
        memory_metrics={"totals": {"candidate_count": 0, "pending_count": 0}},
        pending_memories=[],
        agent_plugin_runtime=_agent_plugin_runtime(),
        agent_interop_e2e={"status": "not_run", "summary": {}},
    )

    assert roadmap["sections"]["evaluation_telemetry"]["status"] == "passed"
    assert roadmap["sections"]["trust_sandbox"]["status"] == "passed"


def test_ecosystem_roadmap_surfaces_virtual_agent_context_pack():
    runtime = {
        "status": "passed",
        "summary": {"context_pack_count": 1, "agent_plugin_count": 1},
        "sections": {
            "context_agent_packs": {
                "id": "context_agent_packs",
                "status": "passed",
                "summary": {"context_pack_count": 1, "memory_count": 0, "agent_plugin_count": 1},
                "items": [
                    {
                        "id": "demo.echo-agent:empty",
                        "agent_plugin_id": "demo.echo-agent",
                        "scope": "agent-plugin",
                        "type": "context-pack",
                        "status": "empty",
                        "count": 0,
                        "virtual": True,
                        "ready_for_agent_loading": True,
                    }
                ],
            }
        },
    }

    roadmap = build_aaa_ecosystem_roadmap(
        plugins=[],
        capability_registry={},
        registry_health={},
        agent_cards={},
        mcp_safety={},
        autopilot_registry={},
        autopilot_runs={"runs": []},
        autopilot_telemetry={},
        ops_dashboard={"status": "passed"},
        release_evaluation={},
        memory_metrics={},
        pending_memories=[],
        agent_plugin_runtime=runtime,
    )

    context_section = roadmap["sections"]["context_packs"]
    assert context_section["status"] == "passed"
    assert context_section["summary"]["context_pack_count"] == 1
    assert context_section["items"][0]["id"] == "demo.echo-agent:empty"
    assert context_section["items"][0]["virtual"] is True
    assert context_section["items"][0]["ready_for_agent_loading"] is True


def _agent_plugin_runtime():
    return {
        "status": "passed",
        "summary": {
            "downstream_count": 3,
            "downstream_ready_count": 3,
            "agent_plugin_count": 1,
            "external_agent_count": 1,
            "healthy_external_agent_count": 1,
            "ready_agent_plugin_count": 1,
            "context_pack_count": 1,
        },
        "sections": {
            "orchestrator_external_agents": {
                "id": "orchestrator_external_agents",
                "title": "Orchestrator External Agent Registry",
                "status": "passed",
                "summary": {"agent_count": 1, "healthy_agent_count": 1},
                "items": [{"id": "demo.echo-agent", "agent_id": "demo.echo", "status": "passed"}],
            },
            "autopilot_agent_plugin_runtime": {
                "id": "autopilot_agent_plugin_runtime",
                "title": "Autopilot Generic Agent Plugin Runtime",
                "status": "passed",
                "summary": {"agent_plugin_count": 1, "ready_agent_plugin_count": 1},
                "items": [{"id": "demo.echo-agent", "status": "passed"}],
            },
            "context_agent_packs": {
                "id": "context_agent_packs",
                "title": "Context Agent Plugin Packs",
                "status": "passed",
                "summary": {"context_pack_count": 1, "memory_count": 2, "agent_plugin_count": 1},
                "items": [{"id": "demo.echo-agent:global:note:active"}],
            },
        },
    }
