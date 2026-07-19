import os
from pathlib import Path

import pytest


LIVE_E2E_ENV = "ACROSS_AGENTS_RUN_LIVE_E2E"
LIVE_E2E_FILES = {
    Path("e2e/test_api_e2e.py"),
    Path("e2e/test_e2e_complex_multi_wave.py"),
    Path("e2e/test_e2e_minimal_task.py"),
    Path("e2e/test_e2e_rest_api.py"),
}


@pytest.fixture(autouse=True)
def isolate_orchestrator_plugin_runtime(monkeypatch, tmp_path, request):
    """Keep unit tests from discovering a real user-installed plugin."""

    if Path(request.node.fspath).name != "test_local_paths.py":
        monkeypatch.setenv("ACROSS_AGENTS_HOME", str(tmp_path / "app-home"))
    monkeypatch.delenv("ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT", raising=False)
    monkeypatch.setenv("ACROSS_AGENTS_ORCHESTRATOR_MODE", "external")
    monkeypatch.setenv(
        "ACROSS_AGENTS_ORCHESTRATOR_COMMAND",
        str(tmp_path / "missing-across-orchestrator"),
    )
    monkeypatch.setenv(
        "ACROSS_AGENTS_ORCHESTRATOR_PLUGIN_HOME",
        str(tmp_path / "plugins"),
    )
    try:
        import across_agents_assistant.api_server as api_server
        from across_agents_assistant.worker_control import reset_worker_network_runtime_for_tests
    except Exception:
        yield
        return
    reset_worker_network_runtime_for_tests()
    api_server._orchestrator_plugin_manager = None
    api_server._orchestrator_plugin_signature = None
    try:
        yield
    finally:
        reset_worker_network_runtime_for_tests()
        api_server._orchestrator_plugin_manager = None
        api_server._orchestrator_plugin_signature = None


def pytest_collection_modifyitems(config, items):
    if os.environ.get(LIVE_E2E_ENV) == "1":
        return

    skip_live_e2e = pytest.mark.skip(
        reason=f"live app E2E requires {LIVE_E2E_ENV}=1"
    )
    tests_root = Path(__file__).resolve().parent

    for item in items:
        try:
            relative_path = Path(item.fspath).resolve().relative_to(tests_root)
        except ValueError:
            continue
        if relative_path in LIVE_E2E_FILES:
            item.add_marker(skip_live_e2e)
