from types import SimpleNamespace

from across_agents_assistant.agent_bridge.agent import AgentSession
from across_agents_assistant.local_agent.client import UniversalAgentClient


class _FakeManager:
    def get_active_agent(self):
        return "hermes"

    def get_agent_config(self, agent_id):
        return {
            "args_template": ["{message}"],
            "output_format": "raw",
        }


def test_agent_session_forwards_timeout_to_local_client():
    observed = {}

    class FakeClient:
        def send(self, **kwargs):
            observed.update(kwargs)
            return SimpleNamespace(text="done")

    session = AgentSession("hermes", FakeClient())

    response = session.invoke(
        "repair the delivery",
        timeout=37.0,
        project_dir="/tmp/project",
    )

    assert response.is_success is True
    assert observed["timeout"] == 37.0


def test_universal_agent_client_uses_call_timeout_for_process(monkeypatch, tmp_path):
    observed = {}

    from across_agents_assistant import local_agent_health
    from across_agents_assistant.local_agent import client as client_mod

    monkeypatch.setattr(
        client_mod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=b"PATH=/usr/bin\0HOME=/tmp\0"),
    )
    monkeypatch.setattr(
        local_agent_health,
        "resolve_local_agent_executable",
        lambda agent_id: "/bin/echo",
    )

    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            observed["timeout"] = timeout
            return ("agent output", "")

        def kill(self):
            observed["killed"] = True

        def wait(self):
            observed["waited"] = True

    monkeypatch.setattr(client_mod.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())

    client = UniversalAgentClient(_FakeManager())
    reply = client.send(
        "repair the delivery",
        target_agent="hermes",
        project_dir=str(tmp_path),
        timeout=23.0,
    )

    assert reply.text == "agent output"
    assert observed["timeout"] == 23.0


def test_universal_agent_client_passes_configured_model_to_codex(monkeypatch, tmp_path):
    observed = {}

    from across_agents_assistant import local_agent_health
    from across_agents_assistant.local_agent import client as client_mod

    class CodexManager:
        def get_active_agent(self):
            return "codex"

        def get_agent_config(self, agent_id):
            return {"output_format": "raw"}

    monkeypatch.setattr(
        client_mod.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=b"PATH=/usr/bin\0HOME=/tmp\0"),
    )
    monkeypatch.setattr(
        local_agent_health,
        "resolve_local_agent_executable",
        lambda agent_id: "/usr/local/bin/codex",
    )
    monkeypatch.setattr(
        local_agent_health,
        "get_configured_agent_model",
        lambda agent_id: "gpt-5-codex",
    )

    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return ("codex completed", "")

    def fake_popen(args, **kwargs):
        observed["args"] = args
        observed["cwd"] = kwargs.get("cwd")
        return FakeProcess()

    monkeypatch.setattr(client_mod.subprocess, "Popen", fake_popen)

    client = UniversalAgentClient(CodexManager())
    reply = client.send(
        "repair the delivery",
        target_agent="codex",
        project_dir=str(tmp_path),
        timeout=23.0,
    )

    assert reply.text == "codex completed"
    assert observed["args"][:4] == ["/usr/local/bin/codex", "exec", "--model", "gpt-5-codex"]
    assert "--cd" in observed["args"]
    assert str(tmp_path) in observed["args"]
