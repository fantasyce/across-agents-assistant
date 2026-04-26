"""
LLM Gateway Adapter for AgentLoop.

Bridges the LLMGateway interface with AgentLoop's expected interface.
"""
import logging
from typing import List, Dict, Any, Optional

from .config import LoopConfig, LoopResult

logger = logging.getLogger("across_agents_assistant.agent_loop.adapter")


class LLMGatewayAdapter:
    """
    Adapter that bridges LLMGateway with AgentLoop.

    AgentLoop expects: llm.chat(messages=[...], tools=[...])
    LLMGateway provides: gateway.chat(message=..., system_prompt=..., context=...)
    """

    def __init__(self, llm_gateway: Any):
        """
        Initialize with an LLMGateway instance.

        Args:
            llm_gateway: An LLMGateway instance
        """
        self._gateway = llm_gateway
        self._tools = None

    def set_tools(self, tools: Any) -> None:
        """Set the tool registry for function calling."""
        self._tools = tools

    async def chat(self, messages: List[Dict[str, str]], tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Bridge method that converts AgentLoop's interface to LLMGateway's interface.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: List of tool definitions

        Returns:
            Dict with 'content' and 'tool_calls' keys
        """
        if not messages:
            return {'content': '', 'tool_calls': []}

        # Get the last user message
        last_message = messages[-1]
        user_message = last_message.get('content', '')

        # Build system prompt from messages
        system_parts = []
        for msg in messages[:-1]:
            if msg.get('role') == 'system':
                system_parts.append(msg.get('content', ''))

        system_prompt = '\n\n'.join(system_parts) if system_parts else None

        # Call LLM Gateway
        try:
            response = await self._gateway.chat(
                message=user_message,
                system_prompt=system_prompt,
                context=None
            )

            # Convert LLMResponse to AgentLoop format
            result = {
                'content': response.text,
                'tool_calls': []
            }

            # Check if response has function calls in raw data
            # Different providers have different formats
            raw = response.raw if hasattr(response, 'raw') else {}

            # Try OpenAI-style function calls
            if 'choices' in raw and raw['choices']:
                choice = raw['choices'][0]
                if 'message' in choice:
                    msg = choice['message']
                    if 'tool_calls' in msg:
                        result['tool_calls'] = self._parse_tool_calls(msg['tool_calls'])
                    elif 'function_call' in msg:
                        fc = msg['function_call']
                        result['tool_calls'] = [{
                            'id': f"call-{hash(fc['name'])}",
                            'name': fc['name'],
                            'arguments': fc.get('arguments', '{}')
                        }]

            return result

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return {'content': f'Error: {str(e)}', 'tool_calls': []}

    def _parse_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """Parse tool calls from LLM response to AgentLoop format."""
        parsed = []
        for tc in tool_calls:
            if isinstance(tc, dict):
                # OpenAI format
                tc_id = tc.get('id', f"call-{hash(str(tc))}")
                func = tc.get('function', {})
                name = func.get('name', '')
                arguments = func.get('arguments', '{}')

                if isinstance(arguments, str):
                    arguments = arguments

                parsed.append({
                    'id': tc_id,
                    'name': name,
                    'arguments': arguments
                })
            else:
                # Already in correct format
                parsed.append(tc)

        return parsed
