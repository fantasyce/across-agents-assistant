# LLM Gateway Specification

## Overview

LLM Gateway provides a unified interface for multiple LLM providers, enabling the App to act as an LLM-powered Manager.

## Supported Providers

| Provider | Model | Function Calling | Max Tokens |
|----------|-------|-----------------|------------|
| MiniMax | MiniMax-Text-01 | Yes | 32,000 |
| MiniMax | abab6.5s-chat | Yes | 24,576 |
| Bailian | qwen-plus | Yes | 32,768 |
| Bailian | qwen-max | Yes | 8,192 |
| Bailian | qwen-turbo | Yes | 8,192 |
| Deepseek | deepseek-chat | Yes | 64,000 |
| Deepseek | deepseek-coder | Yes | 16,384 |

## Architecture

```
LLMGateway
├── MinimaxAdapter
├── BailianAdapter
└── DeepseekAdapter
```

## API Endpoints

- `GET /api/llm/providers` - List all providers with status
- `GET /api/llm/models/{provider_id}` - List models for a provider
- `POST /api/llm/switch` - Switch provider
- `GET /api/llm/status` - Get current provider status
- `POST /api/llm/chat` - Direct chat (for testing)

## Usage

```python
from across_agents_assistant.llm_gateway import get_gateway

gateway = get_gateway()

# Simple chat
response = await gateway.chat(
    message="Hello",
    system_prompt="You are a helpful assistant",
    context={"frontmost_app": "Chrome"}
)
print(response.text)

# Switch provider
gateway.switch_provider("bailian")

# List providers
providers = gateway.list_providers()
```

## Configuration

Configuration is stored in `~/Library/Application Support/AcrossAgentsAssistant/llm_config.json`

API keys are loaded from:
1. Environment variables (e.g., MINIMAX_API_KEY)
2. macOS Keychain as fallback

## Error Handling

- Automatic fallback to secondary providers on failure
- Graceful degradation when API keys are missing
- Logging of all LLM calls with provider/model info
