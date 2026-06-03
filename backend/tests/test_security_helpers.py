import pytest

from across_agents_assistant.agent_manager import _is_minimax_io_endpoint
from across_agents_assistant.llm_client import OrchestratorClient
from across_agents_assistant.persistence.service import _normalize_local_path


def test_minimax_host_detection_uses_hostname_boundaries():
    assert OrchestratorClient._is_minimax_endpoint("https://api.minimaxi.com/v1")
    assert OrchestratorClient._is_minimax_endpoint("https://gateway.minimax.io/v1")
    assert not OrchestratorClient._is_minimax_endpoint("https://api.minimax.io.evil.example/v1")
    assert not OrchestratorClient._is_minimax_endpoint("https://evil-minimaxi.com/v1")


def test_legacy_minimax_io_detection_uses_hostname_boundaries():
    assert _is_minimax_io_endpoint("https://api.minimax.io/anthropic")
    assert not _is_minimax_io_endpoint("https://api.minimax.io.evil.example/anthropic")


def test_normalize_local_path_rejects_control_characters():
    with pytest.raises(ValueError, match="Invalid local path"):
        _normalize_local_path("/tmp/project\nother")
    with pytest.raises(ValueError, match="Invalid local path"):
        _normalize_local_path("/tmp/project\x00other")
