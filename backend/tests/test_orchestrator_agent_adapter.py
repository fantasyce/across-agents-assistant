import json
import threading
from types import SimpleNamespace

import pytest

from across_agents_assistant import orchestrator_agent_adapter as adapter


@pytest.mark.parametrize(
    "output",
    [
        "logger write failed while opening the runtime log",
        "Internal error: host command could not continue",
        "EPERM: operation not permitted, mkdir '/runtime/state'",
        "抱歉，大脑没有返回任何内容",
    ],
)
def test_kimi_exit_zero_with_internal_failure_output_returns_failure(
    monkeypatch, capsys, output
):
    class FakeBridge:
        def invoke(self, *_args, **_kwargs):
            return SimpleNamespace(
                is_success=True,
                output=output,
                error=None,
                metadata={},
            )

    monkeypatch.setattr(adapter, "build_agent_bridge", lambda: FakeBridge())
    monkeypatch.setenv("ACROSS_TASK_JSON", '{"project_root":"/tmp/project","task_id":"task-1"}')
    monkeypatch.setenv("ACROSS_SUBTASK_JSON", '{"subtask_id":"subtask-1","path":"README.md"}')

    assert adapter.main(["--agent", "kimi"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Kimi host agent reported an internal runtime failure\n"
    assert output not in captured.err


def test_non_kimi_output_is_not_reclassified(monkeypatch, capsys):
    class FakeBridge:
        def invoke(self, *_args, **_kwargs):
            return SimpleNamespace(
                is_success=True,
                output="Internal error appears in the requested documentation",
                error=None,
                metadata={},
            )

    monkeypatch.setattr(adapter, "build_agent_bridge", lambda: FakeBridge())
    monkeypatch.setenv("ACROSS_TASK_JSON", '{"project_root":"/tmp/project","task_id":"task-1"}')
    monkeypatch.setenv("ACROSS_SUBTASK_JSON", '{"subtask_id":"subtask-1","path":"README.md"}')

    assert adapter.main(["--agent", "claude"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert '"output": "Internal error appears in the requested documentation"' in captured.out


def test_kimi_emits_sanitized_heartbeat_then_final_result(monkeypatch, capsys):
    release = threading.Event()

    class FakeBridge:
        def invoke(self, *_args, **_kwargs):
            assert release.wait(timeout=1)
            return SimpleNamespace(
                is_success=True,
                output="completed",
                error=None,
                metadata={"result": "ok"},
            )

    monkeypatch.setattr(adapter, "build_agent_bridge", lambda: FakeBridge())
    monkeypatch.setattr(adapter, "_KIMI_HEARTBEAT_INTERVAL_SECONDS", 0.01)
    monkeypatch.setenv(
        "ACROSS_TASK_JSON",
        '{"project_root":"/tmp/secret-project","task_id":"secret-task"}',
    )
    monkeypatch.setenv(
        "ACROSS_SUBTASK_JSON",
        '{"subtask_id":"secret-subtask","path":"private.txt"}',
    )
    threading.Timer(0.04, release.set).start()

    assert adapter.main(["--agent", "kimi", "--timeout", "1200"]) == 0
    captured = capsys.readouterr()
    lines = [json.loads(line) for line in captured.out.splitlines()]

    assert captured.err == ""
    assert len(lines) >= 2
    assert all(
        line == {"type": "heartbeat", "agent": "kimi", "status": "running"}
        for line in lines[:-1]
    )
    assert lines[-1]["output"] == "completed"
    heartbeat_output = "\n".join(captured.out.splitlines()[:-1])
    assert "secret-task" not in heartbeat_output
    assert "secret-subtask" not in heartbeat_output
    assert "secret-project" not in heartbeat_output
    assert "private.txt" not in heartbeat_output


def test_kimi_bridge_exception_returns_sanitized_failure(monkeypatch, capsys):
    class FakeBridge:
        def invoke(self, *_args, **_kwargs):
            raise RuntimeError("token=super-secret")

    monkeypatch.setattr(adapter, "build_agent_bridge", lambda: FakeBridge())
    monkeypatch.setenv("ACROSS_TASK_JSON", '{"project_root":"/tmp/project"}')
    monkeypatch.setenv("ACROSS_SUBTASK_JSON", '{"path":"README.md"}')

    assert adapter.main(["--agent", "kimi"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Kimi host agent adapter failed\n"
    assert "super-secret" not in captured.err
