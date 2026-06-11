import os

os.environ["ACROSS_AGENTS_DB_PATH"] = os.path.join(
    os.environ.get("TMPDIR", "/tmp"),
    "test_agent_capabilities.db",
)
os.makedirs(os.path.dirname(os.environ["ACROSS_AGENTS_DB_PATH"]), exist_ok=True)

from fastapi.testclient import TestClient

from across_agents_assistant.api_server import app
from across_agents_assistant.agent_capabilities import AgentCapabilityStore, DEFAULT_AGENT_IDS


def test_store_does_not_normalize_legacy_local_agent_alias(tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")

    profile = store.get_profile("local")

    assert profile["agent_id"] == "local"
    assert profile["enabled_skill_ids"] == []
    assert profile["enabled_plugin_ids"] == []
    assert profile["enabled_tool_names"] == []


def test_store_saves_agent_skill_plugin_tool_profile(tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")

    saved = store.save_profile(
        "hermes",
        {
            "enabled_skill_ids": ["frontend_design", "test_authoring"],
            "enabled_plugin_ids": ["filesystem", "local_kb"],
            "enabled_tool_names": ["read_file", "write_file"],
            "custom_instructions": "Prefer accessible, keyboard-first UI.",
            "strict_tool_scope": True,
        },
    )
    reloaded = AgentCapabilityStore(tmp_path / "agent-capabilities.json").get_profile("hermes")

    assert saved == reloaded
    assert reloaded["enabled_skill_ids"] == ["frontend_design", "test_authoring"]
    assert reloaded["enabled_plugin_ids"] == ["filesystem", "local_kb"]
    assert reloaded["enabled_tool_names"] == ["read_file", "write_file"]
    assert reloaded["custom_instructions"] == "Prefer accessible, keyboard-first UI."
    assert reloaded["strict_tool_scope"] is True


def test_store_builds_prompt_context_for_selected_agents(tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")
    store.save_profile(
        "deepseek",
        {
            "enabled_skill_ids": ["backend_api"],
            "enabled_plugin_ids": ["sqlite"],
            "enabled_tool_names": ["sqlite__sqlite_query"],
            "custom_instructions": "Favor typed request and response validation.",
            "strict_tool_scope": True,
        },
    )

    payload = store.build_task_context(["deepseek", "openclaw"])

    assert set(payload["profiles"].keys()) == {"deepseek", "openclaw"}
    assert "deepseek" in payload["prompt"]
    assert "Backend API implementation" in payload["prompt"]
    assert "sqlite__sqlite_query" in payload["prompt"]
    assert "Favor typed request and response validation." in payload["prompt"]
    assert "Strict scope" in payload["prompt"]


def test_across_context_plugin_can_be_enabled_for_every_agent(tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")

    for agent_id in DEFAULT_AGENT_IDS:
        store.save_profile(agent_id, {"enabled_plugin_ids": ["across_context"]})

    payload = store.build_task_context(DEFAULT_AGENT_IDS)

    assert set(payload["profiles"].keys()) == set(DEFAULT_AGENT_IDS)
    for agent_id in DEFAULT_AGENT_IDS:
        assert payload["profiles"][agent_id]["enabled_plugin_ids"] == ["across_context"]
        assert f"- {agent_id}:" in payload["prompt"]
    assert payload["prompt"].count("plugins=across_context") == len(DEFAULT_AGENT_IDS)


def test_across_context_plugin_is_default_for_every_known_agent(tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")

    payload = store.build_task_context(DEFAULT_AGENT_IDS)

    for agent_id in DEFAULT_AGENT_IDS:
        assert store.get_profile(agent_id)["enabled_plugin_ids"] == ["across_context"]
        assert payload["profiles"][agent_id]["enabled_plugin_ids"] == ["across_context"]
    assert payload["prompt"].count("plugins=across_context") == len(DEFAULT_AGENT_IDS)


def test_store_persists_custom_skill_and_includes_it_in_task_context(tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")

    skill = store.save_custom_skill(
        {
            "id": "custom_accessibility_review",
            "name": "Accessibility review",
            "description": "Review keyboard, contrast, and screen-reader behavior.",
            "prompt_hint": "Check accessibility acceptance criteria before marking UI work complete.",
            "tags": ["frontend", "quality", "accessibility"],
        }
    )
    store.save_profile("hermes", {"enabled_skill_ids": ["frontend_design", skill["id"]]})

    reloaded = AgentCapabilityStore(tmp_path / "agent-capabilities.json")
    payload = reloaded.build_task_context(["hermes"])

    assert skill in reloaded.skill_catalog()
    assert "Accessibility review" in payload["prompt"]
    assert "Check accessibility acceptance criteria" in payload["prompt"]


def test_store_deletes_custom_skill_from_all_profiles(tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")
    store.save_custom_skill(
        {
            "id": "custom_release_gate",
            "name": "Release gate",
            "description": "Verify packaging evidence before release.",
            "prompt_hint": "Confirm release evidence before approving packaging tasks.",
            "tags": ["release", "quality"],
        }
    )
    store.save_profile("minimax", {"enabled_skill_ids": ["devops_release", "custom_release_gate"]})

    deleted = store.delete_custom_skill("custom_release_gate")

    assert deleted is True
    assert "custom_release_gate" not in store.get_profile("minimax")["enabled_skill_ids"]
    assert all(skill["id"] != "custom_release_gate" for skill in store.skill_catalog())


def test_store_builds_task_preflight_recommendations(tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")

    preflight = store.build_task_preflight(
        description="Build a polished React dashboard UI with E2E tests.",
        owner_agent="auto",
        allowed_subtask_agents=["hermes", "deepseek", "minimax"],
        task_types=["functional"],
    )

    assert preflight["recommended_agent_ids"][0] == "hermes"
    hermes = next(item for item in preflight["agent_summaries"] if item["agent_id"] == "hermes")
    assert "frontend_design" in hermes["matched_skill_ids"]
    assert "test_authoring" in hermes["matched_skill_ids"]
    assert "prompt_preview" in preflight


def test_preflight_prioritizes_frontend_agent_for_static_web_canvas_task(tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")

    preflight = store.build_task_preflight(
        description=(
            "Build a static web app with index.html, styles.css, app.js, "
            "canvas animation, responsive cards, and browser interactions."
        ),
        owner_agent="auto",
        allowed_subtask_agents=["hermes", "minimax", "claude"],
        task_types=["functional"],
    )

    assert preflight["recommended_agent_ids"][0] == "hermes"
    hermes = next(item for item in preflight["agent_summaries"] if item["agent_id"] == "hermes")
    assert "frontend_design" in hermes["matched_skill_ids"]
    assert "interaction_design" in hermes["matched_skill_ids"]


def test_agent_capabilities_api_round_trip(monkeypatch, tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")

    class FakeNativeSkillManager:
        def list_all_agent_skills(self):
            return {
                "openclaw": {
                    "agent_id": "openclaw",
                    "skills": [
                        {"id": "filesystem-review", "status": "enabled", "availability": "available"},
                        {"id": "apple-notes", "status": "unavailable", "availability": "unavailable"},
                    ],
                },
                "hermes": {"agent_id": "hermes", "skills": []},
                "claude": {"agent_id": "claude", "skills": []},
            }

    monkeypatch.setattr(
        "across_agents_assistant.api_server.get_agent_capability_store",
        lambda: store,
    )
    monkeypatch.setattr(
        "across_agents_assistant.api_server.get_native_skill_manager",
        lambda: FakeNativeSkillManager(),
    )
    monkeypatch.setattr(
        "across_agents_assistant.api_server._runtime_tool_schemas",
        lambda: [
            {
                "name": "read_file",
                "description": "Read a local text file.",
                "risk_level": "low",
            }
        ],
    )

    client = TestClient(app)
    response = client.put(
        "/api/agent-capabilities/openclaw",
        json={
            "enabled_skill_ids": ["macos_automation"],
            "enabled_plugin_ids": ["filesystem"],
            "enabled_tool_names": ["read_file"],
            "custom_instructions": "Use Finder context before file operations.",
            "strict_tool_scope": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["agent_id"] == "openclaw"
    assert body["profile"]["enabled_plugin_ids"] == ["filesystem"]

    response = client.get("/api/agent-capabilities?refresh=true")
    assert response.status_code == 200
    body = response.json()
    assert body["profiles"]["openclaw"]["enabled_tool_names"] == ["read_file"]
    assert body["available_tools"][0]["name"] == "read_file"
    assert body["agent_cards"][0]["agent_id"] == "openclaw"
    assert "tool_risk_summary" in body["agent_cards"][0]
    assert body["agent_cards"][0]["native_skill_health"] == {
        "available": 1,
        "unavailable": 1,
        "total": 2,
    }
    assert "Unavailable native skills need repair before routing." in body["agent_cards"][0]["warnings"]


def test_agent_capabilities_refresh_persists_native_skill_snapshot(monkeypatch, tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")
    calls = {"count": 0}

    class FakeNativeSkillManager:
        def list_all_agent_skills(self):
            calls["count"] += 1
            return {
                "openclaw": {
                    "agent_id": "openclaw",
                    "skills": [
                        {"id": "filesystem-review", "status": "enabled", "availability": "available"},
                        {"id": "apple-notes", "status": "unavailable", "availability": "unavailable"},
                    ],
                },
                "hermes": {"agent_id": "hermes", "skills": []},
                "claude": {"agent_id": "claude", "skills": []},
            }

    monkeypatch.setattr(
        "across_agents_assistant.api_server.get_agent_capability_store",
        lambda: store,
    )
    monkeypatch.setattr(
        "across_agents_assistant.api_server.get_native_skill_manager",
        lambda: FakeNativeSkillManager(),
    )
    monkeypatch.setattr(
        "across_agents_assistant.api_server._runtime_tool_schemas",
        lambda: [],
    )

    client = TestClient(app)

    response = client.get("/api/agent-capabilities")
    assert response.status_code == 200
    assert calls["count"] == 0
    assert response.json()["agent_cards"][0]["native_skill_health"] == {
        "available": 0,
        "unavailable": 0,
        "total": 0,
    }

    response = client.get("/api/agent-capabilities?refresh=true")
    assert response.status_code == 200
    assert calls["count"] == 1
    assert response.json()["agent_cards"][0]["native_skill_health"] == {
        "available": 1,
        "unavailable": 1,
        "total": 2,
    }

    response = client.get("/api/agent-capabilities")
    assert response.status_code == 200
    assert calls["count"] == 1
    assert response.json()["agent_cards"][0]["native_skill_health"] == {
        "available": 1,
        "unavailable": 1,
        "total": 2,
    }


def test_native_skills_api_refresh_persists_snapshot(monkeypatch, tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")
    calls = {"count": 0}

    class FakeNativeSkillManager:
        def list_all_agent_skills(self):
            calls["count"] += 1
            return {
                "hermes": {
                    "agent_id": "hermes",
                    "display_name": "Hermes",
                    "mode": "cli",
                    "supports_create": False,
                    "supports_install": True,
                    "supports_uninstall": True,
                    "supports_update": True,
                    "supports_check": True,
                    "skills": [{"id": "dogfood", "name": "dogfood", "status": "builtin"}],
                }
            }

    monkeypatch.setattr(
        "across_agents_assistant.api_server.get_agent_capability_store",
        lambda: store,
    )
    monkeypatch.setattr(
        "across_agents_assistant.api_server.get_native_skill_manager",
        lambda: FakeNativeSkillManager(),
    )

    client = TestClient(app)

    response = client.get("/api/native-skills")
    assert response.status_code == 200
    assert response.json()["agents"] == {}
    assert calls["count"] == 0

    response = client.get("/api/native-skills?refresh=true")
    assert response.status_code == 200
    assert response.json()["agents"]["hermes"]["skills"][0]["id"] == "dogfood"
    assert calls["count"] == 1

    response = client.get("/api/native-skills")
    assert response.status_code == 200
    assert response.json()["agents"]["hermes"]["skills"][0]["id"] == "dogfood"
    assert calls["count"] == 1


def test_agent_capabilities_api_custom_skill_and_preflight(monkeypatch, tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")
    monkeypatch.setattr(
        "across_agents_assistant.api_server.get_agent_capability_store",
        lambda: store,
    )
    monkeypatch.setattr(
        "across_agents_assistant.api_server._runtime_tool_schemas",
        lambda: [],
    )

    client = TestClient(app)
    response = client.post(
        "/api/agent-capabilities/skills",
        json={
            "id": "custom_accessibility_review",
            "name": "Accessibility review",
            "description": "Review keyboard and contrast behavior.",
            "prompt_hint": "Keep accessibility checks in the acceptance criteria.",
            "tags": ["frontend", "accessibility"],
        },
    )
    assert response.status_code == 200
    assert response.json()["skill"]["id"] == "custom_accessibility_review"

    response = client.put(
        "/api/agent-capabilities/hermes",
        json={"enabled_skill_ids": ["frontend_design", "custom_accessibility_review"]},
    )
    assert response.status_code == 200

    response = client.post(
        "/api/agent-capabilities/preflight",
        json={
            "description": "Improve accessibility for the dashboard UI.",
            "owner_agent": "auto",
            "allowed_subtask_agents": ["hermes", "deepseek"],
            "task_types": ["functional"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["recommended_agent_ids"][0] == "hermes"
    assert "custom_accessibility_review" in body["agent_summaries"][0]["matched_skill_ids"]

    response = client.delete("/api/agent-capabilities/skills/custom_accessibility_review")
    assert response.status_code == 200
    assert "custom_accessibility_review" not in store.get_profile("hermes")["enabled_skill_ids"]


def test_preflight_marks_matching_unavailable_native_skills_as_repairable(monkeypatch, tmp_path):
    from across_agents_assistant.native_agent_skills import NativeSkillManager

    class RecordingRunner:
        def __init__(self):
            self.commands = []

        def run(self, command, *, timeout=20):
            self.commands.append(list(command))
            if command == ["openclaw", "skills", "list", "--json"]:
                return (
                    '{"skills": ['
                    '{"id":"apple-notes","name":"Apple Notes","description":"Export selected Apple Notes"},'
                    '{"id":"window-capture","name":"Window Capture","description":"Capture macOS windows"}'
                    ']}'
                )
            if command == ["openclaw", "skills", "check"]:
                return (
                    "Skills Status Check\n\n"
                    "Ready to use:\n"
                    "  window-capture\n\n"
                    "Missing requirements:\n"
                    "  apple-notes (bins: memo; env: NOTES_TOKEN)\n"
                )
            return ""

    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")
    store.save_profile("hermes", {"enabled_skill_ids": []})
    store.save_profile("openclaw", {"enabled_skill_ids": []})
    manager = NativeSkillManager(command_runner=RecordingRunner())
    monkeypatch.setattr(
        "across_agents_assistant.api_server.get_agent_capability_store",
        lambda: store,
    )
    monkeypatch.setattr(
        "across_agents_assistant.api_server.get_native_skill_manager",
        lambda: manager,
    )

    client = TestClient(app)
    response = client.post(
        "/api/agent-capabilities/preflight",
        json={
            "description": "Export selected Apple Notes into markdown.",
            "owner_agent": "auto",
            "allowed_subtask_agents": ["hermes", "openclaw"],
            "task_types": ["functional"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    openclaw = next(item for item in body["agent_summaries"] if item["agent_id"] == "openclaw")
    assert openclaw["score"] == 0
    assert openclaw["matched_native_skill_ids"] == []
    assert openclaw["unavailable_native_skill_ids"] == ["apple-notes"]
    assert openclaw["routing_evidence"][0]["status"] == "unavailable"
    assert openclaw["routing_evidence"][0]["skill_id"] == "apple-notes"
    assert openclaw["native_skill_repair_suggestions"] == [
        "Install required binary `memo` and make it available on PATH.",
        "Set environment variable `NOTES_TOKEN` for the agent runtime.",
    ]
    assert "openclaw native skill Apple Notes is unavailable" in " ".join(openclaw["warnings"])
    assert "openclaw native skill Apple Notes is unavailable" in " ".join(body["warnings"])


def test_preflight_scores_available_native_skill_match(tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")
    store.save_profile("hermes", {"enabled_skill_ids": []})
    store.save_profile("openclaw", {"enabled_skill_ids": []})

    preflight = store.build_task_preflight(
        description="Export selected Apple Notes into markdown.",
        owner_agent="auto",
        allowed_subtask_agents=["hermes", "openclaw"],
        task_types=["functional"],
        native_skills_by_agent={
            "openclaw": [
                {
                    "id": "apple-notes",
                    "name": "Apple Notes",
                    "description": "Export selected Apple Notes into markdown.",
                    "status": "enabled",
                    "availability": "available",
                }
            ]
        },
    )

    openclaw = next(item for item in preflight["agent_summaries"] if item["agent_id"] == "openclaw")
    assert preflight["recommended_agent_ids"][0] == "openclaw"
    assert openclaw["matched_native_skill_ids"] == ["apple-notes"]
    assert openclaw["score"] == 4
    assert openclaw["routing_evidence"][0]["source"] == "native_skill"
    assert openclaw["routing_evidence"][0]["status"] == "available"
    assert openclaw["routing_evidence"][0]["skill_id"] == "apple-notes"


def test_preflight_does_not_match_native_skills_on_generic_file_words(tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")
    store.save_profile("openclaw", {"enabled_skill_ids": []})

    preflight = store.build_task_preflight(
        description=(
            "Create exactly these files: index.html, styles.css, app.js, README.md. "
            "The app should show quality gates and route evidence."
        ),
        owner_agent="auto",
        allowed_subtask_agents=["openclaw"],
        task_types=["functional"],
        native_skills_by_agent={
            "openclaw": [
                {
                    "id": "video-frames",
                    "name": "Video Frames",
                    "description": "Extract frames from local video files.",
                    "status": "enabled",
                    "availability": "available",
                }
            ]
        },
    )

    openclaw = preflight["agent_summaries"][0]
    assert openclaw["matched_native_skill_ids"] == []
    assert openclaw["score"] == 0


def test_preflight_does_not_match_native_skill_in_negative_mock_context(tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")
    store.save_profile("hermes", {"enabled_skill_ids": []})

    preflight = store.build_task_preflight(
        description=(
            "Build an Apple Notes integration mock panel only. "
            "It must not create, edit, delete, export, or touch real Apple Notes data."
        ),
        owner_agent="auto",
        allowed_subtask_agents=["hermes"],
        task_types=["functional"],
        native_skills_by_agent={
            "hermes": [
                {
                    "id": "apple-notes",
                    "name": "Apple Notes",
                    "description": "Create, edit, delete, search, or export Apple Notes.",
                    "status": "enabled",
                    "availability": "available",
                }
            ]
        },
    )

    hermes = preflight["agent_summaries"][0]
    assert hermes["matched_native_skill_ids"] == []
    assert hermes["score"] == 0


def test_preflight_does_not_match_native_skill_on_vendor_name_only(tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")
    store.save_profile("hermes", {"enabled_skill_ids": []})

    preflight = store.build_task_preflight(
        description="Show mock repair advice for an unavailable Apple Notes native skill.",
        owner_agent="auto",
        allowed_subtask_agents=["hermes"],
        task_types=["functional"],
        native_skills_by_agent={
            "hermes": [
                {
                    "id": "apple-reminders",
                    "name": "Apple Reminders",
                    "description": "Create and manage Apple Reminders.",
                    "status": "enabled",
                    "availability": "available",
                }
            ]
        },
    )

    hermes = preflight["agent_summaries"][0]
    assert hermes["matched_native_skill_ids"] == []
    assert hermes["score"] == 0


def test_preflight_does_not_match_native_skills_from_agent_names_only(tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")
    store.save_profile("openclaw", {"enabled_skill_ids": []})

    preflight = store.build_task_preflight(
        description=(
            "Visualize cross-agent routing across OpenClaw, Hermes, Claude Code, "
            "DeepSeek, and MiniMax in a static web page."
        ),
        owner_agent="auto",
        allowed_subtask_agents=["openclaw"],
        task_types=["functional"],
        native_skills_by_agent={
            "openclaw": [
                {
                    "id": "minimax-multimodal-toolkit",
                    "name": "MiniMax Multimodal Toolkit",
                    "description": "Use MiniMax media generation tools.",
                    "status": "enabled",
                    "availability": "available",
                },
                {
                    "id": "page-agent",
                    "name": "Page Agent",
                    "description": "Automate and inspect browser pages.",
                    "status": "enabled",
                    "availability": "available",
                },
            ]
        },
    )

    openclaw = preflight["agent_summaries"][0]
    assert openclaw["matched_native_skill_ids"] == []
    assert openclaw["score"] == 0


def test_store_builds_standard_agent_cards_with_tool_and_native_skill_health(tmp_path):
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")
    store.save_profile(
        "openclaw",
        {
            "enabled_skill_ids": ["general_execution"],
            "enabled_tool_names": ["filesystem__write_file", "read_file"],
            "strict_tool_scope": True,
        },
    )

    cards = store.build_agent_cards(
        tool_schemas=[
            {"name": "filesystem__write_file", "risk_level": "high", "source": "mcp"},
            {"name": "read_file", "risk_level": "low", "source": "local"},
        ],
        native_skills_by_agent={
            "openclaw": [
                {"id": "apple-notes", "status": "enabled", "availability": "available"},
                {"id": "browser-qa", "status": "unavailable", "availability": "unavailable"},
            ]
        },
    )

    openclaw = next(card for card in cards if card["agent_id"] == "openclaw")
    assert openclaw["display_name"] == "OpenClaw"
    assert openclaw["agent_type"] == "local"
    assert openclaw["native_skill_health"] == {
        "available": 1,
        "unavailable": 1,
        "total": 2,
    }
    assert openclaw["tool_risk_summary"] == {"high": 1, "low": 1, "medium": 0, "unknown": 0}
    assert "High-risk tools require explicit approval." in openclaw["warnings"]


def test_auto_task_uses_external_orchestrator_plugin_boundary(monkeypatch, tmp_path):
    captured = {}
    store = AgentCapabilityStore(tmp_path / "agent-capabilities.json")
    store.save_profile("hermes", {"enabled_skill_ids": ["frontend_design"]})
    store.save_profile("deepseek", {"enabled_skill_ids": ["backend_api"]})

    class FakePlugin:
        def implementation_status(self, probe=True):
            return {
                "mode": "external",
                "implementation": "external",
                "available": True,
                "transport": "cli",
                "connection_note": "fake external runtime",
            }

        def submit_task(self, *, goal, project_dir, deliverables=None, agent=None, subtasks=None, strict_dependency=False, task_types=None):
            captured["goal"] = goal
            captured["project_dir"] = project_dir
            captured["deliverables"] = deliverables
            captured["agent"] = agent
            captured["subtasks"] = subtasks
            captured["strict_dependency"] = strict_dependency
            captured["task_types"] = task_types
            return {"task_id": "task-capabilities", "status": "pending"}

    monkeypatch.setattr(
        "across_agents_assistant.api_server._check_llm_provider_readiness",
        lambda: [],
    )
    monkeypatch.setattr(
        "across_agents_assistant.api_server.get_task_orchestrator",
        lambda: (_ for _ in ()).throw(AssertionError("internal orchestrator must not be used")),
    )
    monkeypatch.setattr(
        "across_agents_assistant.api_server.get_agent_capability_store",
        lambda: store,
    )
    monkeypatch.setattr(
        "across_agents_assistant.api_server.get_orchestrator_plugin_manager",
        lambda: FakePlugin(),
    )

    client = TestClient(app)
    response = client.post(
        "/api/tasks/auto",
        json={
            "description": "Build a polished dashboard",
            "task_types": ["functional"],
            "owner_agent": "hermes",
            "allowed_subtask_agents": ["deepseek"],
            "project_dir": str(tmp_path / "project"),
        },
    )

    assert response.status_code == 200
    assert response.json()["implementation"] == "external"
    assert response.json()["external_task"] is True
    assert captured == {
        "goal": "Build a polished dashboard",
        "project_dir": str(tmp_path / "project"),
        "deliverables": ["README.md"],
        "agent": "hermes",
        "subtasks": [],
        "strict_dependency": True,
        "task_types": ["functional"],
    }
