from across_agents_assistant.external_task_planning import (
    ExternalTaskPlanningRequest,
    agent_adapters_for_external_task,
    deliverables_for_external_task,
    external_owner_agent,
    external_subtask_agents,
    host_agent_adapter_command,
    planned_subtasks_for_external_task,
)


def test_strict_dependency_planning_creates_serial_dependencies():
    req = ExternalTaskPlanningRequest(
        description="Create README.md and app.py for a dashboard",
        task_types=["functional", "artifact"],
        allowed_subtask_agents=["claude", "codex"],
        strict_dependency=True,
    )

    deliverables = deliverables_for_external_task(req)
    subtasks = planned_subtasks_for_external_task(req, deliverables)

    assert deliverables == ["README.md", "app.py"]
    assert [item["id"] for item in subtasks] == ["stage-1", "stage-2"]
    assert subtasks[0]["dependencies"] == []
    assert subtasks[1]["dependencies"] == ["stage-1"]
    assert [item["agent"] for item in subtasks] == ["claude", "codex"]


def test_parallel_planning_leaves_dependencies_empty():
    req = ExternalTaskPlanningRequest(
        description="Build a dashboard",
        task_types=["artifact"],
        allowed_subtask_agents=["claude"],
        strict_dependency=False,
    )

    deliverables = deliverables_for_external_task(req)
    subtasks = planned_subtasks_for_external_task(req, deliverables)

    assert deliverables == ["README.md"]
    assert subtasks == []


def test_multiple_lines_in_same_wave_have_unique_ids_and_wave_dependencies():
    req = ExternalTaskPlanningRequest(
        description="\n".join(
            [
                "Wave 1 Contract: create docs/contract.json.",
                "Wave 1 Architecture: create docs/architecture.md.",
                "Wave 2 API: create api/server.mjs.",
                "Wave 2 Schema: create api/schema.json.",
                "Wave 3 UI: create web/index.html.",
            ]
        ),
        allowed_subtask_agents=["claude", "codex"],
        strict_dependency=True,
    )

    deliverables = deliverables_for_external_task(req)
    subtasks = planned_subtasks_for_external_task(req, deliverables)

    assert [item["id"] for item in subtasks] == [
        "wave-1-1",
        "wave-1-2",
        "wave-2-1",
        "wave-2-2",
        "wave-3-1",
    ]
    assert [item["dependencies"] for item in subtasks] == [
        [],
        [],
        ["wave-1-1", "wave-1-2"],
        ["wave-1-1", "wave-1-2"],
        ["wave-2-1", "wave-2-2"],
    ]
    assert len({item["id"] for item in subtasks}) == len(subtasks)
    assert all(item["id"] not in item["dependencies"] for item in subtasks)


def test_negative_guidance_does_not_erase_explicit_artifact_in_prior_clause():
    req = ExternalTaskPlanningRequest(
        description=(
            "修复发现的高优先级问题；最终生成 DELIVERY_AUDIT.md，记录实际变更；"
            "不要只写报告，必须实际修复至少一个可验证问题。"
        ),
        task_types=["functional", "artifact"],
    )

    assert deliverables_for_external_task(req) == ["DELIVERY_AUDIT.md"]


def test_negative_file_clause_is_not_treated_as_required_delivery():
    req = ExternalTaskPlanningRequest(
        description="Create app.py. Do not create package.json or node_modules.",
        task_types=["functional", "artifact"],
    )

    assert deliverables_for_external_task(req) == ["app.py"]


def test_owner_and_subtask_agent_defaults_are_host_controlled():
    req = ExternalTaskPlanningRequest(description="Build a dashboard")

    assert external_owner_agent(req) == "demo"
    assert external_subtask_agents(req) == ["demo"]


def test_owner_agent_can_seed_subtask_agents():
    req = ExternalTaskPlanningRequest(description="Build a dashboard", owner_agent="openclaw")

    assert external_owner_agent(req) == "openclaw"
    assert external_subtask_agents(req) == ["openclaw"]


def test_real_agent_selection_declares_aaa_host_command_adapters():
    req = ExternalTaskPlanningRequest(
        description="Build a dashboard",
        owner_agent="OpenClaw",
        allowed_subtask_agents=["hermes", "demo", "claude", "hermes"],
    )

    adapters = agent_adapters_for_external_task(req)

    assert set(adapters) == {"openclaw", "hermes", "claude"}
    for agent_id, spec in adapters.items():
        assert spec["type"] == "command"
        assert spec["command"][-4:] == [
            "-m",
            "across_agents_assistant.orchestrator_agent_adapter",
            "--agent",
            agent_id,
        ]


def test_kimi_host_adapter_declares_only_required_runtime_state_paths():
    req = ExternalTaskPlanningRequest(
        description="Build a dashboard",
        owner_agent="kimi",
        allowed_subtask_agents=["claude"],
    )

    adapters = agent_adapters_for_external_task(req)

    assert adapters["kimi"]["command"][-2:] == ["--timeout", "1200"]
    assert adapters["kimi"]["sandboxPolicy"]["network_policy"] == "adapter_scoped"
    assert adapters["kimi"]["sandboxPolicy"]["execution"] == {
        "timeout_seconds": 90,
        "refresh_timeout_on_output": True,
        "max_wall_timeout_seconds": 1200,
    }
    filesystem_policy = adapters["kimi"]["sandboxPolicy"]["filesystem_policy"]
    assert filesystem_policy["runtime_state_roots"] == [
        "~/.kimi-code/logs",
        "~/.kimi-code/sessions",
        "~/.kimi-code/telemetry",
        "~/.kimi-code/updates",
        "~/.kimi-code/user-history",
    ]
    assert filesystem_policy["runtime_state_files"] == ["~/.kimi-code/session_index.jsonl"]
    assert "~/.kimi-code" not in filesystem_policy["runtime_state_roots"]
    assert "~/.kimi-code/config.toml" not in filesystem_policy["runtime_state_files"]
    assert "sandboxPolicy" not in adapters["claude"]
    assert adapters["claude"]["command"][-1] == "claude"


def test_kimi_packaged_host_command_has_explicit_timeout(monkeypatch):
    import across_agents_assistant.external_task_planning as planning

    monkeypatch.setattr(planning.sys, "frozen", True, raising=False)
    monkeypatch.setattr(planning.sys, "executable", "/Applications/AAA/backend")

    assert host_agent_adapter_command("Kimi") == [
        "/Applications/AAA/backend",
        "orchestrator-agent-adapter",
        "--agent",
        "kimi",
        "--timeout",
        "1200",
    ]


def test_packaged_host_agent_adapter_command_uses_backend_subcommand(monkeypatch):
    import across_agents_assistant.external_task_planning as planning

    monkeypatch.setattr(planning.sys, "frozen", True, raising=False)
    monkeypatch.setattr(planning.sys, "executable", "/Applications/Across Agents Assistant.app/Contents/Resources/backend/backend")

    assert host_agent_adapter_command("Claude") == [
        "/Applications/Across Agents Assistant.app/Contents/Resources/backend/backend",
        "orchestrator-agent-adapter",
        "--agent",
        "claude",
    ]
