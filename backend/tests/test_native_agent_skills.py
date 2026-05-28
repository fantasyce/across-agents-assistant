import os
from pathlib import Path

os.environ["ACROSS_AGENTS_DB_PATH"] = os.path.join(
    os.environ.get("TMPDIR", "/tmp"),
    "test_native_agent_skills.db",
)
os.makedirs(os.path.dirname(os.environ["ACROSS_AGENTS_DB_PATH"]), exist_ok=True)

from fastapi.testclient import TestClient

from across_agents_assistant import api_server
from across_agents_assistant.api_server import app
from across_agents_assistant.native_agent_skills import (
    NativeSkillManager,
    NativeSkillRequest,
)
from across_agents_assistant.task_manager.orchestration.owner_agent import OwnerAgent
from across_agents_assistant.task_manager.state import TaskState


class RecordingRunner:
    def __init__(self, outputs=None):
        self.outputs = outputs or {}
        self.commands = []

    def run(self, command, *, timeout=20):
        self.commands.append(list(command))
        key = tuple(command)
        return self.outputs.get(key, "")


class MockLLMResponse:
    def __init__(self, text: str):
        self.text = text


class MockLLMGateway:
    def __init__(self, response_text: str):
        self._response_text = response_text

    def __call__(self, system_prompt: str, message: str, temperature: float):
        return MockLLMResponse(self._response_text)


def _local_agents():
    return [
        {"id": "claude", "name": "Claude Code", "characteristics": "architecture"},
        {"id": "hermes", "name": "Hermes", "characteristics": "frontend"},
        {"id": "openclaw", "name": "OpenClaw", "characteristics": "general"},
    ]


def _business_subtasks(task):
    return [st for st in task.subtasks if not st.subtask_id.endswith("-decompose")]


def test_claude_adapter_creates_lists_and_removes_managed_user_skill(tmp_path):
    manager = NativeSkillManager(
        claude_user_skills_dir=tmp_path / "claude-skills",
    )

    result = manager.install_skill(
        "claude",
        NativeSkillRequest(
            name="Release Gate",
            description="Check release evidence before approving packaging work.",
            body="Confirm tests, packaging notes, and rollback steps before release.",
        ),
    )

    skill_file = tmp_path / "claude-skills" / "release-gate" / "SKILL.md"
    assert result["status"] == "installed"
    assert result["id"] == "release-gate"
    assert skill_file.exists()
    assert "managed_by: across-agents-assistant" in skill_file.read_text(encoding="utf-8")

    state = manager.list_agent_skills("claude")

    assert state["agent_id"] == "claude"
    assert state["supports_create"] is True
    assert state["supports_uninstall"] is True
    assert state["skills"][0]["name"] == "Release Gate"
    assert state["skills"][0]["source"] == "user"
    assert state["skills"][0]["managed_by_app"] is True

    removed = manager.uninstall_skill("claude", "release-gate")

    assert removed["status"] == "uninstalled"
    assert not skill_file.exists()


def test_cli_adapters_use_native_skill_commands_for_hermes_and_openclaw():
    runner = RecordingRunner(
        {
            ("hermes", "skills", "list", "--source", "all"): (
                "Installed skills\n"
                "- github-review  hub  enabled\n"
                "- release-gate   local disabled\n"
            ),
            ("openclaw", "skills", "list", "--json"): (
                '[{"name":"frontend-review","description":"Review UI delivery","ready":true}]'
            ),
        }
    )
    manager = NativeSkillManager(command_runner=runner)

    hermes = manager.list_agent_skills("hermes")
    openclaw = manager.list_agent_skills("openclaw")
    install = manager.install_skill(
        "hermes",
        NativeSkillRequest(identifier="openai/skills/github-review", force=True),
    )
    update = manager.update_skill("openclaw", "frontend-review")

    assert [skill["id"] for skill in hermes["skills"]] == ["github-review", "release-gate"]
    assert hermes["skills"][0]["status"] == "enabled"
    assert openclaw["skills"][0]["id"] == "frontend-review"
    assert install["command"] == [
        "hermes",
        "skills",
        "install",
        "openai/skills/github-review",
        "--force",
        "--yes",
    ]
    assert update["command"] == ["openclaw", "skills", "update", "frontend-review"]


def test_openclaw_list_marks_missing_requirements_unavailable():
    runner = RecordingRunner(
        {
            ("openclaw", "skills", "list", "--json"): (
                '{"skills": ['
                '{"id":"apple-notes","name":"apple-notes","description":"Apple Notes control"},'
                '{"id":"gstack","name":"gstack","description":"Browser QA"}'
                ']}'
            ),
            ("openclaw", "skills", "check"): (
                "Skills Status Check\n\n"
                "Ready to use:\n"
                "  gstack\n\n"
                "Missing requirements:\n"
                "  apple-notes (bins: memo; env: NOTES_TOKEN)\n"
            ),
        }
    )
    manager = NativeSkillManager(command_runner=runner)

    state = manager.list_agent_skills("openclaw")
    skills = {skill["id"]: skill for skill in state["skills"]}

    assert skills["gstack"]["availability"] == "available"
    assert skills["apple-notes"]["status"] == "unavailable"
    assert skills["apple-notes"]["availability"] == "unavailable"
    assert skills["apple-notes"]["missing_requirements"] == ["bins: memo", "env: NOTES_TOKEN"]
    assert "Missing requirements" in skills["apple-notes"]["unavailable_reason"]
    assert ("openclaw", "skills", "check") in [tuple(command) for command in runner.commands]


def test_native_skill_context_excludes_unavailable_checked_skills(monkeypatch):
    runner = RecordingRunner(
        {
            ("openclaw", "skills", "list", "--json"): (
                '{"skills": [{"id":"apple-notes","name":"apple-notes","description":"Apple Notes control"}]}'
            ),
            ("openclaw", "skills", "check"): (
                "Skills Status Check\n\n"
                "Missing requirements:\n"
                "  apple-notes (bins: memo)\n"
            ),
        }
    )
    manager = NativeSkillManager(command_runner=runner)
    monkeypatch.setattr(
        "across_agents_assistant.api_server.get_native_skill_manager",
        lambda: manager,
    )

    capability_context = api_server._append_native_skill_context(
        {},
        ["openclaw"],
        "Export selected Apple Notes.",
    )

    assert capability_context.get("native_skills", {}).get("openclaw", []) == []
    assert "apple-notes" not in capability_context.get("prompt", "")


def test_hermes_native_skill_parser_handles_table_output():
    runner = RecordingRunner(
        {
            ("hermes", "skills", "list", "--source", "all"): (
                "                                Installed Skills                                \n"
                "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━┓\n"
                "┃ Name                              ┃ Category             ┃ Source  ┃ Trust   ┃\n"
                "┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━┩\n"
                "│ dogfood                           │                      │ builtin │ builtin │\n"
                "│ apple-notes                       │ apple                │ builtin │ builtin │\n"
                "└───────────────────────────────────┴──────────────────────┴─────────┴─────────┘\n"
            ),
        }
    )
    manager = NativeSkillManager(command_runner=runner)

    hermes = manager.list_agent_skills("hermes")

    assert [skill["id"] for skill in hermes["skills"]] == ["dogfood", "apple-notes"]
    assert hermes["skills"][0]["name"] == "dogfood"
    assert hermes["skills"][0]["status"] == "builtin"


def test_native_skills_api_round_trip(monkeypatch, tmp_path):
    manager = NativeSkillManager(claude_user_skills_dir=tmp_path / "claude-skills")
    monkeypatch.setattr(
        "across_agents_assistant.api_server.get_native_skill_manager",
        lambda: manager,
    )

    client = TestClient(app)
    response = client.post(
        "/api/native-skills/claude/install",
        json={
            "name": "Code Review Gate",
            "description": "Review correctness risks before accepting code changes.",
            "body": "List blocking bugs, risky assumptions, and missing verification.",
        },
    )
    assert response.status_code == 200
    assert response.json()["skill"]["id"] == "code-review-gate"

    response = client.get("/api/native-skills")
    assert response.status_code == 200
    body = response.json()
    assert "claude" in body["agents"]
    assert body["agents"]["claude"]["skills"][0]["name"] == "Code Review Gate"

    response = client.delete("/api/native-skills/claude/code-review-gate")
    assert response.status_code == 200
    assert response.json()["skill"]["status"] == "uninstalled"


def test_auto_task_includes_installed_native_skill_context(monkeypatch, tmp_path):
    captured = {}
    manager = NativeSkillManager(claude_user_skills_dir=tmp_path / "claude-skills")
    manager.install_skill(
        "claude",
        NativeSkillRequest(
            name="Architecture Review",
            description="Review architecture boundaries before implementation.",
            body="Check API boundaries, data ownership, and rollout risks.",
        ),
    )

    class FakeOrchestrator:
        def submit_task(self, description, context):
            captured["description"] = description
            captured["context"] = context
            return "task-native-skills"

    monkeypatch.setattr(
        "across_agents_assistant.api_server._check_llm_provider_readiness",
        lambda: [],
    )
    monkeypatch.setattr(
        "across_agents_assistant.api_server.get_task_orchestrator",
        lambda: FakeOrchestrator(),
    )
    monkeypatch.setattr(
        "across_agents_assistant.api_server.get_native_skill_manager",
        lambda: manager,
    )

    client = TestClient(app)
    response = client.post(
        "/api/tasks/auto",
        json={
            "description": "Design a plugin system.",
            "task_types": ["functional"],
            "owner_agent": "claude",
            "allowed_subtask_agents": ["claude"],
        },
    )

    assert response.status_code == 200
    capabilities = captured["context"]["agent_capabilities"]
    assert capabilities["native_skills"]["claude"][0]["name"] == "Architecture Review"
    assert "Installed native skills" in capabilities["prompt"]


def test_native_skill_context_from_cli_adapter_routes_owner_agent(monkeypatch, tmp_path):
    runner = RecordingRunner(
        {
            ("hermes", "skills", "list", "--source", "all"): "Keyboard Accessibility Review    enabled\n",
            ("openclaw", "skills", "list", "--json"): '{"skills":[]}',
        }
    )
    manager = NativeSkillManager(
        command_runner=runner,
        claude_user_skills_dir=tmp_path / "claude-skills",
    )
    monkeypatch.setattr(
        "across_agents_assistant.api_server.get_native_skill_manager",
        lambda: manager,
    )

    capability_context = api_server._append_native_skill_context(
        {},
        ["claude", "hermes", "openclaw"],
        "Review keyboard accessibility and screen reader behavior for the settings workflow.",
    )
    state = TaskState()
    task = state.create_task(
        "Review keyboard accessibility and screen reader behavior for the settings workflow.",
        project_dir=str(tmp_path),
        owner_agent="claude",
        allowed_subtask_agents=["claude", "hermes", "openclaw"],
        task_types=["functional"],
    )
    owner = OwnerAgent(
        MockLLMGateway(
            """{"subtasks": [
                {"id": "a11y", "description": "Review keyboard accessibility and screen reader behavior for the settings workflow", "agent": "claude", "priority": 1, "dependencies": []}
            ]}"""
        ),
        state,
    )
    owner._get_available_agents = _local_agents

    result = owner.decompose_and_assign(
        task,
        context={
            "owner_agent": "claude",
            "allowed_subtask_agents": ["claude", "hermes", "openclaw"],
            "task_types": ["functional"],
            "agent_capabilities": capability_context,
        },
    )

    subtask = _business_subtasks(result)[0]
    assert subtask.agent_id == "hermes"
    assert "Native skill match: Keyboard Accessibility Review" in subtask.description
    assert ("hermes", "skills", "list", "--source", "all") in [tuple(command) for command in runner.commands]
