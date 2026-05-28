import httpx
from typing import Optional
from .base_adapter import (
    BaseLLMAdapter, LLMResponse, ChatCompletionRequest, ChatMessage
)

class BailianAdapter(BaseLLMAdapter):
    """Adapter for Alibaba Bailian (Qwen) LLM API."""

    async def chat(self, request: ChatCompletionRequest) -> LLMResponse:
        """Send chat completion request to Bailian API."""
        url = f"{self._config.endpoint}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Convert messages to Bailian format
        messages = []
        for msg in request.messages:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })

        payload = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p
        }

        if request.stop:
            payload["stop"] = request.stop

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        # Parse Bailian response
        choice = data["choices"][0]
        message = choice["message"]

        return LLMResponse(
            text=message.get("content", ""),
            raw=data,
            model=data.get("model", request.model),
            provider="bailian",
            finish_reason=choice.get("finish_reason", "stop"),
            usage=data.get("usage", {})
        )

    def supports_function_calling(self, model_id: str) -> bool:
        model = self.get_model(model_id)
        if model:
            return model.supports_function_calling
        return False