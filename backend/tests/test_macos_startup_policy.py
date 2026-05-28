import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _swift_source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_session_view_model_constructor_does_not_fetch_backend():
    source = _swift_source("macOS-Client/Sources/ViewModels/SessionViewModel.swift")
    match = re.search(r"\n    init\(\) \{\n(?P<body>.*?)\n    \}", source, re.S)

    assert match, "SessionViewModel.init() should remain easy to audit"
    body = match.group("body")

    assert "loadDefaultWorkspaceDirectory()" in body
    assert "fetchProjects()" not in body
    assert "fetchSessions()" not in body
    assert "fetchMCPContexts()" not in body


def test_main_panel_owns_one_initial_data_load():
    source = _swift_source("macOS-Client/Sources/Views/MainPanelView.swift")

    assert "loadInitialDataWhenBackendAvailable()" in source
    assert source.count("viewModel.loadInitialDataIfNeeded()") == 1
    assert "settingsViewModel.availabilityBootstrapState != .loading" in source
    assert source.count("viewModel.fetchProjects()") == 0
    assert source.count("viewModel.fetchSessions()") == 0


def test_agent_detection_endpoint_offloads_blocking_probe():
    source = _swift_source("backend/src/across_agents_assistant/api_server.py")

    assert "await asyncio.to_thread(detect_local_agents, force=force)" in source
