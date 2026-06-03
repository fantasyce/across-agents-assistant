"""Cloud LLM provider registry.

The registry keeps public, non-secret provider metadata in one place so the
settings UI, credential store, gateway, and readiness checks agree on which
providers are supported by this build.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .config import ModelInfo


@dataclass(frozen=True)
class ProviderDefinition:
    provider_id: str
    name: str
    api_key_env: str
    endpoint: str
    provider_type: str = "openai_compatible"
    models_endpoint: Optional[str] = None
    default_models: tuple[ModelInfo, ...] = field(default_factory=tuple)
    enabled: bool = True


DEFAULT_PROVIDER_DEFINITIONS: tuple[ProviderDefinition, ...] = (
    ProviderDefinition(
        provider_id="openai",
        name="OpenAI",
        api_key_env="OPENAI_API_KEY",
        endpoint="https://api.openai.com/v1",
        models_endpoint="https://api.openai.com/v1/models",
        default_models=(
            ModelInfo("gpt-5.1", "GPT-5.1", supports_function_calling=True, max_tokens=8192),
            ModelInfo("gpt-5-codex", "GPT-5 Codex", supports_function_calling=True, max_tokens=8192),
        ),
    ),
    ProviderDefinition(
        provider_id="anthropic",
        name="Anthropic",
        api_key_env="ANTHROPIC_API_KEY",
        endpoint="https://api.anthropic.com/v1",
        provider_type="anthropic",
        models_endpoint="https://api.anthropic.com/v1/models",
        default_models=(
            ModelInfo("claude-sonnet-4-6", "Claude Sonnet 4.6", supports_function_calling=True, max_tokens=8192),
            ModelInfo("claude-opus-4-1", "Claude Opus 4.1", supports_function_calling=True, max_tokens=8192),
        ),
    ),
    ProviderDefinition(
        provider_id="deepseek",
        name="DeepSeek",
        api_key_env="DEEPSEEK_API_KEY",
        endpoint="https://api.deepseek.com/v1",
        models_endpoint="https://api.deepseek.com/v1/models",
        default_models=(
            ModelInfo("deepseek-chat", "DeepSeek Chat", supports_function_calling=True, max_tokens=8192),
            ModelInfo("deepseek-reasoner", "DeepSeek Reasoner", supports_function_calling=True, max_tokens=8192),
        ),
    ),
    ProviderDefinition(
        provider_id="minimax",
        name="MiniMax",
        api_key_env="MINIMAX_API_KEY",
        endpoint="https://api.minimaxi.com/v1",
        models_endpoint="https://api.minimaxi.com/v1/models",
        default_models=(
            ModelInfo("MiniMax-M2.7", "MiniMax M2.7", supports_function_calling=True, max_tokens=8192),
            ModelInfo("MiniMax-M3", "MiniMax M3", supports_function_calling=True, max_tokens=8192),
        ),
    ),
    ProviderDefinition(
        provider_id="bailian",
        name="Alibaba Bailian / Qwen",
        api_key_env="BAILIAN_API_KEY",
        endpoint="https://dashscope.aliyuncs.com/compatible-mode/v1",
        models_endpoint="https://dashscope.aliyuncs.com/compatible-mode/v1/models",
        default_models=(
            ModelInfo("qwen-plus", "Qwen Plus", supports_function_calling=True, max_tokens=8192),
            ModelInfo("qwen-max", "Qwen Max", supports_function_calling=True, max_tokens=8192),
            ModelInfo("qwen-turbo", "Qwen Turbo", supports_function_calling=True, max_tokens=8192),
        ),
    ),
    ProviderDefinition(
        provider_id="moonshot",
        name="Moonshot / Kimi",
        api_key_env="MOONSHOT_API_KEY",
        endpoint="https://api.moonshot.cn/v1",
        models_endpoint="https://api.moonshot.cn/v1/models",
        default_models=(
            ModelInfo("kimi-k2-0711-preview", "Kimi K2", supports_function_calling=True, max_tokens=8192),
            ModelInfo("moonshot-v1-32k", "Moonshot v1 32K", supports_function_calling=True, max_tokens=8192),
        ),
    ),
    ProviderDefinition(
        provider_id="zhipu",
        name="Zhipu GLM",
        api_key_env="ZHIPU_API_KEY",
        endpoint="https://open.bigmodel.cn/api/paas/v4",
        models_endpoint="https://open.bigmodel.cn/api/paas/v4/models",
        default_models=(
            ModelInfo("glm-4.5", "GLM-4.5", supports_function_calling=True, max_tokens=8192),
            ModelInfo("glm-4.5-air", "GLM-4.5 Air", supports_function_calling=True, max_tokens=8192),
        ),
    ),
    ProviderDefinition(
        provider_id="volcengine",
        name="Volcengine Ark / Doubao",
        api_key_env="VOLCENGINE_API_KEY",
        endpoint="https://ark.cn-beijing.volces.com/api/v3",
        models_endpoint="https://ark.cn-beijing.volces.com/api/v3/models",
        default_models=(
            ModelInfo("doubao-seed-1-6", "Doubao Seed 1.6", supports_function_calling=True, max_tokens=8192),
        ),
    ),
    ProviderDefinition(
        provider_id="google",
        name="Google Gemini",
        api_key_env="GEMINI_API_KEY",
        endpoint="https://generativelanguage.googleapis.com/v1beta/openai",
        models_endpoint="https://generativelanguage.googleapis.com/v1beta/openai/models",
        default_models=(
            ModelInfo("gemini-2.5-pro", "Gemini 2.5 Pro", supports_function_calling=True, max_tokens=8192),
            ModelInfo("gemini-2.5-flash", "Gemini 2.5 Flash", supports_function_calling=True, max_tokens=8192),
        ),
    ),
    ProviderDefinition(
        provider_id="xai",
        name="xAI",
        api_key_env="XAI_API_KEY",
        endpoint="https://api.x.ai/v1",
        models_endpoint="https://api.x.ai/v1/models",
        default_models=(
            ModelInfo("grok-4", "Grok 4", supports_function_calling=True, max_tokens=8192),
            ModelInfo("grok-4-mini", "Grok 4 Mini", supports_function_calling=True, max_tokens=8192),
        ),
    ),
    ProviderDefinition(
        provider_id="mistral",
        name="Mistral AI",
        api_key_env="MISTRAL_API_KEY",
        endpoint="https://api.mistral.ai/v1",
        models_endpoint="https://api.mistral.ai/v1/models",
        default_models=(
            ModelInfo("mistral-large-latest", "Mistral Large", supports_function_calling=True, max_tokens=8192),
            ModelInfo("codestral-latest", "Codestral", supports_function_calling=True, max_tokens=8192),
        ),
    ),
    ProviderDefinition(
        provider_id="groq",
        name="Groq",
        api_key_env="GROQ_API_KEY",
        endpoint="https://api.groq.com/openai/v1",
        models_endpoint="https://api.groq.com/openai/v1/models",
        default_models=(
            ModelInfo("llama-3.3-70b-versatile", "Llama 3.3 70B Versatile", supports_function_calling=True, max_tokens=8192),
            ModelInfo("openai/gpt-oss-120b", "GPT OSS 120B", supports_function_calling=True, max_tokens=8192),
        ),
    ),
    ProviderDefinition(
        provider_id="cohere",
        name="Cohere",
        api_key_env="COHERE_API_KEY",
        endpoint="https://api.cohere.com/compatibility/v1",
        models_endpoint="https://api.cohere.com/compatibility/v1/models",
        default_models=(
            ModelInfo("command-a-03-2025", "Command A", supports_function_calling=True, max_tokens=8192),
        ),
    ),
)


def get_default_provider_definitions() -> tuple[ProviderDefinition, ...]:
    return DEFAULT_PROVIDER_DEFINITIONS


def get_default_provider_ids() -> tuple[str, ...]:
    return tuple(provider.provider_id for provider in DEFAULT_PROVIDER_DEFINITIONS)


def get_provider_definition(provider_id: str) -> Optional[ProviderDefinition]:
    for provider in DEFAULT_PROVIDER_DEFINITIONS:
        if provider.provider_id == provider_id:
            return provider
    return None
