"""
LLM Gateway configuration management.
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ModelInfo:
    """Information about a specific model."""
    model_id: str
    name: str
    supports_vision: bool = False
    supports_function_calling: bool = False
    max_tokens: int = 8192


@dataclass
class LLMProviderConfig:
    """Configuration for an LLM provider."""
    provider_id: str
    name: str
    api_key_env: str
    endpoint: str
    models: List[ModelInfo] = field(default_factory=list)
    enabled: bool = True


@dataclass
class LLMConfig:
    """Global LLM Gateway configuration."""
    providers: List[LLMProviderConfig] = field(default_factory=list)
    primary_provider: str = "minimax"
    fallback_providers: List[str] = field(default_factory=list)


CONFIG_FILE = Path.home() / "Library/Application Support/AcrossAgentsAssistant/llm_config.json"


def _default_config() -> LLMConfig:
    """Return default configuration with MiniMax, Bailian, Deepseek providers."""
    return LLMConfig(
        providers=[
            LLMProviderConfig(
                provider_id="minimax",
                name="MiniMax",
                api_key_env="MINIMAX_API_KEY",
                endpoint="https://api.minimax.chat/v1",
                models=[
                    ModelInfo(model_id="MiniMax-Text-01", name="MiniMax Text 01", supports_vision=False, supports_function_calling=True, max_tokens=8192),
                    ModelInfo(model_id="abab6.5s-chat", name="ABAB 6.5S Chat", supports_vision=False, supports_function_calling=True, max_tokens=8192),
                ],
                enabled=True,
            ),
            LLMProviderConfig(
                provider_id="bailian",
                name="Bailian (Alibaba)",
                api_key_env="BAILIAN_API_KEY",
                endpoint="https://dashscope.aliyuncs.com/compatible-mode/v1",
                models=[
                    ModelInfo(model_id="qwen-plus", name="Qwen Plus", supports_vision=False, supports_function_calling=True, max_tokens=8192),
                    ModelInfo(model_id="qwen-max", name="Qwen Max", supports_vision=False, supports_function_calling=True, max_tokens=8192),
                    ModelInfo(model_id="qwen-turbo", name="Qwen Turbo", supports_vision=False, supports_function_calling=True, max_tokens=8192),
                ],
                enabled=True,
            ),
            LLMProviderConfig(
                provider_id="deepseek",
                name="Deepseek",
                api_key_env="DEEPSEEK_API_KEY",
                endpoint="https://api.deepseek.com/v1",
                models=[
                    ModelInfo(model_id="deepseek-chat", name="DeepSeek Chat", supports_vision=False, supports_function_calling=True, max_tokens=8192),
                    ModelInfo(model_id="deepseek-coder", name="DeepSeek Coder", supports_vision=False, supports_function_calling=True, max_tokens=8192),
                ],
                enabled=True,
            ),
        ],
        primary_provider="minimax",
        fallback_providers=["bailian", "deepseek"],
    )


def _parse_config(data: Dict) -> LLMConfig:
    """Parse JSON data into LLMConfig."""
    providers = []
    for p in data.get("providers", []):
        models = [ModelInfo(**m) for m in p.get("models", [])]
        providers.append(LLMProviderConfig(
            provider_id=p["provider_id"],
            name=p["name"],
            api_key_env=p["api_key_env"],
            endpoint=p["endpoint"],
            models=models,
            enabled=p.get("enabled", True),
        ))
    return LLMConfig(
        providers=providers,
        primary_provider=data.get("primary_provider", "minimax"),
        fallback_providers=data.get("fallback_providers", []),
    )


def load_llm_config() -> LLMConfig:
    """Load LLM config from file, or return defaults if file doesn't exist."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            return _parse_config(data)
        except (json.JSONDecodeError, KeyError):
            pass
    return _default_config()


def save_llm_config(config: LLMConfig) -> None:
    """Save LLM config to file."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "providers": [
            {
                "provider_id": p.provider_id,
                "name": p.name,
                "api_key_env": p.api_key_env,
                "endpoint": p.endpoint,
                "models": [vars(m) for m in p.models],
                "enabled": p.enabled,
            }
            for p in config.providers
        ],
        "primary_provider": config.primary_provider,
        "fallback_providers": config.fallback_providers,
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)