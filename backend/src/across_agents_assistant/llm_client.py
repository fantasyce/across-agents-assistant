import json
import logging
import os
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from .attachments import convert_openai_content_to_anthropic
from .llm_gateway.provider_registry import get_provider_definition

logger = logging.getLogger("across_agents_assistant")

class OrchestratorResponse:
    def __init__(self, text: Optional[str] = None, tool_calls: Optional[List[Dict[str, Any]]] = None):
        self.text = text
        self.tool_calls = tool_calls or []

class OrchestratorClient:
    def __init__(self, config_manager):
        self.manager = config_manager

    @staticmethod
    def _compose_system_prompt(strong_prompt: str, existing_prompt: Optional[str]) -> str:
        existing = (existing_prompt or "").strip()
        if not existing:
            return strong_prompt
        if existing == strong_prompt or existing.startswith(strong_prompt):
            return existing
        return f"{strong_prompt}\n\n{existing}"

    @staticmethod
    def _url_host(base_url: str) -> str:
        try:
            return (urlparse(base_url).hostname or "").lower()
        except ValueError:
            return ""

    @classmethod
    def _is_provider_host(cls, base_url: str, domains: set[str]) -> bool:
        host = cls._url_host(base_url)
        return any(host == domain or host.endswith(f".{domain}") for domain in domains)

    @classmethod
    def _is_minimax_endpoint(cls, base_url: str) -> bool:
        return cls._is_provider_host(base_url, {"minimaxi.com", "minimax.io"})

    @classmethod
    def _is_deepseek_endpoint(cls, base_url: str) -> bool:
        return cls._is_provider_host(base_url, {"deepseek.com"})

    @staticmethod
    def _registry_api_key(agent_id: str) -> str:
        provider = get_provider_definition(agent_id)
        if not provider:
            return ""
        return os.environ.get(provider.api_key_env, "")

    def _get_openai_client(self, agent_config):
        import httpx
        from openai import AsyncOpenAI
        api_key = agent_config.get("api_key", "").strip()
        base_url = agent_config.get("base_url", "").strip()
        agent_id = agent_config.get("id", "")

        if not api_key:
            api_key = self._registry_api_key(agent_id)
        if not api_key:
            if self._is_minimax_endpoint(base_url) or agent_id == "minimax":
                api_key = os.environ.get("MINIMAX_API_KEY", "")
            elif self._is_deepseek_endpoint(base_url) or agent_id == "deepseek":
                api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            else:
                api_key = os.environ.get("OPENAI_API_KEY", "")

        if not base_url:
            base_url = "https://api.openai.com/v1"

        # Create a custom httpx client with trust_env=False to bypass system proxy settings
        # This prevents network tools/VPNs from interfering with gzip decompression
        # Use HTTP/1.1 to avoid HTTP/2 compression issues with some proxies
        http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            trust_env=False,  # Disable to prevent proxy interference
            http1=True,
            http2=False
        )
        return AsyncOpenAI(api_key=api_key, base_url=base_url, http_client=http_client)

    def _get_anthropic_client(self, agent_config):
        from anthropic import AsyncAnthropic
        api_key = agent_config.get("api_key", "").strip()
        base_url = agent_config.get("base_url", "").strip()
        agent_id = agent_config.get("id", "")

        if not api_key:
            api_key = self._registry_api_key(agent_id)
        if not api_key:
            if self._is_minimax_endpoint(base_url) or agent_id == "minimax":
                api_key = os.environ.get("MINIMAX_API_KEY", "")
            else:
                api_key = os.environ.get("ANTHROPIC_API_KEY", "")

        if base_url:
            return AsyncAnthropic(api_key=api_key, base_url=base_url)
        return AsyncAnthropic(api_key=api_key)

    @staticmethod
    def _is_minimax_anthropic(config: Dict[str, Any]) -> bool:
        base = (config.get("base_url") or "").lower()
        aid = (config.get("id") or "").lower()
        return OrchestratorClient._is_minimax_endpoint(base) or aid == "minimax"

    async def chat(self, agent_id: str, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> OrchestratorResponse:
        agent_config = self.manager.get_agent_config(agent_id)
        if not agent_config:
            return OrchestratorResponse(text=f"未找到智能体配置: {agent_id}")

        # inject agent_id into config so we can check it
        agent_config["id"] = agent_id

        provider_type = agent_config.get("type", "openai_compatible")
        model = agent_config.get("model", "")

        # Override the system prompt universally to prevent model hallucination
        strong_system_prompt = "You are a helpful AI assistant running in a macOS desktop environment. You are NOT Claude. You are NOT Hermes. You are NOT OpenClaw. You are the Across Agents Assistant, a versatile tool for macOS users. Do not use conversational filler, just act."

        # Replace or add the strong system prompt
        has_system = False
        for m in messages:
            if m["role"] == "system":
                m["content"] = self._compose_system_prompt(strong_system_prompt, m.get("content"))
                has_system = True
                break

        if not has_system:
            messages.insert(0, {"role": "system", "content": strong_system_prompt})

        if agent_id == "minimax":
            logger.debug(f"Pre-anthropic messages ({len(messages)}):")
            for i, m in enumerate(messages):
                tc = m.get("tool_calls")
                tcid = m.get("tool_call_id")
                c = str(m.get("content", ""))[:80]
                logger.debug(f"  [{i}] role={m['role']}, tc={bool(tc)}, tcid={tcid}, content={c}")

        # Check if API key is configured (unless it's local like ollama which might not need one, but let's just warn)
        if not agent_config.get("api_key") and not self._registry_api_key(agent_id):
            logger.warning(f"Agent {agent_id} 没有配置 API Key。可能导致请求失败。")

        try:
            if provider_type == "openai_compatible":
                return await self._chat_openai(agent_config, model, messages, tools)
            elif provider_type == "anthropic":
                return await self._chat_anthropic(agent_config, model, messages, tools)
            else:
                return OrchestratorResponse(text=f"不支持的提供商类型: {provider_type}")
        except Exception as e:
            error_str = str(e)
            # Check for decompression errors which often indicate network/proxy issues
            if "decompress" in error_str.lower() or "zlib" in error_str.lower():
                logger.error(f"LLM API 请求失败 (可能的网络/代理问题): {e}", exc_info=True)
                return OrchestratorResponse(text=f"请求大模型失败: 网络或代理可能干扰了响应压缩。请检查VPN/代理设置。原始错误: {error_str[:100]}")
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

        # MiniMax OpenAI-compatible API: interleaved thinking is split out with reasoning_split,
        # avoiding empty `content` when the model only emitted internal reasoning on some paths.
        if (config.get("id") or "").lower() == "minimax":
            kwargs["extra_body"] = {"reasoning_split": True}
            kwargs["max_tokens"] = 8192

        response = await client.chat.completions.create(**kwargs)

        message = response.choices[0].message
        text_out = message.content or ""

        if message.tool_calls:
            parsed_tool_calls = []
            for tc in message.tool_calls:
                parsed_tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments)
                })
            if not text_out and getattr(message, "reasoning_details", None):
                try:
                    details = message.reasoning_details
                    if isinstance(details, list) and details and isinstance(details[0], dict):
                        text_out = details[0].get("text") or ""
                except Exception:
                    pass
            return OrchestratorResponse(text=text_out, tool_calls=parsed_tool_calls)

        if not text_out and getattr(message, "reasoning_details", None):
            try:
                details = message.reasoning_details
                if isinstance(details, list) and details and isinstance(details[0], dict):
                    text_out = details[0].get("text") or ""
            except Exception:
                pass

        return OrchestratorResponse(text=text_out)

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
                if m["role"] == "assistant" and m.get("tool_calls"):
                    # Convert OpenAI-format tool_calls to Anthropic tool_use blocks
                    content_blocks = []
                    content_value = convert_openai_content_to_anthropic(m.get("content"))
                    if isinstance(content_value, list):
                        content_blocks.extend(content_value)
                    elif content_value:
                        content_blocks.append({"type": "text", "text": str(content_value)})
                    for tc in m["tool_calls"]:
                        try:
                            args = json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"]
                        except (json.JSONDecodeError, TypeError, KeyError):
                            args = {}
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["function"]["name"],
                            "input": args
                    })
                    filtered_messages.append({"role": "assistant", "content": content_blocks})
                else:
                    filtered_messages.append({
                        "role": m["role"],
                        "content": convert_openai_content_to_anthropic(m["content"]),
                    })
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
                    # Merge content keeping Anthropic-compatible format
                    if isinstance(last["content"], list):
                        if isinstance(m["content"], list):
                            last["content"].extend(m["content"])
                        else:
                            last["content"].append({"type": "text", "text": m["content"]})
                    elif isinstance(m["content"], list):
                        merged_messages.append({"role": m["role"], "content": [{"type": "text", "text": last["content"]}]})
                        last = merged_messages[-1]
                        last["content"].extend(m["content"])
                    else:
                        last["content"] += f"\n\n{m['content']}"
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

        # MiniMax Anthropic-compatible API documents max_tokens upper bound 2048; sending
        # larger values can yield malformed responses (e.g. content=null) while base_resp still succeeds.
        max_tokens = 4096
        if self._is_minimax_anthropic(config):
            max_tokens = min(max_tokens, 2048)

        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": merged_messages,
            "system": "\n\n".join(system_prompts) if system_prompts else ""
        }
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools

        logger.debug(f"Anthropic request: model={model}, messages={len(merged_messages)}, tools={len(anthropic_tools)}")
        for i, m in enumerate(merged_messages):
            content_preview = str(m.get('content', ''))[:100] if isinstance(m.get('content'), str) else f"list[{len(m.get('content', []))}]"
            logger.debug(f"  msg[{i}] role={m.get('role')}, content={content_preview}")

        response = await client.messages.create(**kwargs)

        text_blocks = []
        tool_calls = []

        # MiniMax may return JSON with "content": null on edge cases; the SDK then builds a Message
        # with content=None via model_construct (see anthropic Message repr).
        raw_blocks = response.content
        if raw_blocks is None:
            raw_blocks = []
        if not raw_blocks:
            logger.error(f"Anthropic response has no content: {response}")
            hint = ""
            if self._is_minimax_anthropic(config):
                hint = (
                    " MiniMax M2.x often does this when the request violates documented limits "
                    "(e.g. max_tokens above 2048) or the provider returns an empty body; retry after updating the client."
                )
            label = "MiniMax" if self._is_minimax_anthropic(config) else "LLM"
            return OrchestratorResponse(
                text=f"{label} returned empty response.{hint} Response object: {response}"
            )

        for block in raw_blocks:
            if block.type == "text":
                text_blocks.append(block.text)
            elif block.type == "thinking":
                # MiniMax interleaved thinking; include as fallback when there is no separate text block yet.
                text_blocks.append(block.thinking)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input
                })

        return OrchestratorResponse(text="\n\n".join(text_blocks), tool_calls=tool_calls)
