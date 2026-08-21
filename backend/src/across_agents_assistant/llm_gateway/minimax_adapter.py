import httpx
import logging
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
            "top_p": request.top_p
        }
        if self._uses_completion_token_limit(request.model):
            # MiniMax-M3 documents `max_tokens` as deprecated and expects the
            # generation cap in `max_completion_tokens`. Keeping the old field
            # on M3 can produce 200 responses with no final text on long or
            # thinking-enabled paths.
            payload["max_completion_tokens"] = request.max_tokens
        else:
            payload["max_tokens"] = request.max_tokens

        if request.stop:
            payload["stop"] = request.stop

        if request.extra_body:
            payload.update(request.extra_body)
        if self._uses_completion_token_limit(request.model) and "max_completion_tokens" not in payload:
            payload["max_completion_tokens"] = int(payload.pop("max_tokens", request.max_tokens) or request.max_tokens)

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

        generation_limit = payload.get("max_completion_tokens", payload.get("max_tokens"))
        logger.info(f"MiniMax request: url={url}, model={request.model}, "
                     f"messages_count={len(messages)}, generation_limit={generation_limit}")

        async with httpx.AsyncClient(timeout=self.request_timeout_seconds(request, default=180.0)) as client:
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
        text = self._extract_message_text(message)
        if not text.strip():
            self._raise_empty_content(data=data, choice=choice)

        return LLMResponse(
            text=text,
            raw=data,
            model=data.get("model", request.model),
            provider="minimax",
            finish_reason=choice.get("finish_reason", "stop"),
            usage=data.get("usage", {})
        )

    @staticmethod
    def _uses_completion_token_limit(model_id: str) -> bool:
        return str(model_id or "").strip().lower().startswith("minimax-m3")

    @staticmethod
    def _extract_message_text(message: dict) -> str:
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)
        return ""

    @staticmethod
    def _raise_empty_content(*, data: dict, choice: dict) -> None:
        base_resp = data.get("base_resp") if isinstance(data.get("base_resp"), dict) else {}
        base_code = base_resp.get("status_code")
        base_message = str(base_resp.get("status_msg") or "").strip()
        input_sensitive = data.get("input_sensitive") is True
        output_sensitive = data.get("output_sensitive") is True
        finish_reason = str(choice.get("finish_reason") or "").strip().lower()
        if base_code not in (None, 0, "0"):
            raise RuntimeError(f"MiniMax returned empty content with base_resp status {base_code}: {base_message or 'no message'}")
        if input_sensitive or output_sensitive:
            source = "input" if input_sensitive else "output"
            raise RuntimeError(f"MiniMax returned empty content due to {source} sensitivity policy")
        if finish_reason == "length":
            raise RuntimeError("MiniMax returned empty content because completion length was exhausted")
        raise RuntimeError("MiniMax returned empty content")

    def supports_function_calling(self, model_id: str) -> bool:
        model = self.get_model(model_id)
        if model:
            return model.supports_function_calling
        return False
