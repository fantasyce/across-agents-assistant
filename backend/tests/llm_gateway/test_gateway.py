import pytest
import sys
sys.path.insert(0, 'src')

from across_agents_assistant.llm_gateway.gateway import LLMGateway
from across_agents_assistant.llm_gateway.config import load_llm_config

def test_gateway_initialization():
    config = load_llm_config()
    gateway = LLMGateway(config)
    assert gateway is not None
    assert len(gateway.list_providers()) >= 3

def test_list_providers():
    config = load_llm_config()
    gateway = LLMGateway(config)
    providers = gateway.list_providers()
    provider_ids = [p.provider_id for p in providers]
    assert "minimax" in provider_ids
    assert "bailian" in provider_ids
    assert "deepseek" in provider_ids

def test_list_models():
    config = load_llm_config()
    gateway = LLMGateway(config)
    models = gateway.list_models("minimax")
    assert len(models) >= 1
    assert any(m.model_id == "MiniMax-Text-01" for m in models)

def test_switch_provider():
    config = load_llm_config()
    gateway = LLMGateway(config)
    # Note: will return False if API key not available, but should not crash
    result = gateway.switch_provider("bailian")
    # Just verify method exists and can be called

def test_get_current_provider_id():
    config = load_llm_config()
    gateway = LLMGateway(config)
    provider_id = gateway.get_current_provider_id()
    assert provider_id in ["minimax", "bailian", "deepseek"]