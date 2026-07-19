import asyncio
import io
import subprocess
import sys

from across_agents_assistant import api_server
from across_agents_assistant import autopilot_code_iteration_cli
from across_agents_assistant.local_agent.client import UniversalAgentClient


def test_code_iteration_cli_emits_heartbeat_while_awaiting_model(monkeypatch):
    async def fake_create_code_iteration(_req):
        await asyncio.sleep(0.04)
        return {
            "schema_version": "across-host-code-iteration/1.0",
            "status": "passed",
            "patches": [],
        }

    monkeypatch.setattr(api_server, "create_autopilot_code_iteration", fake_create_code_iteration)
    monkeypatch.setenv("ACROSS_AAA_HOST_CLI_HEARTBEAT_SECONDS", "0.01")
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr)

    result = asyncio.run(autopilot_code_iteration_cli._run({
        "goal": "Exercise progress logging.",
        "candidate_workspace": "/tmp/candidate",
        "model_policy": {
            "provider": "local-agent",
            "agent_id": "codex",
            "model": "gpt-5.3-codex-spark",
        },
    }))

    assert result["status"] == "passed"
    progress = stderr.getvalue()
    assert "code_iteration.start" in progress
    assert "code_iteration.heartbeat" in progress
    assert "heartbeat_kind" in progress
    assert "code_iteration.model_call" in progress
    assert "code_iteration.complete" in progress


def test_local_agent_activity_progress_omits_output_text(monkeypatch):
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setenv("ACROSS_AAA_HOST_CLI_PROGRESS_LOG_FILE", "autopilot-code-iteration.jsonl")
    monkeypatch.setenv("ACROSS_AAA_HOST_CLI_PROGRESS_RUN_ID", "run-progress")
    monkeypatch.setenv("ACROSS_AAA_HOST_CLI_PROGRESS_CANDIDATE_ID", "candidate-progress")
    monkeypatch.setenv("ACROSS_AAA_HOST_CLI_PROGRESS_PHASE", "code_iteration.model_call")

    process = subprocess.Popen(
        [sys.executable, "-c", "import sys; print('SECRET_OUTPUT'); print('ERR_OUTPUT', file=sys.stderr)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout, process_stderr, timeout_kind, _timeout_seconds = UniversalAgentClient._communicate_with_activity_timeout(
        process,
        max_wall_timeout=5,
        idle_timeout=5,
    )

    assert timeout_kind is None
    assert "SECRET_OUTPUT" in stdout
    assert "ERR_OUTPUT" in process_stderr

    progress = stderr.getvalue()
    assert "local_agent.activity" in progress
    assert "code_iteration.model_call" in progress
    assert "\"stream\": \"stdout\"" in progress
    assert "\"stream\": \"stderr\"" in progress
    assert "SECRET_OUTPUT" not in progress
    assert "ERR_OUTPUT" not in progress


def test_local_agent_activity_refreshes_wall_timeout():
    process = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-c",
            (
                "import sys, time\n"
                "for i in range(6):\n"
                "    print(f'heartbeat {i}', file=sys.stderr, flush=True)\n"
                "    time.sleep(0.25)\n"
                "print('DONE', flush=True)\n"
            ),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )

    stdout, process_stderr, timeout_kind, _timeout_seconds = UniversalAgentClient._communicate_with_activity_timeout(
        process,
        max_wall_timeout=0.8,
        idle_timeout=1.2,
    )

    assert timeout_kind is None
    assert "DONE" in stdout
    assert "heartbeat 5" in process_stderr
