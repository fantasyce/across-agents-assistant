from across_agents_assistant.external_agent_plugin_gateway import (
    AGENT_PLUGIN_RUNTIME_SCHEMA_VERSION,
    build_agent_plugin_runtime_status,
)


def test_agent_plugin_runtime_status_merges_three_downstream_contracts():
    payload = build_agent_plugin_runtime_status(
        orchestrator={
            "status": "passed",
            "payload": {
                "summary": {"agent_count": 1, "healthy_agent_count": 1, "plugin_count": 1},
                "agents": [
                    {
                        "plugin_id": "demo.echo-agent",
                        "agent_id": "demo.echo",
                        "display_name": "Demo Echo",
                        "health": {"status": "passed"},
                        "trust": {"mutation_boundary": "read_only"},
                    }
                ],
            },
        },
        autopilot={
            "status": "passed",
            "payload": {
                "sections": {
                    "agent_plugin_runtime": {
                        "status": "passed",
                        "summary": {"agent_plugin_count": 1, "ready_agent_plugin_count": 1, "dry_run_only": True},
                        "items": [{"id": "demo.echo-agent", "status": "passed"}],
                    }
                }
            },
        },
        context={
            "status": "passed",
            "payload": {
                "status": "passed",
                "summary": {"context_pack_count": 1, "memory_count": 2, "pending_count": 0, "agent_plugin_count": 1},
                "packs": [{"id": "demo.echo-agent:global:note:active", "agent_plugin_id": "demo.echo-agent"}],
            },
        },
    )

    assert payload["schema_version"] == AGENT_PLUGIN_RUNTIME_SCHEMA_VERSION
    assert payload["status"] == "passed"
    assert payload["summary"]["downstream_ready_count"] == 3
    assert payload["summary"]["agent_plugin_count"] == 1
    assert payload["summary"]["context_pack_count"] == 1
    assert payload["security"]["shell_execution"] is False


def test_agent_plugin_runtime_status_accepts_virtual_empty_context_pack():
    payload = build_agent_plugin_runtime_status(
        orchestrator={
            "status": "passed",
            "payload": {
                "summary": {"agent_count": 1, "healthy_agent_count": 1, "plugin_count": 1},
                "agents": [
                    {
                        "plugin_id": "demo.echo-agent",
                        "agent_id": "demo.echo",
                        "display_name": "Demo Echo",
                        "health": {"status": "passed"},
                        "trust": {"mutation_boundary": "read_only"},
                    }
                ],
            },
        },
        autopilot={
            "status": "passed",
            "payload": {
                "sections": {
                    "agent_plugin_runtime": {
                        "status": "passed",
                        "summary": {"agent_plugin_count": 1, "ready_agent_plugin_count": 1, "dry_run_only": True},
                        "items": [{"id": "demo.echo-agent", "status": "passed"}],
                    }
                }
            },
        },
        context={
            "status": "passed",
            "payload": {
                "status": "passed",
                "summary": {"context_pack_count": 1, "memory_count": 0, "pending_count": 0, "agent_plugin_count": 1},
                "packs": [
                    {
                        "id": "demo.echo-agent:empty",
                        "agent_plugin_id": "demo.echo-agent",
                        "status": "empty",
                        "count": 0,
                        "virtual": True,
                        "ready_for_agent_loading": True,
                    }
                ],
            },
        },
    )

    assert payload["status"] == "passed"
    assert payload["summary"]["context_pack_count"] == 1
    assert payload["sections"]["context_agent_packs"]["items"][0]["virtual"] is True
