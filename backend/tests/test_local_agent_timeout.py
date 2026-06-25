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
        observed["stdin"] = kwargs.get("stdin")
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
    assert "--ask-for-approval" not in observed["args"]
    assert "--cd" in observed["args"]
    assert str(tmp_path) in observed["args"]
    assert observed["stdin"] is client_mod.subprocess.DEVNULL


def test_universal_agent_client_passes_configured_model_to_opencode(monkeypatch, tmp_path):
    observed = {}

    from across_agents_assistant import local_agent_health
    from across_agents_assistant.local_agent import client as client_mod

    class OpenCodeManager:
        def get_active_agent(self):
            return "opencode"

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
        lambda agent_id: "/usr/local/bin/opencode",
    )
    monkeypatch.setattr(
        local_agent_health,
        "get_configured_agent_model",
        lambda agent_id: "anthropic/claude-sonnet-4-5",
    )

    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return ("opencode completed", "")

    def fake_popen(args, **kwargs):
        observed["args"] = args
        observed["cwd"] = kwargs.get("cwd")
        return FakeProcess()

    monkeypatch.setattr(client_mod.subprocess, "Popen", fake_popen)

    client = UniversalAgentClient(OpenCodeManager())
    reply = client.send(
        "repair the delivery",
        target_agent="opencode",
        project_dir=str(tmp_path),
        timeout=23.0,
    )

    assert reply.text == "opencode completed"
    assert observed["args"][:4] == ["/usr/local/bin/opencode", "run", "--model", "anthropic/claude-sonnet-4-5"]
    assert observed["cwd"] == str(tmp_path)


def test_universal_agent_client_runs_claude_code_desktop_as_claude_family(monkeypatch, tmp_path):
    observed = {}

    from across_agents_assistant import local_agent_health
    from across_agents_assistant.local_agent import client as client_mod

    class ClaudeCodeDesktopManager:
        def get_active_agent(self):
            return "claude-desktop"

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
        lambda agent_id: "/usr/local/bin/claude",
    )
    monkeypatch.setattr(
        local_agent_health,
        "get_configured_agent_model",
        lambda agent_id: "sonnet",
    )

    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return ('{"result":"claude code completed","session_id":"claude-session"}', "")

    def fake_popen(args, **kwargs):
        observed["args"] = args
        observed["cwd"] = kwargs.get("cwd")
        observed["stdin"] = kwargs.get("stdin")
        return FakeProcess()

    monkeypatch.setattr(client_mod.subprocess, "Popen", fake_popen)

    client = UniversalAgentClient(ClaudeCodeDesktopManager())
    reply = client.send(
        "repair the delivery",
        target_agent="claude-desktop",
        session_id="app-session",
        project_dir=str(tmp_path),
        timeout=23.0,
    )

    assert reply.text == "claude code completed"
    assert observed["args"] == [
        "/usr/local/bin/claude",
        "--model",
        "sonnet",
        "-p",
        "--permission-mode",
        "acceptEdits",
        "--output-format",
        "json",
        "repair the delivery",
    ]
    assert observed["cwd"] == str(tmp_path)
    assert observed["stdin"] is client_mod.subprocess.DEVNULL
    assert client.claude_sessions["app-session"] == "claude-session"


def test_universal_agent_client_leaves_cursor_auto_model_to_cli(monkeypatch, tmp_path):
    observed = {}

    from across_agents_assistant import local_agent_health
    from across_agents_assistant.local_agent import client as client_mod

    class CursorManager:
        def get_active_agent(self):
            return "cursor"

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
        lambda agent_id: "/usr/local/bin/cursor-agent",
    )
    monkeypatch.setattr(
        local_agent_health,
        "get_configured_agent_model",
        lambda agent_id: "auto",
    )

    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return ("cursor completed", "")

    def fake_popen(args, **kwargs):
        observed["args"] = args
        observed["cwd"] = kwargs.get("cwd")
        return FakeProcess()

    monkeypatch.setattr(client_mod.subprocess, "Popen", fake_popen)

    client = UniversalAgentClient(CursorManager())
    reply = client.send(
        "repair the delivery",
        target_agent="cursor",
        project_dir=str(tmp_path),
        timeout=23.0,
    )

    assert reply.text == "cursor completed"
    assert observed["args"] == ["/usr/local/bin/cursor-agent", "-p", "repair the delivery"]
    assert observed["cwd"] == str(tmp_path)
