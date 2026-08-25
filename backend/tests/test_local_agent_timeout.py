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
        lambda agent_id: "gpt-5.3-codex-spark",
    )
    monkeypatch.setattr(local_agent_health, "codex_model_is_available", lambda model: True)

    class FakeProcess:
        returncode = 0

    def fake_popen(args, **kwargs):
        observed["args"] = args
        observed["cwd"] = kwargs.get("cwd")
        observed["stdin"] = kwargs.get("stdin")
        observed["start_new_session"] = kwargs.get("start_new_session")
        return FakeProcess()

    monkeypatch.setattr(client_mod.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        client_mod.UniversalAgentClient,
        "_communicate_with_activity_timeout",
        staticmethod(lambda process, *, max_wall_timeout, idle_timeout: (
            '{"type":"item.completed","item":{"type":"agent_message","text":"codex completed"}}\n',
            "",
            None,
            None,
        )),
    )

    client = UniversalAgentClient(CodexManager())
    reply = client.send(
        "repair the delivery",
        target_agent="codex",
        project_dir=str(tmp_path),
        timeout=23.0,
    )

    assert reply.text == "codex completed"
    assert observed["args"][:5] == ["/usr/local/bin/codex", "exec", "--json", "--model", "gpt-5.3-codex-spark"]
    assert "--ask-for-approval" not in observed["args"]
    assert "--cd" in observed["args"]
    assert str(tmp_path) in observed["args"]
    assert observed["stdin"] is client_mod.subprocess.DEVNULL
    assert observed["start_new_session"] is True


def test_universal_agent_client_configures_task_scoped_codex_mcp_proxy(monkeypatch, tmp_path):
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
    monkeypatch.setattr(local_agent_health, "resolve_local_agent_executable", lambda agent_id: "/usr/local/bin/codex")
    monkeypatch.setattr(local_agent_health, "get_configured_agent_model", lambda agent_id: "")

    class FakeProcess:
        returncode = 0

    def fake_popen(args, **kwargs):
        observed["args"] = args
        return FakeProcess()

    monkeypatch.setattr(client_mod.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        client_mod.UniversalAgentClient,
        "_communicate_with_activity_timeout",
        staticmethod(lambda process, *, max_wall_timeout, idle_timeout: (
            '{"type":"item.completed","item":{"type":"agent_message","text":"done"}}\n',
            "",
            None,
            None,
        )),
    )

    client = UniversalAgentClient(CodexManager())
    reply = client.send(
        "verify runtime",
        target_agent="codex",
        project_dir=str(tmp_path),
        host_mcp_proxy_command=["/Applications/AAA/backend", "host-mcp-proxy"],
        read_only=True,
    )

    assert reply.text == "done"
    args = observed["args"]
    assert 'mcp_servers.aaa_host.command="/Applications/AAA/backend"' in args
    assert 'mcp_servers.aaa_host.args=["host-mcp-proxy"]' in args
    assert "--ignore-user-config" in args
    assert "--ignore-rules" in args
    assert "--ephemeral" in args
    assert args[args.index("--sandbox") + 1] == "read-only"


def test_readonly_codex_task_normalizes_unsafe_custom_args_template(monkeypatch, tmp_path):
    observed = {}

    from across_agents_assistant import local_agent_health
    from across_agents_assistant.local_agent import client as client_mod

    class CodexManager:
        def get_active_agent(self):
            return "codex"

        def get_agent_config(self, agent_id):
            return {
                "output_format": "raw",
                "args_template": [
                    "exec",
                    "--dangerously-bypass-approvals-and-sandbox",
                    "--dangerously-bypass-hook-trust",
                    "--sandbox",
                    "danger-full-access",
                    "-sdanger-full-access",
                    "{message}",
                ],
            }

    monkeypatch.setattr(client_mod.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=b"PATH=/usr/bin\0HOME=/tmp\0"))
    monkeypatch.setattr(local_agent_health, "resolve_local_agent_executable", lambda agent_id: "/usr/local/bin/codex")
    monkeypatch.setattr(local_agent_health, "get_configured_agent_model", lambda agent_id: "")

    class FakeProcess:
        returncode = 0

    def fake_popen(args, **kwargs):
        observed["args"] = args
        return FakeProcess()

    monkeypatch.setattr(client_mod.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        client_mod.UniversalAgentClient,
        "_communicate_with_activity_timeout",
        staticmethod(lambda process, *, max_wall_timeout, idle_timeout: (
            '{"type":"item.completed","item":{"type":"agent_message","text":"done"}}\n',
            "",
            None,
            None,
        )),
    )

    client = UniversalAgentClient(CodexManager())
    client.send(
        "verify runtime",
        target_agent="codex",
        project_dir=str(tmp_path),
        host_mcp_proxy_command=["/Applications/AAA/backend", "host-mcp-proxy"],
        read_only=True,
    )

    args = observed["args"]
    assert "--dangerously-bypass-approvals-and-sandbox" not in args
    assert "--dangerously-bypass-hook-trust" not in args
    assert "-sdanger-full-access" not in args
    assert "danger-full-access" not in args
    assert args.count("--sandbox") == 1
    assert args[args.index("--sandbox") + 1] == "read-only"


def test_universal_agent_client_terminates_process_group(monkeypatch):
    observed = {}

    from across_agents_assistant.local_agent import client as client_mod

    class FakeProcess:
        pid = 12345
        _polls = [None, None, 0]

        def poll(self):
            return self._polls.pop(0) if self._polls else 0

        def terminate(self):
            observed["terminated"] = True

        def kill(self):
            observed["killed"] = True

        def wait(self, timeout=None):
            observed.setdefault("waits", []).append(timeout)
            return 0

    monkeypatch.setattr(client_mod.os, "getpgid", lambda pid: 67890)
    monkeypatch.setattr(client_mod.os, "killpg", lambda pgid, sig: observed.setdefault("signals", []).append((pgid, sig)))

    client_mod.UniversalAgentClient._terminate_process_tree(FakeProcess())

    assert observed["signals"] == [(67890, client_mod.signal.SIGTERM)]
    assert observed["waits"] == [2.0]


def test_universal_agent_client_ignores_unavailable_configured_codex_model(monkeypatch, tmp_path):
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
    monkeypatch.setattr(local_agent_health, "codex_model_is_available", lambda model: False)

    class FakeProcess:
        returncode = 0

    def fake_popen(args, **kwargs):
        observed["args"] = args
        return FakeProcess()

    monkeypatch.setattr(client_mod.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        client_mod.UniversalAgentClient,
        "_communicate_with_activity_timeout",
        staticmethod(lambda process, *, max_wall_timeout, idle_timeout: (
            '{"type":"item.completed","item":{"type":"agent_message","text":"codex completed"}}\n',
            "",
            None,
            None,
        )),
    )

    client = UniversalAgentClient(CodexManager())
    reply = client.send(
        "repair the delivery",
        target_agent="codex",
        project_dir=str(tmp_path),
        timeout=23.0,
    )

    assert reply.text == "codex completed"
    assert observed["args"][:2] == ["/usr/local/bin/codex", "exec"]
    assert "--json" in observed["args"]
    assert "--model" not in observed["args"]


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


def test_universal_agent_client_passes_configured_model_to_kimi(monkeypatch, tmp_path):
    observed = {}

    from across_agents_assistant import local_agent_health
    from across_agents_assistant.local_agent import client as client_mod

    class KimiManager:
        def get_active_agent(self):
            return "kimi"

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
        lambda agent_id: "/usr/local/bin/kimi",
    )
    monkeypatch.setattr(
        local_agent_health,
        "get_configured_agent_model",
        lambda agent_id: "minimax/MiniMax-M3",
    )

    class FakeProcess:
        returncode = 0

        def communicate(self, timeout=None):
            return (
                '{"role":"assistant","content":"kimi completed"}\n'
                '{"role":"meta","type":"session.resume_hint","session_id":"kimi-session","content":"To resume this session"}\n',
                "",
            )

    def fake_popen(args, **kwargs):
        observed["args"] = args
        observed["cwd"] = kwargs.get("cwd")
        observed["stdin"] = kwargs.get("stdin")
        return FakeProcess()

    monkeypatch.setattr(client_mod.subprocess, "Popen", fake_popen)

    client = UniversalAgentClient(KimiManager())
    reply = client.send(
        "repair the delivery",
        target_agent="kimi",
        project_dir=str(tmp_path),
        timeout=23.0,
    )

    assert reply.text == "kimi completed"
    assert observed["args"] == [
        "/usr/local/bin/kimi",
        "--model",
        "minimax/MiniMax-M3",
        "-p",
        "repair the delivery",
        "--output-format",
        "stream-json",
    ]
    assert "resume" not in reply.text.lower()
    assert observed["cwd"] == str(tmp_path)
    assert observed["stdin"] is client_mod.subprocess.DEVNULL


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
