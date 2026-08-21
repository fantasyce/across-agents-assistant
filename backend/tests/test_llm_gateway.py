import pytest

from across_agents_assistant.llm_gateway.base_adapter import ChatCompletionRequest, LLMResponse
from across_agents_assistant.llm_gateway.base_adapter import ChatMessage
from across_agents_assistant.llm_gateway.config import LLMConfig, LLMProviderConfig, ModelInfo
from across_agents_assistant.llm_gateway.gateway import LLMGateway
from across_agents_assistant.llm_gateway.minimax_adapter import MiniMaxAdapter


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


def test_adapter_timeout_seconds_can_be_configured(monkeypatch):
    adapter = MiniMaxAdapter(LLMProviderConfig(
        provider_id="minimax",
        name="MiniMax",
        api_key_env="MINIMAX_API_KEY",
        endpoint="https://example.invalid",
    ))

    assert adapter.timeout_seconds(default=180.0) == 180.0

    monkeypatch.setenv("ACROSS_LLM_CHAT_TIMEOUT_SECONDS", "210")
    assert adapter.timeout_seconds(default=180.0) == 210.0

    monkeypatch.setenv("ACROSS_LLM_MINIMAX_CHAT_TIMEOUT_SECONDS", "240")
    assert adapter.timeout_seconds(default=180.0) == 240.0


def test_request_timeout_seconds_overrides_provider_default(monkeypatch):
    monkeypatch.setenv("ACROSS_LLM_MINIMAX_CHAT_TIMEOUT_SECONDS", "210")
    adapter = MiniMaxAdapter(LLMProviderConfig(
        provider_id="minimax",
        name="MiniMax",
        api_key_env="MINIMAX_API_KEY",
        endpoint="https://example.invalid",
    ))
    request = ChatCompletionRequest(messages=[], model="test", timeout_seconds=45)

    assert adapter.request_timeout_seconds(request, default=180.0) == 45.0
    assert adapter.request_timeout_seconds(
        ChatCompletionRequest(messages=[], model="test"),
        default=180.0,
    ) == 210.0


@pytest.mark.asyncio
async def test_minimax_m3_uses_max_completion_tokens(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{
                    "finish_reason": "stop",
                    "message": {"content": "正常"},
                }],
                "model": "MiniMax-M3",
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
                "base_resp": {"status_code": 0, "status_msg": ""},
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(
        "across_agents_assistant.llm_gateway.minimax_adapter.httpx.AsyncClient",
        FakeAsyncClient,
    )
    adapter = MiniMaxAdapter(LLMProviderConfig(
        provider_id="minimax",
        name="MiniMax",
        api_key_env="MINIMAX_API_KEY",
        endpoint="https://example.invalid/v1",
    ))
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")

    response = await adapter.chat(ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="ping")],
        model="MiniMax-M3",
        max_tokens=64,
        extra_body={"reasoning_split": True, "thinking": {"type": "disabled"}},
    ))

    assert response.text == "正常"
    assert captured["json"]["max_completion_tokens"] == 64
    assert "max_tokens" not in captured["json"]
    assert captured["json"]["thinking"] == {"type": "disabled"}


@pytest.mark.asyncio
async def test_minimax_empty_sensitive_response_is_error(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{
                    "finish_reason": "stop",
                    "message": {"content": ""},
                }],
                "model": "MiniMax-M3",
                "usage": {"prompt_tokens": 2, "completion_tokens": 0, "total_tokens": 2},
                "input_sensitive": False,
                "output_sensitive": True,
                "base_resp": {"status_code": 0, "status_msg": ""},
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(
        "across_agents_assistant.llm_gateway.minimax_adapter.httpx.AsyncClient",
        FakeAsyncClient,
    )
    adapter = MiniMaxAdapter(LLMProviderConfig(
        provider_id="minimax",
        name="MiniMax",
        api_key_env="MINIMAX_API_KEY",
        endpoint="https://example.invalid/v1",
    ))
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")

    with pytest.raises(RuntimeError, match="output sensitivity policy"):
        await adapter.chat(ChatCompletionRequest(
            messages=[ChatMessage(role="user", content="ping")],
            model="MiniMax-M3",
            max_tokens=64,
        ))


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
