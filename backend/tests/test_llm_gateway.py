import pytest

from across_agents_assistant.llm_gateway.base_adapter import LLMResponse
from across_agents_assistant.llm_gateway.config import LLMConfig, ModelInfo
from across_agents_assistant.llm_gateway.gateway import LLMGateway


class FailingAdapter:
    def __init__(self, provider_id, error, available=True):
        self.provider_id = provider_id
        self.error = error
        self.available = available

    def is_available(self):
        return self.available

    def list_models(self):
        return [ModelInfo(model_id=f"{self.provider_id}-model", name=self.provider_id)]

    async def chat(self, _request):
        raise self.error


class PassingAdapter:
    def is_available(self):
        return True

    def list_models(self):
        return [ModelInfo(model_id="fallback-model", name="fallback")]

    async def chat(self, _request):
        return LLMResponse(
            text="ok",
            raw={},
            model="fallback-model",
            provider="fallback",
            finish_reason="stop",
        )


@pytest.mark.asyncio
async def test_gateway_reports_last_fallback_error():
    gateway = LLMGateway(LLMConfig(primary_provider="minimax", fallback_providers=["deepseek"]))
    gateway._current_provider_id = "minimax"
    gateway._adapters = {
        "minimax": FailingAdapter("minimax", ValueError("No API key found for minimax"), available=False),
        "deepseek": FailingAdapter("deepseek", RuntimeError("401 invalid deepseek key")),
    }

    with pytest.raises(RuntimeError, match="401 invalid deepseek key"):
        await gateway.chat("hello")


@pytest.mark.asyncio
async def test_gateway_uses_available_fallback():
    gateway = LLMGateway(LLMConfig(primary_provider="minimax", fallback_providers=["deepseek"]))
    gateway._current_provider_id = "minimax"
    gateway._adapters = {
        "minimax": FailingAdapter("minimax", ValueError("No API key found for minimax"), available=False),
        "deepseek": PassingAdapter(),
    }

    response = await gateway.chat("hello")

    assert response.text == "ok"
