"""
Base adapter interface for LLM providers.
"""
import os
import subprocess
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
    content: str
    name: Optional[str] = None


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


class BaseLLMAdapter(ABC):
    """Abstract base class for LLM provider adapters."""

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
        """Lazy load API key from environment, fallback to macOS keychain."""
        if self._api_key:
            return self._api_key

        # Try environment variable first
        key = os.environ.get(self._config.api_key_env)
        if key:
            self._api_key = key
            return key

        # Fallback to keychain
        key = self._load_from_keychain()
        if key:
            self._api_key = key
            return key

        raise ValueError(f"No API key found for {self.provider_id}")

    def _load_from_keychain(self) -> Optional[str]:
        """Load API key from macOS keychain via security command."""
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", self._config.api_key_env, "-w"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.SubprocessError, OSError):
            pass
        return None

    def is_available(self) -> bool:
        """Check if the provider is available and configured."""
        try:
            self.api_key
            return True
        except ValueError:
            return False

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