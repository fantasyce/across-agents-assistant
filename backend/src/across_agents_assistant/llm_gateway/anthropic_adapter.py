from __future__ import annotations

from typing import Any, Dict, List

import httpx

from .base_adapter import BaseLLMAdapter, ChatCompletionRequest, ChatMessage, LLMResponse
from .config import ModelInfo


def parse_anthropic_models_payload(payload: Dict[str, Any]) -> List[ModelInfo]:
    models: List[ModelInfo] = []
    raw_models = payload.get("data")
    if not isinstance(raw_models, list):
        return models
    for raw_model in raw_models:
        if not isinstance(raw_model, dict):
            continue
        model_id = str(raw_model.get("id") or "").strip()
        if not model_id:
            continue
        display_name = str(raw_model.get("display_name") or model_id)
        models.append(ModelInfo(model_id=model_id, name=display_name, supports_function_calling=True))
    return models


class AnthropicAdapter(BaseLLMAdapter):
    """Small Anthropic Messages API adapter used by the gateway."""

    async def fetch_models(self) -> List[ModelInfo]:
        endpoint = self._config.models_endpoint or f"{self._config.endpoint.rstrip('/')}/models"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            response = await client.get(endpoint, headers=headers)
            response.raise_for_status()
            parsed = parse_anthropic_models_payload(response.json())
        return parsed or self.list_models()

    async def chat(self, request: ChatCompletionRequest) -> LLMResponse:
        system_parts: List[str] = []
        messages: List[Dict[str, Any]] = []
        for msg in request.messages:
            if msg.role == "system":
                if msg.content:
                    system_parts.append(str(msg.content))
                continue
            if msg.role not in {"user", "assistant"}:
                continue
            messages.append({"role": msg.role, "content": msg.content or ""})

        payload: Dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        endpoint = f"{self._config.endpoint.rstrip('/')}/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds(default=180.0), trust_env=False) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        text_parts = [
            str(block.get("text") or "")
            for block in data.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return LLMResponse(
            text="".join(text_parts),
            raw=data,
            model=data.get("model", request.model),
            provider=self.provider_id,
            finish_reason=data.get("stop_reason", "stop"),
            usage=data.get("usage", {}),
        )

    def supports_function_calling(self, model_id: str) -> bool:
        model = self.get_model(model_id)
        if model:
            return model.supports_function_calling
        return True
