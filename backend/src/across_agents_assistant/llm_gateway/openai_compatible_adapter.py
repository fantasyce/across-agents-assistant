import logging
from typing import Any, Dict, List

import httpx

from .base_adapter import BaseLLMAdapter, ChatCompletionRequest, LLMResponse
from .config import ModelInfo

logger = logging.getLogger("across_agents_assistant.llm_gateway.openai_compatible")


def parse_openai_models_payload(payload: Dict[str, Any]) -> List[ModelInfo]:
    """Parse OpenAI-compatible model-list payloads into ModelInfo values."""
    result: List[ModelInfo] = []
    raw_models = payload.get("data")
    if not isinstance(raw_models, list):
        return result
    for raw_model in raw_models:
        if not isinstance(raw_model, dict):
            continue
        model_id = str(raw_model.get("id") or "").strip()
        if not model_id:
            continue
        if model_id.startswith("models/"):
            model_id = model_id.split("/", 1)[1]
        result.append(ModelInfo(model_id=model_id, name=model_id))
    return result


class OpenAICompatibleAdapter(BaseLLMAdapter):
    """Adapter for providers that expose OpenAI-compatible chat completions."""

    async def fetch_models(self) -> List[ModelInfo]:
        endpoint = self._config.models_endpoint or f"{self._config.endpoint.rstrip('/')}/models"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=20.0, trust_env=False) as client:
            response = await client.get(endpoint, headers=headers)
            response.raise_for_status()
            parsed = parse_openai_models_payload(response.json())
        return parsed or self.list_models()

    async def chat(self, request: ChatCompletionRequest) -> LLMResponse:
        url = f"{self._config.endpoint.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        messages = []
        for msg in request.messages:
            payload_msg = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                payload_msg["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                payload_msg["tool_call_id"] = msg.tool_call_id
            messages.append(payload_msg)

        payload: Dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
        }
        if request.stop:
            payload["stop"] = request.stop
        if request.extra_body:
            payload.update(request.extra_body)
        if request.functions and self.supports_function_calling(request.model):
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": fn["name"],
                        "description": fn.get("description", ""),
                        "parameters": fn.get("parameters", {"type": "object", "properties": {}}),
                    },
                }
                for fn in request.functions
            ]
            payload["tool_choice"] = "auto"

        provider_id = self.provider_id
        if provider_id == "minimax" and "reasoning_split" not in payload:
            payload["reasoning_split"] = True

        logger.info(
            "OpenAI-compatible request: provider=%s url=%s model=%s messages=%d",
            provider_id,
            url,
            request.model,
            len(messages),
        )
        async with httpx.AsyncClient(timeout=self.request_timeout_seconds(request, default=180.0), trust_env=False) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        message = choice.get("message") or {}
        return LLMResponse(
            text=message.get("content", "") or "",
            raw=data,
            model=data.get("model", request.model),
            provider=provider_id,
            finish_reason=choice.get("finish_reason", "stop"),
            usage=data.get("usage", {}),
        )

    def supports_function_calling(self, model_id: str) -> bool:
        model = self.get_model(model_id)
        if model:
            return model.supports_function_calling
        return True
