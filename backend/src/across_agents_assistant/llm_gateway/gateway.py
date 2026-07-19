import logging
from typing import List, Optional, Dict, Any
from .base_adapter import (
    BaseLLMAdapter, LLMResponse, ChatCompletionRequest, ChatMessage,
    KeychainDeniedError, KeychainTimeoutError, KeychainNotFoundError, KeychainError
)
from .config import LLMConfig, LLMProviderConfig, load_llm_config, save_llm_config, ModelInfo
from .minimax_adapter import MiniMaxAdapter
from .bailian_adapter import BailianAdapter
from .deepseek_adapter import DeepseekAdapter
from .openai_compatible_adapter import OpenAICompatibleAdapter
from .anthropic_adapter import AnthropicAdapter

logger = logging.getLogger("across_agents_assistant.llm_gateway")

class LLMGateway:
    """
    Unified gateway for multiple LLM providers.
    """

    ADAPTERS = {
        "minimax": MiniMaxAdapter,
        "bailian": BailianAdapter,
        "deepseek": DeepseekAdapter,
        "openai_compatible": OpenAICompatibleAdapter,
        "anthropic": AnthropicAdapter,
    }

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or load_llm_config()
        self._adapters: Dict[str, BaseLLMAdapter] = {}
        self._current_provider_id: Optional[str] = None
        self._initialize_adapters()
        self._current_provider_id = self.config.primary_provider

    def _initialize_adapters(self):
        """Initialize all configured adapters."""
        for provider_config in self.config.providers:
            adapter_class = (
                self.ADAPTERS.get(provider_config.provider_type)
                or self.ADAPTERS.get(provider_config.provider_id)
            )
            if adapter_class:
                self._adapters[provider_config.provider_id] = adapter_class(provider_config)
                logger.info(f"Initialized LLM adapter: {provider_config.provider_id}")

    def list_providers(self) -> List[LLMProviderConfig]:
        """List all configured providers."""
        return [p for p in self.config.providers if p.enabled]

    def list_models(self, provider_id: str) -> List[ModelInfo]:
        """List all models for a provider."""
        adapter = self._adapters.get(provider_id)
        if adapter:
            return adapter.list_models()
        return []

    async def fetch_models(self, provider_id: str) -> List[ModelInfo]:
        """Fetch live models for a provider, falling back to configured models."""
        adapter = self._adapters.get(provider_id)
        if adapter:
            try:
                return await adapter.fetch_models()
            except Exception as exc:
                logger.warning("Live model discovery failed for %s: %s", provider_id, exc)
                return adapter.list_models()
        return []

    def switch_provider(self, provider_id: str) -> bool:
        """Switch to a different provider."""
        if provider_id not in self._adapters:
            logger.error(f"Provider not available: {provider_id}")
            return False

        if not self._adapters[provider_id].is_available():
            logger.error(f"Provider not available (no API key): {provider_id}")
            return False

        self._current_provider_id = provider_id
        logger.info(f"Switched to LLM provider: {provider_id}")
        return True

    def get_current_provider_id(self) -> str:
        """Get the current provider ID."""
        return self._current_provider_id or self.config.primary_provider

    def get_current_adapter(self) -> Optional[BaseLLMAdapter]:
        """Get the current adapter."""
        if self._current_provider_id:
            return self._adapters.get(self._current_provider_id)
        return None

    async def chat(
        self,
        message: Optional[str] = None,
        system_prompt: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        model: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        functions: Optional[List[Dict[str, Any]]] = None,
        provider_id: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """Send a chat message and get a response."""
        adapter = self._adapters.get(provider_id) if provider_id else self.get_current_adapter()
        if not adapter:
            raise RuntimeError("No LLM adapter available")

        actual_provider = provider_id or self._current_provider_id
        logger.info(f"LLM gateway chat: provider={actual_provider}, "
                     f"adapter_available={adapter.is_available()}, "
                     f"message_len={len(message) if message else 0}, "
                     f"has_system_prompt={system_prompt is not None}, "
                     f"context_keys={list(context.keys()) if context else []}, "
                     f"model_override={model}")

        request_messages: List[ChatMessage] = []
        if messages:
            for msg in messages:
                request_messages.append(ChatMessage(
                    role=msg.get("role", "user"),
                    content=msg.get("content") if "content" in msg else "",
                    name=msg.get("name"),
                    tool_calls=msg.get("tool_calls"),
                    tool_call_id=msg.get("tool_call_id"),
                ))
        else:
            system_parts = []
            if system_prompt:
                system_parts.append(system_prompt)

            if context:
                ctx_parts = []
                for key, value in context.items():
                    if value:
                        ctx_parts.append(f"{key}: {value}")
                if ctx_parts:
                    system_parts.append("【System Context】\n" + "\n".join(ctx_parts))

            if system_parts:
                request_messages.append(ChatMessage(role="system", content="\n\n".join(system_parts)))

            request_messages.append(ChatMessage(role="user", content=message or ""))

        # Determine model
        if model is None:
            models = adapter.list_models()
            if models:
                model = models[0].model_id
            else:
                raise RuntimeError(
                    f"No models available for provider {provider_id or self._current_provider_id}"
                )

        # Create request
        request = ChatCompletionRequest(
            messages=request_messages,
            model=model,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2048),
            top_p=kwargs.get("top_p", 1.0),
            stop=kwargs.get("stop"),
            functions=functions,
            extra_body=dict(kwargs.get("extra_body") or {}),
            timeout_seconds=float(kwargs["timeout"]) if kwargs.get("timeout") is not None else None,
        )

        # Try current provider, fallback to others
        try:
            return await adapter.chat(request)
        except (KeychainDeniedError, KeychainTimeoutError, KeychainNotFoundError):
            # Re-raise keychain errors directly so API layer can return user-friendly messages
            raise
        except Exception as e:
            last_error = e
            logger.warning(f"Primary provider {provider_id or self._current_provider_id} failed: {e}")
            for fallback_id in self.config.fallback_providers:
                if provider_id and fallback_id == provider_id:
                    continue
                fallback_adapter = self._adapters.get(fallback_id)
                if fallback_adapter and fallback_adapter.is_available():
                    try:
                        logger.info(f"Trying fallback provider: {fallback_id}")
                        fallback_models = fallback_adapter.list_models()
                        fallback_model = fallback_models[0].model_id if fallback_models else request.model
                        fallback_request = ChatCompletionRequest(
                            messages=request.messages,
                            model=fallback_model,
                            temperature=request.temperature,
                            max_tokens=request.max_tokens,
                            top_p=request.top_p,
                            stop=request.stop,
                            functions=request.functions,
                            extra_body=dict(request.extra_body or {}),
                            timeout_seconds=request.timeout_seconds,
                        )
                        return await fallback_adapter.chat(fallback_request)
                    except (KeychainDeniedError, KeychainTimeoutError, KeychainNotFoundError):
                        raise
                    except Exception as fallback_error:
                        last_error = fallback_error
                        logger.warning(f"Fallback provider {fallback_id} also failed: {fallback_error}")
                        continue

            raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")

    def save_config(self):
        """Save current configuration."""
        save_llm_config(self.config)

# Global gateway instance (lazy loaded)
_gateway: Optional[LLMGateway] = None

def get_gateway() -> LLMGateway:
    """Get or create the global gateway instance."""
    global _gateway
    if _gateway is None:
        _gateway = LLMGateway()
    return _gateway
