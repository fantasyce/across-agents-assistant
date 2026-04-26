import pytest
import sys
sys.path.insert(0, 'src')

from across_agents_assistant.llm_gateway.bailian_adapter import BailianAdapter
from across_agents_assistant.llm_gateway.config import LLMProviderConfig, ModelInfo

@pytest.fixture
def bailian_config():
    return LLMProviderConfig(
        provider_id="bailian",
        name="Bailian (Ali)",
        api_key_env="BAILIAN_API_KEY",
        endpoint="https://dashscope.aliyuncs.com/compatible-mode/v1",
        models=[
            ModelInfo("qwen-plus", "Qwen Plus", supports_function_calling=True, max_tokens=32768),
        ]
    )

def test_adapter_initialization(bailian_config):
    adapter = BailianAdapter(bailian_config)
    assert adapter.provider_id == "bailian"
    assert adapter.name == "Bailian (Ali)"

def test_supports_function_calling(bailian_config):
    adapter = BailianAdapter(bailian_config)
    assert adapter.supports_function_calling("qwen-plus") == True