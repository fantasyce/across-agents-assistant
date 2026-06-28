from across_agents_assistant.external_agent_plugin_gateway import (
    AGENT_PLUGIN_RUNTIME_SCHEMA_VERSION,
    _effective_commands,
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


def test_agent_plugin_runtime_status_treats_reachable_empty_inventory_as_ready():
    payload = build_agent_plugin_runtime_status(
        orchestrator={
            "status": "passed",
            "payload": {
                "status": "passed",
                "summary": {"agent_count": 0, "healthy_agent_count": 0, "plugin_count": 0},
                "agents": [],
            },
        },
        autopilot={
            "status": "passed",
            "payload": {
                "sections": {
                    "agent_plugin_runtime": {
                        "status": "unavailable",
                        "summary": {"agent_plugin_count": 0, "ready_agent_plugin_count": 0, "dry_run_only": True},
                        "items": [],
                    }
                }
            },
        },
        context={
            "status": "passed",
            "payload": {
                "status": "passed",
                "summary": {"context_pack_count": 0, "memory_count": 0, "pending_count": 0, "agent_plugin_count": 0},
                "packs": [],
            },
        },
    )

    assert payload["status"] == "passed"
    assert payload["summary"]["downstream_ready_count"] == 3
    assert payload["summary"]["agent_plugin_count"] == 0


def test_agent_plugin_runtime_uses_managed_across_home_binaries(tmp_path):
    across_home = tmp_path / ".across"
    bin_dir = across_home / "bin"
    bin_dir.mkdir(parents=True)
    managed = bin_dir / "across-autopilot"
    managed.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    managed.chmod(0o755)

    commands = _effective_commands(None, {"ACROSS_HOME": str(across_home)})

    assert commands["autopilot"][0] == str(managed)
