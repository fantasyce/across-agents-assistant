import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
import requests

os.environ.setdefault("ACROSS_AGENTS_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))


def test_app_api_connects_across_context_and_exposes_memory_tools(tmp_path, monkeypatch):
    if not shutil.which("across-context"):
        pytest.skip("across-context CLI is not installed on PATH")

    backend_root = Path(__file__).resolve().parents[2]
    context_home = tmp_path / "across-context-home"
    app_home = tmp_path / "across-agents-home"
    monkeypatch.setenv("ACROSS_CONTEXT_HOME", str(context_home))
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(backend_root / "src"),
            "ACROSS_AGENTS_HOME": str(app_home),
            "ACROSS_AGENTS_DB_PATH": str(app_home / "assistant.db"),
            "ACROSS_CONTEXT_HOME": str(context_home),
        }
    )

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "across_agents_assistant.api_server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=backend_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        _wait_for_health(base_url, process)

        response = requests.post(
            f"{base_url}/api/mcp/connect",
            json={
                "server_id": "across_context",
                "command": "across-context",
                "args": ["mcp"],
                "env": {"ACROSS_CONTEXT_HOME": str(context_home)},
                "readonly": False,
            },
            timeout=10,
        )
        assert response.status_code == 200, response.text

        tools_response = requests.get(f"{base_url}/api/tools", timeout=10)
        assert tools_response.status_code == 200, tools_response.text
        tools = tools_response.json()
        tools_by_name = {tool["name"]: tool for tool in tools}

        assert "across_context__search_context" in tools_by_name
        assert tools_by_name["across_context__search_context"]["risk_level"] == "medium"
        assert tools_by_name["across_context__remember_context"]["risk_level"] == "high"
        assert tools_by_name["across_context__approve_memory"]["risk_level"] == "high"
    finally:
        try:
            requests.post(
                f"{base_url}/api/mcp/disconnect",
                json={"server_id": "across_context"},
                timeout=5,
            )
        except Exception:
            pass
        process.terminate()
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_health(base_url, process):
    deadline = time.time() + 15
    last_error = None
    while time.time() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            raise AssertionError(f"uvicorn exited early\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")
        try:
            response = requests.get(f"{base_url}/api/health", timeout=1)
            if response.status_code == 200:
                return
        except Exception as exc:
            last_error = exc
        time.sleep(0.2)
    raise AssertionError(f"uvicorn did not become healthy: {last_error}")
