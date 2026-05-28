import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock

from across_agents_assistant.harness import (
    post_process_llm_response,
    execute_tool_with_retry,
    OutputClassification,
    MAX_AGENT_LOOP_ITERATIONS,
)
from across_agents_assistant.harness.errors import InfraError, LogicError


class FakeReply:
    def __init__(self, text=None, tool_calls=None):
        self.text = text
        self.tool_calls = tool_calls or []


class FakeToolDef:
    def __init__(self, handler):
        self.handler = handler


@pytest.mark.asyncio
async def test_post_process_poisoned_tool_mention():
    """Detect poisoned output: text mentions tool but no structured tool_calls."""
    reply = FakeReply(text="请求调用工具：edit_file", tool_calls=[])
    processed = post_process_llm_response(reply)
    assert processed.classification == OutputClassification.POISONED_TEXT_TOOL_MENTION
    assert processed.should_retry is True
    assert processed.retry_count == 2


@pytest.mark.asyncio
async def test_post_process_iteration_limit():
    """Detect iteration limit marker."""
    reply = FakeReply(text="I reached the iteration limit", tool_calls=[])
    processed = post_process_llm_response(reply)
    assert processed.classification == OutputClassification.ITERATION_LIMIT
    assert processed.should_retry is False


@pytest.mark.asyncio
async def test_post_process_empty_output():
    """Detect empty output."""
    reply = FakeReply(text="", tool_calls=[])
    processed = post_process_llm_response(reply)
    assert processed.classification == OutputClassification.EMPTY_OUTPUT
    assert processed.should_retry is True


@pytest.mark.asyncio
async def test_post_process_normal_output():
    """Normal output should not trigger any detection."""
    reply = FakeReply(text="这是正常的回复内容", tool_calls=[])
    processed = post_process_llm_response(reply)
    assert processed.classification == OutputClassification.NORMAL
    assert processed.should_retry is False


@pytest.mark.asyncio
async def test_post_process_with_tool_calls():
    """When tool_calls exist, skip all heuristics."""
    reply = FakeReply(text="请求调用工具：edit_file", tool_calls=[{"name": "edit_file"}])
    processed = post_process_llm_response(reply)
    assert processed.classification == OutputClassification.NORMAL


@pytest.mark.asyncio
async def test_execute_tool_retry_infra_error():
    """Infrastructure errors should be retried."""
    call_count = 0

    def failing_handler():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise TimeoutError("Simulated timeout")
        return "success"

    tool_def = FakeToolDef(failing_handler)
    result = await execute_tool_with_retry(
        tool_def=tool_def,
        tool_args={},
        is_mcp=False,
        mcp_manager=None,
        max_retries=2,
    )
    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_execute_tool_no_retry_logic_error():
    """Logic errors should NOT be retried."""
    call_count = 0

    def failing_handler():
        nonlocal call_count
        call_count += 1
        raise ValueError("Simulated logic error")

    tool_def = FakeToolDef(failing_handler)
    with pytest.raises(LogicError):
        await execute_tool_with_retry(
            tool_def=tool_def,
            tool_args={},
            is_mcp=False,
            mcp_manager=None,
            max_retries=2,
        )
    assert call_count == 1


@pytest.mark.asyncio
async def test_execute_tool_retry_exhausted():
    """When all retries are exhausted, raise InfraError."""
    def always_fail():
        raise ConnectionError("Simulated connection error")

    tool_def = FakeToolDef(always_fail)
    with pytest.raises(InfraError):
        await execute_tool_with_retry(
            tool_def=tool_def,
            tool_args={},
            is_mcp=False,
            mcp_manager=None,
            max_retries=2,
        )


@pytest.mark.asyncio
async def test_max_agent_loop_iterations_constant():
    """Verify the iteration limit constant is set correctly."""
    assert MAX_AGENT_LOOP_ITERATIONS == 20
