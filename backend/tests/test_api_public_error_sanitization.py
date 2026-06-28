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


def test_public_payload_sanitizer_redacts_traceback_text_under_neutral_keys():
    payload = api_server._sanitize_public_payload({"note": TRACEBACK_TEXT, "nested": [{"summary": TRACEBACK_TEXT}]})

    encoded = json.dumps(payload)
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


def test_release_verification_endpoint_sanitizes_report_payload(monkeypatch, tmp_path):
    class FakeState:
        _persistence = None

        def get_all_tasks(self):
            return []

    monkeypatch.setattr(api_server, "_task_state", FakeState())
    monkeypatch.setattr(api_server, "app_subdir", lambda name: tmp_path / name)
    monkeypatch.setattr(
        api_server,
        "_build_startup_diagnostics",
        lambda: {
            "schema_version": "1.0",
            "app_version": "0.4.0",
            "generated_at": "2026-05-31T12:00:00Z",
            "status": "blocked",
            "summary": {"status": "blocked", "passed": 0, "warnings": 0, "failed": 1, "check_count": 1},
            "paths": {},
            "runtime": {},
            "keys": {"has_any_key": False, "providers": {}, "readiness_blockers": [TRACEBACK_TEXT]},
            "checks": [{"id": "boom", "title": "Boom", "status": "failed", "detail": TRACEBACK_TEXT}],
        },
    )

    response = TestClient(app).post("/api/release/verification")

    assert response.status_code == 200
    encoded = _encoded(response)
    assert "Traceback (most recent call last)" not in encoded
    assert 'File "/Users/example/private/app.py"' not in encoded
    assert "private internal path" not in encoded


def test_external_task_stream_sanitizes_runtime_exception(monkeypatch):
    class FakePlugin:
        def get_task(self, task_id):
            raise RuntimeError(TRACEBACK_TEXT)

    monkeypatch.setattr(api_server, "_is_external_orchestrator_task", lambda task_id: True)
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakePlugin())

    response = TestClient(app).get("/api/tasks/external-demo/stream")

    assert response.status_code == 200
    assert_no_stack_trace(response)
