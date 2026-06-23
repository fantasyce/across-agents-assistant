import logging
import httpx
from typing import Optional
from .base_adapter import (
    BaseLLMAdapter, LLMResponse, ChatCompletionRequest, ChatMessage
)

logger = logging.getLogger("across_agents_assistant.llm_gateway.minimax")

class MiniMaxAdapter(BaseLLMAdapter):
    """Adapter for MiniMax LLM API."""

    async def chat(self, request: ChatCompletionRequest) -> LLMResponse:
        """Send chat completion request to MiniMax API."""
        url = f"{self._config.endpoint}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        messages = []
        for msg in request.messages:
            payload_msg = {
                "role": msg.role,
                "content": msg.content
            }
            if msg.tool_calls:
                payload_msg["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                payload_msg["tool_call_id"] = msg.tool_call_id
            messages.append(payload_msg)

        payload = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p
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

        logger.info(f"MiniMax request: url={url}, model={request.model}, "
                     f"messages_count={len(messages)}, max_tokens={request.max_tokens}")

        async with httpx.AsyncClient(timeout=self.timeout_seconds(default=180.0)) as client:
            response = await client.post(url, headers=headers, json=payload)

            if response.status_code != 200:
                logger.error(f"MiniMax API error: status={response.status_code}, "
                             f"url={url}, model={request.model}, "
                             f"response_body={response.text[:500]}")
                logger.error(f"MiniMax request payload (truncated): "
                             f"model={payload.get('model')}, "
                             f"messages_count={len(payload.get('messages', []))}, "
                             f"max_tokens={payload.get('max_tokens')}, "
                             f"temperature={payload.get('temperature')}, "
                             f"top_p={payload.get('top_p')}")

            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        message = choice["message"]

        return LLMResponse(
            text=message.get("content", ""),
            raw=data,
            model=data.get("model", request.model),
            provider="minimax",
            finish_reason=choice.get("finish_reason", "stop"),
            usage=data.get("usage", {})
        )

    def supports_function_calling(self, model_id: str) -> bool:
        model = self.get_model(model_id)
        if model:
            return model.supports_function_calling
        return False
