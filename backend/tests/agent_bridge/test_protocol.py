import pytest
import json
from across_agents_assistant.agent_bridge.protocol import (
    MessageType, AgentMessage, AgentResponse, InvokeRequest
)

def test_message_type_enum():
    assert MessageType.INVOKE.value == "invoke"
    assert MessageType.RESPONSE.value == "response"
    assert MessageType.HEARTBEAT.value == "heartbeat"
    assert MessageType.CANCEL.value == "cancel"
    assert MessageType.ERROR.value == "error"

def test_agent_message_creation():
    msg = AgentMessage(
        message_id="msg-123",
        message_type=MessageType.INVOKE,
        agent_id="openclaw",
        payload={"content": "Hello"},
        metadata={"task_id": "task-1"}
    )
    assert msg.message_id == "msg-123"
    assert msg.message_type == MessageType.INVOKE
    assert msg.agent_id == "openclaw"
    assert msg.payload["content"] == "Hello"

def test_agent_message_to_json():
    msg = AgentMessage(
        message_id="msg-123",
        message_type=MessageType.INVOKE,
        agent_id="openclaw",
        payload={"content": "Hello"}
    )
    json_str = msg.to_json()
    parsed = json.loads(json_str)
    assert parsed["message_id"] == "msg-123"
    assert parsed["message_type"] == "invoke"

def test_agent_message_from_json():
    json_str = '{"message_id":"msg-123","message_type":"invoke","agent_id":"openclaw","payload":{"content":"Hello"},"metadata":{}}'
    msg = AgentMessage.from_json(json_str)
    assert msg.message_id == "msg-123"
    assert msg.message_type == MessageType.INVOKE
    assert msg.payload["content"] == "Hello"

def test_invoke_request_creation():
    req = InvokeRequest(
        request_id="req-1",
        agent_id="openclaw",
        message="帮我分析这个代码",
        context={"frontmost_app": "Chrome"}
    )
    assert req.request_id == "req-1"
    assert req.agent_id == "openclaw"
    assert "frontmost_app" in req.context

def test_agent_response_fields():
    resp = AgentResponse(
        message_id="msg-123",
        request_id="req-1",
        success=True,
        output="分析完成",
        agent_id="openclaw"
    )
    assert resp.success == True
    assert resp.output == "分析完成"