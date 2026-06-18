import json

from fastapi.testclient import TestClient

import across_agents_assistant.api_server as api_server
from across_agents_assistant.api_server import app


TRACEBACK_TEXT = (
    "Traceback (most recent call last):\n"
    '  File "/Users/example/private/app.py", line 7, in boom\n'
    "RuntimeError: private internal path"
)


def _encoded(response) -> str:
    try:
        return json.dumps(response.json())
    except Exception:
        return response.text


def assert_no_stack_trace(response) -> None:
    encoded = _encoded(response)
    assert "Traceback (most recent call last)" not in encoded
    assert 'File "/Users/example/private/app.py"' not in encoded
    assert "private internal path" not in encoded
    assert "See local backend logs for details" in encoded


def test_startup_diagnostics_endpoint_sanitizes_traceback_payload(monkeypatch):
    monkeypatch.setattr(
        api_server,
        "_build_startup_diagnostics",
        lambda: {
            "status": "blocked",
            "summary": {"status": "blocked"},
            "checks": [
                {
                    "id": "orchestrator_plugin",
                    "status": "failed",
                    "detail": TRACEBACK_TEXT,
                    "metadata": {"error": TRACEBACK_TEXT},
                }
            ],
            "runtime": {
                "orchestrator_plugin": {
                    "connection_note": TRACEBACK_TEXT,
                    "error": TRACEBACK_TEXT,
                }
            },
        },
    )

    response = TestClient(app).get("/api/diagnostics/startup")

    assert response.status_code == 200
    assert_no_stack_trace(response)


def test_orchestrator_plugin_status_endpoint_sanitizes_runtime_payload(monkeypatch):
    class FakeManager:
        def implementation_status(self, probe=True):
            return {
                "mode": "external",
                "implementation": "unknown",
                "available": False,
                "connection_note": TRACEBACK_TEXT,
                "error": TRACEBACK_TEXT,
                "install": self.install_status(),
            }

        def install_status(self):
            return {
                "status": "not_installed",
                "installable": True,
                "error": TRACEBACK_TEXT,
            }

    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakeManager())

    response = TestClient(app).get("/api/orchestrator/plugin")

    assert response.status_code == 200
    assert_no_stack_trace(response)


def test_orchestrator_plugin_install_endpoint_sanitizes_exception_payload(monkeypatch):
    class FakeManager:
        def install_plugin(self):
            raise RuntimeError(TRACEBACK_TEXT)

        def implementation_status(self, probe=True):
            return {
                "mode": "external",
                "implementation": "unknown",
                "available": False,
                "connection_note": TRACEBACK_TEXT,
                "error": TRACEBACK_TEXT,
            }

        def install_status(self):
            return {
                "status": "failed",
                "installable": True,
                "error": TRACEBACK_TEXT,
            }

    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakeManager())

    response = TestClient(app).post("/api/orchestrator/plugin/install")

    assert response.status_code == 500
    assert_no_stack_trace(response)


def test_release_verification_endpoint_sanitizes_report_payload(monkeypatch):
    monkeypatch.setattr(
        api_server,
        "_build_release_verification_report",
        lambda **_kwargs: {
            "status": "blocked",
            "startup": {"checks": [{"detail": TRACEBACK_TEXT}]},
            "release_evaluation": {"error": TRACEBACK_TEXT},
        },
    )

    response = TestClient(app).post("/api/release/verification")

    assert response.status_code == 200
    assert_no_stack_trace(response)


def test_external_task_stream_sanitizes_runtime_exception(monkeypatch):
    class FakePlugin:
        def get_task(self, task_id):
            raise RuntimeError(TRACEBACK_TEXT)

    monkeypatch.setattr(api_server, "_is_external_orchestrator_task", lambda task_id: True)
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakePlugin())

    response = TestClient(app).get("/api/tasks/external-demo/stream")

    assert response.status_code == 200
    assert_no_stack_trace(response)
