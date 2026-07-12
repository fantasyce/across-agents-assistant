from pathlib import Path

import across_agents_assistant.agent_interop_e2e as interop
from across_agents_assistant.agent_interop_e2e import _resolve_roots, run_agent_interop_e2e


PROJECTS_ROOT = Path(__file__).resolve().parents[4]


def test_agent_interop_resolves_packaged_app_to_projects_root(monkeypatch):
    monkeypatch.delenv("ACROSS_PROJECTS_ROOT", raising=False)
    roots = _resolve_roots(PROJECTS_ROOT / "build" / "Across Agents Assistant.app" / "Contents", {})

    assert roots["projects"] == PROJECTS_ROOT
    assert (roots["autopilot"] / "examples" / "plugin-compatibility-lab-v2.loop.json").is_file()


def test_agent_interop_prefers_managed_plugins_for_packaged_app(tmp_path, monkeypatch):
    managed = tmp_path / ".across" / "plugins"
    (managed / "across-autopilot" / "examples").mkdir(parents=True)
    (managed / "across-autopilot" / "examples" / "plugin-compatibility-lab-v2.loop.json").write_text("{}", encoding="utf-8")
    (managed / "across-autopilot" / "src").mkdir()
    (managed / "across-autopilot" / "src" / "cli.js").write_text("", encoding="utf-8")
    (managed / "across-context" / "src").mkdir(parents=True)
    (managed / "across-context" / "src" / "cli.js").write_text("", encoding="utf-8")
    (managed / "across-orchestrator" / "venv" / "bin").mkdir(parents=True)
    (managed / "across-orchestrator" / "venv" / "bin" / "across-orchestrator").write_text("", encoding="utf-8")
    monkeypatch.setattr(interop, "_running_packaged_app", lambda: True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ACROSS_PROJECTS_ROOT", raising=False)

    roots = _resolve_roots(None, {"HOME": str(tmp_path)})

    assert roots["projects"] == managed.resolve()
    assert roots["autopilot"] == (managed / "across-autopilot").resolve()


def test_agent_interop_recalls_the_pending_memories_it_just_created(tmp_path, monkeypatch):
    commands = []

    def fake_run_json(command, **_kwargs):
        commands.append(command)
        return {"result_count": 1}

    monkeypatch.setattr(interop, "_run_json", fake_run_json)

    interop._context_recall_evidence(tmp_path, {}, "run-test")
    interop._context_recall_agent_team_receipt(tmp_path, {}, "pack-test")

    assert commands[0][-3:] == ["--status", "pending", "--json"]
    assert commands[1][-3:] == ["--status", "pending", "--json"]


def test_agent_interop_sandbox_evidence_e2e(tmp_path, monkeypatch):
    monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "aaa-home"))
    payload = run_agent_interop_e2e(
        env={
            "ACROSS_HOME": str(tmp_path / "across-home"),
            "ACROSS_AGENTS_HOME": str(tmp_path / "aaa-home"),
            "ACROSS_CONTEXT_HOME": str(tmp_path / "across-home" / "data" / "across-context"),
            "ACROSS_ORCHESTRATOR_HOME": str(tmp_path / "across-home" / "data" / "across-orchestrator"),
        },
        projects_root=PROJECTS_ROOT,
        persist=False,
    )

    assert payload["schema_version"] == "across-aaa-agent-interop-e2e/1.0"
    assert payload["status"] == "passed", payload["errors"]
    assert payload["summary"]["failed_count"] == 0
    assert payload["summary"]["host_target_count"] == 5
    assert payload["summary"]["mcp_server_count"] == 3
    assert payload["summary"]["evidence_node_count"] >= 10
    assert payload["summary"]["protocol_readiness_score"] >= 50
    assert payload["summary"]["market_readiness_status"] == "passed"
    assert payload["summary"]["trust_receipt_status"] == "passed"
    assert payload["summary"]["frontier_interop_status"] == "passed"
    assert payload["summary"]["remote_mcp_template_status"] == "passed"
    assert payload["summary"]["a2a_delegation_status"] == "passed"
    assert payload["summary"]["projection_status"] == "passed"
    assert payload["summary"]["projection_count"] >= 5
    assert payload["summary"]["agui_projection_status"] == "passed"
    assert payload["summary"]["async_task_status"] == "passed"
    assert payload["summary"]["context_skills_bridge_status"] == "passed"
    assert payload["summary"]["computer_use_sandbox_status"] == "passed"
    assert payload["summary"]["local_agent_protocol_status"] == "passed"
    assert payload["summary"]["otel_span_count"] >= 10
    assert payload["summary"]["eval_case_count"] >= 1
    assert payload["summary"]["otlp_resource_span_count"] == 1
    assert set(payload["host_exports"]["host_targets"]) >= {"codex", "claude_code", "mcp", "a2a", "across"}
    assert payload["host_exports"]["product_card_schema"] == "across-workflow-pack-product-card/1.0"
    assert payload["host_exports"]["trust_receipt_schema"] == "across-agent-team-trust-receipt/1.0"
    assert payload["host_exports"]["frontier_interop_schema"] == "across-workflow-pack-frontier-interop/1.0"
    assert payload["host_exports"]["remote_mcp_schema"] == "across-remote-mcp-oauth-template/1.0"
    assert payload["host_exports"]["a2a_delegation_schema"] == "across-a2a-task-delegation/2.0"
    assert payload["host_exports"]["mcp_tasks_schema"] == "across-async-task/1.0"
    assert payload["host_exports"]["agui_schema"] == "across-agui-projection/1.0"
    assert payload["host_exports"]["projection_schema"] == "across-external-projection/1.0"
    assert payload["host_exports"]["otel_schema"] == "across-otel-genai-export/1.0"
    assert payload["agent_team_readiness"]["status"] == "passed"
    assert payload["frontier_interop"]["remote_mcp"]["status"] == "passed"
    assert payload["frontier_interop"]["a2a_delegation"]["status"] == "passed"
    assert payload["frontier_interop"]["a2a_delegation"]["schema_version"] == "across-a2a-task-delegation/2.0"
    assert payload["frontier_interop"]["projection_status"]["status"] == "passed"
    assert payload["frontier_interop"]["ag_ui"]["schema_version"] == "across-agui-projection/1.0"
    assert payload["frontier_interop"]["ag_ui"]["status"] == "passed"
    assert payload["frontier_interop"]["mcp_tasks"]["schema_version"] == "across-aaa-async-task-e2e/1.0"
    assert payload["frontier_interop"]["mcp_tasks"]["status"] == "passed"
    assert payload["frontier_interop"]["otel_export"]["schema_version"] == "across-otel-genai-export/1.0"
    assert payload["frontier_interop"]["otel_export"]["otlp"]["schema_version"] == "otlp-traces-json/1.0"
    assert payload["frontier_interop"]["otel_export"]["otlp_file"]
    assert payload["projection_status"]["schema_version"] == "across-aaa-projection-status/1.0"
    assert payload["context_bridge"]["skill_export"]["schema_version"] == "agentskills.io-export/1.0"
    assert payload["context_bridge"]["skill_export"]["status"] == "passed"
    assert payload["context_bridge"]["memory_backend"]["backend"] == "mem0"
    assert payload["context_bridge"]["memory_backend"]["status"] == "passed"
    assert payload["sandbox_evaluation"]["policy"]["vendor_lock_in"] is False
    assert payload["sandbox_evaluation"]["policy"]["raw_transcripts_included"] is False
    assert payload["local_agent_protocols"]["kimi_code"]["acp"] == "optional"
    assert payload["local_agent_protocols"]["boundaries"]["product_paths_required"] == "~/.across"
    assert payload["host_install_contracts"]["status"] == "passed"
    assert set(payload["host_install_contracts"]["claude_desktop"]["server_ids"]) >= {
        "across-context",
        "across-orchestrator",
        "across-autopilot",
    }
    assert payload["mcp"]["across-context"]["required_tool_present"] is True
    assert payload["mcp"]["across-orchestrator"]["required_tool_present"] is True
    assert payload["mcp"]["across-autopilot"]["required_tool_present"] is True
    check_statuses = {item["id"]: item["status"] for item in payload["checks"]}
    for required in [
        "workflow_pack_export",
        "host_targets_complete",
        "workflow_product_card_ready",
        "workflow_protocol_readiness_honest",
        "workflow_trust_receipt_ready",
        "generic_host_install_contracts",
        "loop_spec_validate",
        "loop_spec_dry_run",
        "autopilot_loop_run",
        "workflow_pack_gate_passed",
        "autopilot_evidence_graph_present",
        "orchestrator_sandbox_probe",
        "orchestrator_agent_team_readiness",
        "orchestrator_evidence_graph",
        "orchestrator_remote_mcp_oauth_template",
        "orchestrator_a2a_task_delegation",
        "orchestrator_otel_genai_export",
        "frontier_interop_contracts_ready",
        "orchestrator_otlp_file_written",
        "projection_status_ready",
        "orchestrator_agui_projection",
        "orchestrator_agent_team_contract",
        "autopilot_async_task_projection",
        "context_skills_bridge_export",
        "context_memory_backend_contract",
        "computer_use_sandbox_eval_contract",
        "local_agent_protocol_contracts",
        "context_evidence_memory",
        "context_evidence_recall",
        "context_evidence_recalled",
        "context_agent_team_receipt_memory",
        "context_agent_team_receipt_recall",
        "context_agent_team_receipt_recalled",
        "three_plugin_mcp_load",
        "mcp_tools_exposed",
    ]:
        assert check_statuses[required] == "passed"
