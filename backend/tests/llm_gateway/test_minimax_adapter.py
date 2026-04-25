import pytest
import sys
sys.path.insert(0, 'src')

from across_agents_assistant.llm_gateway.minimax_adapter import MiniMaxAdapter
from across_agents_assistant.llm_gateway.config import LLMProviderConfig, ModelInfo

@pytest.fixture
def minimax_config():
    return LLMProviderConfig(
        provider_id="minimax",
        name="MiniMax",
        api_key_env="MINIMAX_API_KEY",
        endpoint="https://api.minimax.chat/v1",
        models=[
            ModelInfo("MiniMax-Text-01", "MiniMax Text 01", supports_function_calling=True, max_tokens=32000),
        ]
    )

def test_adapter_initialization(minimax_config):
    adapter = MiniMaxAdapter(minimax_config)
    assert adapter.provider_id == "minimax"
    assert adapter.name == "MiniMax"

def test_supports_function_calling(minimax_config):
    adapter = MiniMaxAdapter(minimax_config)
    assert adapter.supports_function_calling("MiniMax-Text-01") == True
    assert adapter.supports_function_calling("unknown-model") == False

@pytest.mark.asyncio
async def test_chat_request_structure(minimax_config):
    from across_agents_assistant.llm_gateway.base_adapter import ChatCompletionRequest, ChatMessage
    adapter = MiniMaxAdapter(minimax_config)
    request = ChatCompletionRequest(
        messages=[ChatMessage(role="user", content="Hello")],
        model="MiniMax-Text-01"
    )
    assert request.model == "MiniMax-Text-01"