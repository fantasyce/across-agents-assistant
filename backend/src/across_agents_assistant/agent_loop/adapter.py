"""
LLM Gateway Adapter for ChatToolLoop.

Bridges the LLMGateway interface with ChatToolLoop's expected interface.
"""
import copy
import json
import logging
from typing import List, Dict, Any, Optional

from .config import LoopConfig, LoopResult

logger = logging.getLogger("across_agents_assistant.agent_loop.adapter")


class LLMGatewayAdapter:
    """
    Adapter that bridges LLMGateway with ChatToolLoop.

    ChatToolLoop expects: llm.chat(messages=[...], tools=[...])
    LLMGateway provides: gateway.chat(message=..., system_prompt=..., context=...)
    """

    def __init__(self, llm_gateway: Any, provider_id: Optional[str] = None):
        """
        Initialize with an LLMGateway instance.

        Args:
            llm_gateway: An LLMGateway instance
        """
        self._gateway = llm_gateway
        self._tools = None
        self._provider_id = provider_id

    def set_tools(self, tools: Any) -> None:
        """Set the tool registry for function calling."""
        self._tools = tools

    async def chat(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """
        Bridge method that converts ChatToolLoop's interface to LLMGateway's interface.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: List of tool definitions

        Returns:
            Dict with 'content', 'tool_calls', and 'assistant_message' keys
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
                context=None,
                messages=messages,
                functions=tools,
                provider_id=self._provider_id,
                max_tokens=8192,
            )

            # Convert LLMResponse to ChatToolLoop format
            result = {
                'content': response.text,
                'tool_calls': [],
                'assistant_message': {
                    'role': 'assistant',
                    'content': response.text,
                },
            }

            # Check if response has function calls in raw data
            # Different providers have different formats
            raw = response.raw if hasattr(response, 'raw') else {}

            # Try OpenAI-style function calls
            if 'choices' in raw and raw['choices']:
                choice = raw['choices'][0]
                if 'message' in choice:
                    msg = choice['message']
                    assistant_message = copy.deepcopy(msg)
                    assistant_message.setdefault('role', 'assistant')
                    assistant_message.setdefault('content', response.text)
                    result['assistant_message'] = assistant_message
                    if 'tool_calls' in msg:
                        result['tool_calls'] = self._parse_tool_calls(msg['tool_calls'])
                    elif 'function_call' in msg:
                        fc = msg['function_call']
                        result['tool_calls'] = [{
                            'id': f"call-{hash(fc['name'])}",
                            'name': fc['name'],
                            'arguments': self._normalize_arguments(fc.get('arguments', '{}'))
                        }]

            return result

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return {
                'content': f'Error: {str(e)}',
                'tool_calls': [],
                'assistant_message': {
                    'role': 'assistant',
                    'content': f'Error: {str(e)}',
                },
            }

    def _parse_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """Parse tool calls from LLM response to ChatToolLoop format."""
        parsed = []
        for tc in tool_calls:
            if isinstance(tc, dict):
                # OpenAI format
                tc_id = tc.get('id', f"call-{hash(str(tc))}")
                func = tc.get('function', {})
                name = func.get('name', '')
                arguments = func.get('arguments', '{}')

                parsed.append({
                    'id': tc_id,
                    'name': name,
                    'arguments': self._normalize_arguments(arguments)
                })
            else:
                # Already in correct format
                parsed.append(tc)

        return parsed

    @staticmethod
    def _normalize_arguments(arguments: Any) -> Dict[str, Any]:
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {"raw_arguments": arguments}
        return {}
