import asyncio
import logging
from typing import Any, Dict, Optional

from .config import MAX_TOOL_RETRIES, RETRY_BACKOFF_BASE
from .errors import classify_error, InfraError, LogicError, UserCancelledError

logger = logging.getLogger("across_agents_assistant.harness")


async def execute_tool_with_retry(
    tool_def,
    tool_args: Dict[str, Any],
    is_mcp: bool,
    mcp_manager=None,
    max_retries: int = MAX_TOOL_RETRIES,
    cancellation_event: Optional[asyncio.Event] = None,
) -> str:
    """Execute a tool (local or MCP) with retry logic for infrastructure errors.

    Args:
        tool_def: The ToolDefinition (for local tools) or None (for MCP).
        tool_args: Arguments to pass to the tool.
        is_mcp: Whether this is an MCP tool call.
        mcp_manager: The MCP client manager (required when is_mcp=True).
        max_retries: Maximum number of retries for infrastructure errors.
        cancellation_event: If set, abort immediately without retry.

    Returns:
        The tool result as a string.

    Raises:
        UserCancelledError: If the cancellation_event is set.
        LogicError: For non-retryable logic errors (re-raised).
        InfraError: If all retries are exhausted.
    """
    last_error = None

    for attempt in range(max_retries + 1):
        if cancellation_event and cancellation_event.is_set():
            raise UserCancelledError("Tool execution cancelled by user")

        try:
            if is_mcp:
                if mcp_manager is None:
                    raise ValueError("mcp_manager is required for MCP tool calls")
                result = await _call_mcp_tool(mcp_manager, tool_def, tool_args)
            else:
                if tool_def is None:
                    raise ValueError("tool_def is required for local tool calls")
                result = tool_def.handler(**tool_args)
            return str(result)

        except Exception as exc:
            harness_err = classify_error(exc)
            last_error = harness_err

            if isinstance(harness_err, UserCancelledError):
                raise

            if isinstance(harness_err, LogicError):
                # Non-retryable: re-raise immediately
                raise harness_err

            if isinstance(harness_err, InfraError):
                if attempt < max_retries:
                    backoff = RETRY_BACKOFF_BASE * (3 ** attempt)
                    logger.warning(
                        "Tool execution failed (%s) on attempt %d/%d, retrying in %.1fs: %s",
                        harness_err.error_type,
                        attempt + 1,
                        max_retries + 1,
                        backoff,
                        harness_err,
                    )
                    await asyncio.sleep(backoff)
                    continue
                else:
                    logger.error(
                        "Tool execution failed after %d attempts (%s): %s",
                        max_retries + 1,
                        harness_err.error_type,
                        harness_err,
                    )
                    raise harness_err

            # Fallback for any other HarnessError
            raise harness_err

    # Should never reach here, but satisfy type checker
    raise last_error or RuntimeError("Unknown tool execution failure")


async def _call_mcp_tool(mcp_manager, tool_name: str, tool_args: Dict[str, Any]):
    """Helper to call an MCP tool with the split name format."""
    parts = tool_name.split("__", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid MCP tool name format: {tool_name}")
    server_id, actual_tool_name = parts
    return await mcp_manager.call_tool(server_id, actual_tool_name, tool_args)
