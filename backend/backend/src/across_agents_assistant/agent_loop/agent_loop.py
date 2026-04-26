import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .config import LoopConfig, LoopResult

logger = logging.getLogger("across_agents_assistant.agent_loop")

@dataclass
class ChatMessage:
    role: str
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None

class AgentLoop:
    """Agent 推理循环"""

    def __init__(self, llm_client: Any, tool_registry: Any, config: LoopConfig = None):
        self.llm = llm_client
        self.tools = tool_registry
        self.config = config or LoopConfig()

    async def run(self, user_message: str, context: Dict[str, Any] = None) -> LoopResult:
        """
        执行推理循环。
        """
        messages = [ChatMessage(role="user", content=user_message)]
        iterations = 0
        tool_calls = []

        while iterations < self.config.max_iterations:
            # 调用 LLM
            response = await self._call_llm(messages)

            # 检查是否需要调用工具
            if not response.get('tool_calls'):
                return LoopResult(
                    final_answer=response.get('content', ''),
                    iterations=iterations,
                    tool_calls=tool_calls,
                    success=True
                )

            # 执行工具调用
            for tool_call in response['tool_calls']:
                result = self._execute_tool(tool_call)
                tool_calls.append(tool_call)

                messages.append(ChatMessage(
                    role="assistant",
                    content="",
                    tool_calls=[tool_call]
                ))
                messages.append(ChatMessage(
                    role="tool",
                    content=result,
                    tool_call_id=tool_call.get('id')
                ))

            iterations += 1

        return LoopResult(
            final_answer="已达到最大迭代次数",
            iterations=iterations,
            tool_calls=tool_calls,
            success=False,
            error="max_iterations_exceeded"
        )

    async def _call_llm(self, messages: List[ChatMessage]) -> Dict[str, Any]:
        """调用 LLM"""
        try:
            return await self.llm.chat(
                messages=[{'role': m.role, 'content': m.content} for m in messages],
                tools=self.tools.get_all_tools_schema() if self.tools else None
            )
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return {'content': f'Error: {str(e)}', 'tool_calls': []}

    def _execute_tool(self, tool_call: Dict[str, Any]) -> str:
        """执行单个工具调用"""
        tool_name = tool_call.get('name')
        params = tool_call.get('arguments', {})

        tool = self.tools.get_tool(tool_name) if self.tools else None
        if not tool:
            return f"Error: unknown tool {tool_name}"

        try:
            result = tool.handler(**params)
            return str(result)
        except Exception as e:
            return f"Error: {str(e)}"