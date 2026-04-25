import json
import logging
import os
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

logger = logging.getLogger("across_agents_assistant")

class OrchestratorResponse:
    def __init__(self, text: Optional[str] = None, tool_calls: Optional[List[Dict[str, Any]]] = None):
        self.text = text
        self.tool_calls = tool_calls or []

class OrchestratorClient:
    def __init__(self, config_manager):
        self.manager = config_manager
        
    def _get_openai_client(self, agent_config):
        api_key = agent_config.get("api_key", "").strip()
        base_url = agent_config.get("base_url", "").strip()
        agent_id = agent_config.get("id", "")
        
        if not api_key or api_key == "sk-dummy":
            if "minimax" in base_url or agent_id == "minimax":
                api_key = os.environ.get("MINIMAX_API_KEY", "sk-dummy")
            elif "deepseek" in base_url or agent_id == "deepseek":
                api_key = os.environ.get("DEEPSEEK_API_KEY", "sk-dummy")
            else:
                api_key = os.environ.get("OPENAI_API_KEY", "sk-dummy")
                
        if not base_url:
            base_url = "https://api.openai.com/v1"
            
        return AsyncOpenAI(api_key=api_key, base_url=base_url)

    def _get_anthropic_client(self, agent_config):
        api_key = agent_config.get("api_key", "").strip() or "sk-dummy"
        base_url = agent_config.get("base_url", "").strip()
        agent_id = agent_config.get("id", "")
        
        if api_key == "sk-dummy":
            if "minimax" in base_url or agent_id == "minimax":
                api_key = os.environ.get("MINIMAX_API_KEY", "sk-dummy")
            else:
                api_key = os.environ.get("ANTHROPIC_API_KEY", "sk-dummy")
                
        if base_url:
            return AsyncAnthropic(api_key=api_key, base_url=base_url)
        return AsyncAnthropic(api_key=api_key)

    async def chat(self, agent_id: str, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> OrchestratorResponse:
        agent_config = self.manager.get_agent_config(agent_id)
        if not agent_config:
            return OrchestratorResponse(text=f"未找到智能体配置: {agent_id}")
            
        # inject agent_id into config so we can check it
        agent_config["id"] = agent_id
        
        provider_type = agent_config.get("type", "openai_compatible")
        model = agent_config.get("model", "")
        
        # Override the system prompt universally to prevent model hallucination
        strong_system_prompt = "You are a helpful AI assistant running in a macOS desktop environment. You are NOT Claude. You are NOT Hermes. You are NOT OpenClaw. You are the Across Agents Copilot, a versatile tool for macOS users. Do not use conversational filler, just act."
        
        # Replace or add the strong system prompt
        has_system = False
        for m in messages:
            if m["role"] == "system":
                m["content"] = strong_system_prompt
                has_system = True
                break
        
        if not has_system:
            messages.insert(0, {"role": "system", "content": strong_system_prompt})
        
        # Check if API key is configured (unless it's local like ollama which might not need one, but let's just warn)
        if not agent_config.get("api_key"):
            logger.warning(f"Agent {agent_id} 没有配置 API Key。可能导致请求失败。")

        try:
            if provider_type == "openai_compatible":
                return await self._chat_openai(agent_config, model, messages, tools)
            elif provider_type == "anthropic":
                return await self._chat_anthropic(agent_config, model, messages, tools)
            else:
                return OrchestratorResponse(text=f"不支持的提供商类型: {provider_type}")
        except Exception as e:
            logger.error(f"LLM API 请求失败: {e}", exc_info=True)
            return OrchestratorResponse(text=f"请求大模型失败: {str(e)}")

    async def _chat_openai(self, config, model, messages, tools):
        client = self._get_openai_client(config)
        
        # Translate tools to OpenAI format
        openai_tools = []
        for t in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {"type": "object", "properties": {}})
                }
            })
            
        # Ensure system prompt is handled (Anthropic vs OpenAI differs slightly, but OpenAI handles 'system' role fine)
        
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": 0.7
        }
        if openai_tools:
            kwargs["tools"] = openai_tools
            
        response = await client.chat.completions.create(**kwargs)
        
        message = response.choices[0].message
        
        if message.tool_calls:
            parsed_tool_calls = []
            for tc in message.tool_calls:
                parsed_tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments)
                })
            return OrchestratorResponse(text=message.content, tool_calls=parsed_tool_calls)
            
        return OrchestratorResponse(text=message.content)

    async def _chat_anthropic(self, config, model, messages, tools):
        client = self._get_anthropic_client(config)
        
        system_prompts = []
        # Format messages for Anthropic
        # Ensure only user and assistant messages exist
        filtered_messages = []
        for m in messages:
            if m["role"] == "system":
                system_prompts.append(m["content"])
            elif m["role"] in ["user", "assistant"]:
                filtered_messages.append({"role": m["role"], "content": m["content"]})
            elif m["role"] == "tool":
                # Anthropic tool result format
                filtered_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": m.get("tool_call_id", "unknown"),
                            "content": m["content"]
                        }
                    ]
                })
        
        # Merge consecutive messages with same role (Anthropic requires alternating roles)
        merged_messages = []
        for m in filtered_messages:
            if not merged_messages:
                merged_messages.append(m)
            else:
                last = merged_messages[-1]
                if last["role"] == m["role"]:
                    # Merge content
                    if isinstance(last["content"], list) and isinstance(m["content"], list):
                        last["content"].extend(m["content"])
                    elif isinstance(last["content"], str) and isinstance(m["content"], str):
                        last["content"] += f"\n\n{m['content']}"
                    else:
                        # Fallback for mixed types
                        last_str = str(last["content"])
                        m_str = str(m["content"])
                        last["content"] = f"{last_str}\n\n{m_str}"
                else:
                    merged_messages.append(m)
                    
        # Ensure first message is user
        if merged_messages and merged_messages[0]["role"] != "user":
            merged_messages.insert(0, {"role": "user", "content": "Start"})
                    
        anthropic_tools = []
        for t in tools:
            anthropic_tools.append({
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("parameters", {"type": "object", "properties": {}})
            })
            
        kwargs = {
            "model": model,
            "max_tokens": 4096,
            "messages": merged_messages,
            "system": "\n\n".join(system_prompts) if system_prompts else ""
        }
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools
            
        response = await client.messages.create(**kwargs)
        
        text_blocks = []
        tool_calls = []
        
        for block in response.content:
            if block.type == "text":
                text_blocks.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input
                })
                
        return OrchestratorResponse(text="\n\n".join(text_blocks), tool_calls=tool_calls)

