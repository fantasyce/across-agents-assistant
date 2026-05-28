"""Tests for LLM provider readiness check on task submission.

Covers the ``_check_llm_provider_readiness`` function used by ``POST /api/tasks/auto``
to fail early with a clear 412 error when no API keys are configured.
"""

import os
import tempfile
from typing import Dict, Optional

import pytest

# Point persistence to a temp directory before importing the module,
# otherwise the module-level ``persistence = PersistenceService()``
# will try to open the default path which may not exist.
os.environ.setdefault("ACROSS_AGENTS_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

from across_agents_assistant.api_server import _check_llm_provider_readiness


@pytest.fixture(autouse=True)
def reset_credential_cache(monkeypatch: pytest.MonkeyPatch):
    """Reset the module-level credential cache before and after each test."""
    import across_agents_assistant.api_server as srv

    class EmptyStore:
        def get(self, provider_id: str):
            return None

    cache_before: Dict[str, Optional[str]] = dict(srv._credential_cache)
    get_store_before = srv._get_credential_store
    srv._credential_cache.clear()
    monkeypatch.setattr(srv, "_get_credential_store", lambda: EmptyStore())
    yield
    srv._credential_cache.clear()
    srv._credential_cache.update(cache_before)
    monkeypatch.setattr(srv, "_get_credential_store", get_store_before)


class TestLlmProviderReadiness:
    def test_both_providers_missing_returns_all(self, monkeypatch: pytest.MonkeyPatch):
        """When neither deepseek nor minimax has a key, both are returned as missing."""
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        missing = _check_llm_provider_readiness()
        assert missing == ["deepseek", "minimax"]

    def test_deepseek_configured_only(self, monkeypatch: pytest.MonkeyPatch):
        """Only DeepSeek has a key — readiness should pass (empty list)."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "unit-valid-deepseek-key")
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        missing = _check_llm_provider_readiness()
        assert missing == []

    def test_minimax_configured_only(self, monkeypatch: pytest.MonkeyPatch):
        """Only MiniMax has a key — readiness should pass (empty list)."""
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.setenv("MINIMAX_API_KEY", "unit-valid-minimax-key")
        missing = _check_llm_provider_readiness()
        assert missing == []

    def test_both_configured(self, monkeypatch: pytest.MonkeyPatch):
        """Both providers have keys — readiness passes."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "unit-valid-ds")
        monkeypatch.setenv("MINIMAX_API_KEY", "unit-valid-mx")
        missing = _check_llm_provider_readiness()
        assert missing == []

    def test_runtime_credential_cache_respected(self, monkeypatch: pytest.MonkeyPatch):
        """Runtime credential cache entry for a single provider satisfies readiness."""
        import across_agents_assistant.api_server as srv
        srv._credential_cache["deepseek"] = "cached-ds-key"
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        missing = _check_llm_provider_readiness()
        assert missing == []

    def test_whitespace_env_key_not_accepted(self, monkeypatch: pytest.MonkeyPatch):
        """An env var set to whitespace-only should count as not configured."""
        monkeypatch.setenv("DEEPSEEK_API_KEY", "   ")
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        missing = _check_llm_provider_readiness()
        assert missing == ["deepseek", "minimax"]

    def test_whitespace_credential_cache_not_accepted(self, monkeypatch: pytest.MonkeyPatch):
        """Whitespace-only key in cache should count as not configured."""
        import across_agents_assistant.api_server as srv
        srv._credential_cache["deepseek"] = "   "
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        missing = _check_llm_provider_readiness()
        assert missing == ["deepseek", "minimax"]

    def test_placeholder_credential_cache_not_accepted(self, monkeypatch: pytest.MonkeyPatch):
        """Placeholder keys should not satisfy backend readiness."""
        import across_agents_assistant.api_server as srv
        srv._credential_cache["minimax"] = "placeholder-secret"
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        missing = _check_llm_provider_readiness()
        assert missing == ["deepseek", "minimax"]

    def test_key_status_treats_whitespace_cache_as_not_configured(self):
        """get_keys_status should report whitespace-only cache entries as not_configured."""
        import asyncio
        import across_agents_assistant.api_server as srv
        srv._credential_cache["deepseek"] = "   "
        srv._credential_cache["minimax"] = ""
        os.environ.pop("DEEPSEEK_API_KEY", None)
        os.environ.pop("MINIMAX_API_KEY", None)

        response = asyncio.run(srv.get_keys_status())

        assert response.providers["deepseek"] == "not_configured"
        assert response.providers["minimax"] == "not_configured"

    def test_credentials_file_satisfies_submission_readiness_without_env_or_cache(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Task submission should trust the backend-owned credential store."""
        import across_agents_assistant.api_server as srv

        class DummyStore:
            def get(self, provider_id: str):
                return "sk-from-file" if provider_id == "deepseek" else None

        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        srv._credential_cache.clear()
        monkeypatch.setattr(srv, "_get_credential_store", lambda: DummyStore())

        missing = _check_llm_provider_readiness()

        assert missing == []
