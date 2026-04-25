import pytest
import sys
sys.path.insert(0, 'src')

from across_agents_assistant.llm_gateway.deepseek_adapter import DeepseekAdapter
from across_agents_assistant.llm_gateway.config import LLMProviderConfig, ModelInfo

@pytest.fixture
def deepseek_config():
    return LLMProviderConfig(
        provider_id="deepseek",
        name="Deepseek",
        api_key_env="DEEPSEEK_API_KEY",
        endpoint="https://api.deepseek.com/v1",
        models=[
            ModelInfo("deepseek-chat", "DeepSeek Chat", supports_function_calling=True, max_tokens=64000),
        ]
    )

def test_adapter_initialization(deepseek_config):
    adapter = DeepseekAdapter(deepseek_config)
    assert adapter.provider_id == "deepseek"
    assert adapter.name == "Deepseek"

def test_supports_function_calling(deepseek_config):
    adapter = DeepseekAdapter(deepseek_config)
    assert adapter.supports_function_calling("deepseek-chat") == True