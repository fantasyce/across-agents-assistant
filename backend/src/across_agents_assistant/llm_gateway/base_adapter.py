"""
Base adapter interface for LLM providers.
"""
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .config import LLMProviderConfig, ModelInfo


@dataclass
class LLMResponse:
    """Response from an LLM chat completion."""
    text: str
    raw: Dict
    model: str
    provider: str
    finish_reason: str
    usage: Optional[Dict] = None


@dataclass
class ChatMessage:
    """A single message in a chat conversation."""
    role: str
    content: Optional[str]
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


@dataclass
class FunctionCall:
    """A function call requested by the LLM."""
    name: str
    arguments: Dict


@dataclass
class ChatCompletionRequest:
    """Request for chat completion."""
    messages: List[ChatMessage]
    model: str
    temperature: float = 0.7
    max_tokens: int = 8192
    top_p: float = 1.0
    stop: Optional[List[str]] = None
    functions: Optional[List[Dict]] = None
    extra_body: Dict[str, Any] = field(default_factory=dict)


class KeychainError(Exception):
    """Raised when keychain access fails."""
    pass


class KeychainDeniedError(KeychainError):
    """Raised when user denies keychain access."""
    pass


class KeychainTimeoutError(KeychainError):
    """Raised when keychain access times out."""
    pass


class KeychainNotFoundError(KeychainError):
    """Raised when API key is not configured in keychain."""
    pass


class BaseLLMAdapter(ABC):

    def __init__(self, config: LLMProviderConfig):
        self._config = config
        self._api_key: Optional[str] = None

    @property
    def provider_id(self) -> str:
        return self._config.provider_id

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def api_key(self) -> str:
        """Return the API key from cache or environment.

        The backend does NOT access the macOS keychain directly.
        Keys are synced by the Swift client via POST /api/keys on startup
        and when the user saves new keys in Settings.

        Raises:
            ValueError: No API key found for this provider
        """
        if self._api_key:
            return self._api_key

        key = os.environ.get(self._config.api_key_env)
        if key:
            self._api_key = key
            return key

        raise ValueError(f"No API key found for {self.provider_id}")

    def is_available(self) -> bool:
        """Check if the provider has an API key available (cache or env var)."""
        if self._api_key:
            return True
        key = os.environ.get(self._config.api_key_env)
        return bool(key and key.strip())

    def timeout_seconds(self, *, kind: str = "chat", default: float = 60.0) -> float:
        """Return provider HTTP timeout seconds from environment or a safe default."""
        provider_key = f"ACROSS_LLM_{self.provider_id.upper().replace('-', '_')}_{kind.upper()}_TIMEOUT_SECONDS"
        generic_key = f"ACROSS_LLM_{kind.upper()}_TIMEOUT_SECONDS"
        for key in (provider_key, generic_key):
            raw = os.environ.get(key)
            if not raw:
                continue
            try:
                value = float(raw)
            except ValueError:
                continue
            if value > 0:
                return value
        return default

    @abstractmethod
    def chat(self, request: ChatCompletionRequest) -> LLMResponse:
        """Send a chat completion request to the provider."""
        pass

    @abstractmethod
    def supports_function_calling(self, model: str) -> bool:
        """Check if a model supports function calling."""
        pass

    def get_model(self, model_id: str) -> Optional[ModelInfo]:
        """Get model info by ID."""
        for model in self._config.models:
            if model.model_id == model_id:
                return model
        return None

    def list_models(self) -> List[ModelInfo]:
        """List all available models for this provider."""
        return self._config.models.copy()

    async def fetch_models(self) -> List[ModelInfo]:
        """Fetch live models when supported; default to configured fallback list."""
        return self.list_models()
