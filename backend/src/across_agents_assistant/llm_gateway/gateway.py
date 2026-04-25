"""
LLM Gateway - Main entry point for LLM interactions.
"""
from .base_adapter import (
    BaseLLMAdapter,
    ChatCompletionRequest,
    ChatMessage,
    FunctionCall,
    LLMResponse,
)
from .config import LLMConfig, LLMProviderConfig, load_llm_config

__all__ = [
    "LLMGateway",
    "LLMResponse",
    "LLMConfig",
    "LLMProviderConfig",
    "BaseLLMAdapter",
    "ChatCompletionRequest",
    "ChatMessage",
    "FunctionCall",
]


class LLMGateway:
    """
    Unified gateway for interacting with multiple LLM providers.

    Provides a single interface for chat completions with automatic
    failover and provider management.
    """

    def __init__(self, config: LLMConfig):
        self._config = config
        self._adapters: dict[str, BaseLLMAdapter] = {}

    def register_adapter(self, adapter: BaseLLMAdapter) -> None:
        """Register an adapter for a provider."""
        self._adapters[adapter.provider_id] = adapter

    def get_adapter(self, provider_id: str) -> BaseLLMAdapter:
        """Get adapter by provider ID."""
        return self._adapters[provider_id]

    def list_providers(self) -> list[str]:
        """List all registered provider IDs."""
        return list(self._adapters.keys())

    def is_provider_available(self, provider_id: str) -> bool:
        """Check if a provider is available."""
        adapter = self._adapters.get(provider_id)
        return adapter.is_available() if adapter else False