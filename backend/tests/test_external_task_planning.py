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
