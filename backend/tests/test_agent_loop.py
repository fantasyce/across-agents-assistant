from types import SimpleNamespace

import pytest

from across_agents_assistant.agent_loop.adapter import LLMGatewayAdapter
from across_agents_assistant.agent_loop import ChatToolLoop
from across_agents_assistant.agent_loop.config import LoopConfig
from across_agents_assistant.llm_gateway.base_adapter import LLMResponse


class FakeGateway:
    def __init__(self):
        self.calls = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        return LLMResponse(
            text="<think>plan</think>",
            raw={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "<think>plan</think>",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "write_file",
                                        "arguments": '{"path":"out.txt","content":"hello"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            model="MiniMax-M2.7",
            provider="minimax",
            finish_reason="tool_calls",
            usage={},
        )


class ScriptedLLM:
    def __init__(self):
        self.calls = []

    async def chat(self, messages, tools=None):
        self.calls.append({"messages": messages, "tools": tools})
        if len(self.calls) == 1:
            return {
                "content": "<think>inspect</think>",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "name": "write_file",
                        "arguments": {"path": "out.txt", "content": "hello"},
                    }
                ],
                "assistant_message": {
                    "role": "assistant",
                    "content": "<think>inspect</think>",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "write_file",
                                "arguments": '{"path":"out.txt","content":"hello"}',
                            },
                        }
                    ],
                },
            }

        second_messages = messages
        assert second_messages[1]["role"] == "assistant"
        assert second_messages[1]["content"] == "<think>inspect</think>"
        assert second_messages[1]["tool_calls"][0]["id"] == "call-1"
        assert second_messages[2]["role"] == "tool"
        assert second_messages[2]["tool_call_id"] == "call-1"
        return {
            "content": "done",
            "tool_calls": [],
            "assistant_message": {"role": "assistant", "content": "done"},
        }


class ToolRegistryStub:
    def __init__(self):
        self._tool = SimpleNamespace(handler=self._write_file)

    def get_all_tools_schema(self):
        return [
            {
                "name": "write_file",
                "description": "Write a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            }
        ]

    def get_tool(self, tool_name):
        if tool_name == "write_file":
            return self._tool
        return None

    @staticmethod
    def _write_file(path, content):
        return f"wrote {path}: {content}"


@pytest.mark.asyncio
async def test_llm_gateway_adapter_returns_full_assistant_message():
    gateway = FakeGateway()
    adapter = LLMGatewayAdapter(gateway, provider_id="minimax")

    result = await adapter.chat(
        messages=[{"role": "user", "content": "write a file"}],
        tools=[{"name": "write_file", "parameters": {"type": "object", "properties": {}}}],
    )

    assert result["tool_calls"][0]["id"] == "call-1"
    assert result["assistant_message"]["role"] == "assistant"
    assert result["assistant_message"]["tool_calls"][0]["function"]["name"] == "write_file"
    assert gateway.calls[0]["max_tokens"] == 8192


@pytest.mark.asyncio
async def test_chat_tool_loop_preserves_full_assistant_tool_history():
    loop = ChatToolLoop(
        llm_client=ScriptedLLM(),
        tool_registry=ToolRegistryStub(),
        config=LoopConfig(max_iterations=3),
    )

    result = await loop.run("create a file", context={})

    assert result.success is True
    assert result.final_answer == "done"
    assert result.tool_results[0]["success"] is True
