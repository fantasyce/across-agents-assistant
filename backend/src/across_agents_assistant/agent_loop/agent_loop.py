import asyncio
import json
import logging
import uuid
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from dataclasses import dataclass

from .config import LoopConfig, LoopResult

if TYPE_CHECKING:
    from across_agents_assistant.persistence.audit_logger import AuditLogger

logger = logging.getLogger("across_agents_assistant.agent_loop")

@dataclass
class ChatMessage:
    role: str
    content: Optional[str]
    name: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None

class ChatToolLoop:
    """Chat-oriented LLM tool-calling loop used by AAA host agents."""

    def __init__(
        self,
        llm_client: Any,
        tool_registry: Any,
        config: LoopConfig = None,
        audit_logger: Optional["AuditLogger"] = None,
        tool_executor: Any = None,
    ):
        self.llm = llm_client
        self.tools = tool_registry
        self.config = config or LoopConfig()
        self._audit_logger = audit_logger
        self._tool_executor = tool_executor
        self._task_id = str(uuid.uuid4())[:8]

    async def run(self, user_message: str, context: Dict[str, Any] = None) -> LoopResult:
        """
        执行推理循环。
        """
        messages = [ChatMessage(role="user", content=user_message)]
        iterations = 0
        tool_calls = []
        tool_results = []

        while iterations < self.config.max_iterations:
            # 调用 LLM
            response = await self._call_llm(messages)
            assistant_message = self._message_from_response(response)

            # 检查是否需要调用工具
            if not response.get('tool_calls'):
                unresolved_failure = any(not item.get("success", False) for item in tool_results)
                return LoopResult(
                    final_answer=response.get('content', ''),
                    iterations=iterations,
                    tool_calls=tool_calls,
                    success=not unresolved_failure,
                    tool_results=tool_results,
                    error="tool_execution_failed" if unresolved_failure else None,
                )

            # 执行工具调用
            messages.append(assistant_message)
            for tool_call in response['tool_calls']:
                result = self._execute_tool(tool_call, context or {})
                tool_calls.append(tool_call)
                tool_results.append(result)

                messages.append(ChatMessage(
                    role="tool",
                    content=result["message"],
                    tool_call_id=tool_call.get('id')
                ))

            iterations += 1

        return LoopResult(
            final_answer="已达到最大迭代次数",
            iterations=iterations,
            tool_calls=tool_calls,
            tool_results=tool_results,
            success=False,
            error="max_iterations_exceeded"
        )

    async def _call_llm(self, messages: List[ChatMessage]) -> Dict[str, Any]:
        """调用 LLM"""
        try:
            return await self.llm.chat(
                messages=[self._serialize_message(m) for m in messages],
                tools=self.tools.get_all_tools_schema() if self.tools else None
            )
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return {
                'content': f'Error: {str(e)}',
                'tool_calls': [],
                'assistant_message': {
                    'role': 'assistant',
                    'content': f'Error: {str(e)}',
                },
            }

    @staticmethod
    def _serialize_message(message: ChatMessage) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"role": message.role, "content": message.content}
        if message.name:
            payload["name"] = message.name
        if message.tool_calls:
            payload["tool_calls"] = message.tool_calls
        if message.tool_call_id:
            payload["tool_call_id"] = message.tool_call_id
        return payload

    @staticmethod
    def _message_from_response(response: Dict[str, Any]) -> ChatMessage:
        raw_message = dict(response.get("assistant_message") or {})
        return ChatMessage(
            role=raw_message.get("role", "assistant"),
            content=raw_message.get("content", response.get("content", "")),
            name=raw_message.get("name"),
            tool_calls=raw_message.get("tool_calls"),
            tool_call_id=raw_message.get("tool_call_id"),
        )

    def _execute_tool(self, tool_call: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """执行单个工具调用"""
        tool_name = tool_call.get('name')
        params = tool_call.get('arguments', {})
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                return {
                    "success": False,
                    "tool_name": tool_name,
                    "arguments": {},
                    "message": f"Error: invalid JSON arguments for tool {tool_name}",
                    "metadata": {},
                }

        # Log tool call to audit logger if available
        if self._audit_logger:
            try:
                self._audit_logger.log_tool_call(
                    task_id=self._task_id,
                    tool_name=tool_name,
                    risk_level='medium',  # Default risk level for chat tool loop tools
                    params=params
                )
            except Exception as e:
                logger.warning(f"Failed to log tool call: {e}")

        tool = self.tools.get_tool(tool_name) if self.tools else None
        if not tool:
            return {
                "success": False,
                "tool_name": tool_name,
                "arguments": params,
                "message": f"Error: unknown tool {tool_name}",
                "metadata": {},
            }

        try:
            if self._tool_executor:
                result = self._tool_executor.execute_tool(
                    tool_name=tool_name,
                    params=params,
                    task_id=context.get("task_id", self._task_id),
                    subtask_id=context.get("subtask_id", self._task_id),
                    agent_id=context.get("agent_id", "cloud-tool-agent"),
                    user_description=context.get("user_description", ""),
                    plan_summary=context.get("plan_summary", ""),
                    context_sources=context.get("context_sources", []),
                )
                if result.approved_request_id:
                    return {
                        "success": False,
                        "tool_name": tool_name,
                        "arguments": params,
                        "message": (
                            f"Error: tool {tool_name} requires approval "
                            f"(request_id={result.approved_request_id})"
                        ),
                        "metadata": {"approved_request_id": result.approved_request_id},
                    }
                return {
                    "success": result.success,
                    "tool_name": tool_name,
                    "arguments": params,
                    "message": result.output if result.success else f"Error: {result.error}",
                    "metadata": dict(result.metadata or {}),
                }

            result = tool.handler(**params)
            return {
                "success": True,
                "tool_name": tool_name,
                "arguments": params,
                "message": str(result),
                "metadata": {},
            }
        except Exception as e:
            return {
                "success": False,
                "tool_name": tool_name,
                "arguments": params,
                "message": f"Error: {str(e)}",
                "metadata": {},
            }
