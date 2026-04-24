import asyncio
import logging
import json
from typing import Dict, Any, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger("across_agents_assistant.mcp")

class MCPClientManager:
    """Manages connections to multiple MCP servers."""
    def __init__(self):
        self.sessions: Dict[str, ClientSession] = {}
        self._exit_stacks = {}
        self.server_configs: Dict[str, StdioServerParameters] = {}
        self.server_tools: Dict[str, List[Dict[str, Any]]] = {}

    def register_server(self, server_id: str, command: str, args: List[str], env: Optional[Dict[str, str]] = None):
        """Register a new MCP server configuration."""
        self.server_configs[server_id] = StdioServerParameters(
            command=command,
            args=args,
            env=env
        )

    async def connect_server(self, server_id: str):
        """Connect to an MCP server and fetch its tools."""
        if server_id not in self.server_configs:
            logger.error(f"MCP server {server_id} not registered.")
            return False

        if server_id in self.sessions:
            logger.info(f"Already connected to MCP server {server_id}.")
            return True

        params = self.server_configs[server_id]
        logger.info(f"Connecting to MCP server {server_id} via {params.command} {' '.join(params.args)}")
        
        try:
            # We use AsyncExitStack manually to manage the context managers
            from contextlib import AsyncExitStack
            stack = AsyncExitStack()
            self._exit_stacks[server_id] = stack
            
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            
            self.sessions[server_id] = session
            logger.info(f"Successfully connected and initialized MCP server {server_id}.")
            
            # Fetch tools
            tools_response = await session.list_tools()
            self.server_tools[server_id] = []
            for t in tools_response.tools:
                # Convert the tool definition to our internal format
                self.server_tools[server_id].append({
                    "name": f"{server_id}__{t.name}", # Prefix with server_id to avoid conflicts
                    "description": t.description or "",
                    "parameters": t.inputSchema,
                    "risk_level": "medium", # Default to medium for external tools
                    "original_name": t.name
                })
            logger.info(f"Fetched {len(self.server_tools[server_id])} tools from {server_id}.")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to MCP server {server_id}: {e}")
            if server_id in self._exit_stacks:
                await self._exit_stacks[server_id].aclose()
                del self._exit_stacks[server_id]
            return False

    async def disconnect_server(self, server_id: str):
        """Disconnect from an MCP server."""
        if server_id in self.sessions:
            del self.sessions[server_id]
        if server_id in self._exit_stacks:
            await self._exit_stacks[server_id].aclose()
            del self._exit_stacks[server_id]
        if server_id in self.server_tools:
            del self.server_tools[server_id]
        logger.info(f"Disconnected from MCP server {server_id}.")

    async def call_tool(self, server_id: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool on a connected MCP server."""
        if server_id not in self.sessions:
            logger.error(f"Cannot call tool: not connected to {server_id}")
            return f"Error: Not connected to MCP server {server_id}"
            
        session = self.sessions[server_id]
        logger.info(f"Calling MCP tool {tool_name} on {server_id} with args {arguments}")
        
        try:
            result = await session.call_tool(tool_name, arguments=arguments)
            # The result is a CallToolResult object which contains a list of contents
            texts = []
            for content in result.content:
                if content.type == "text":
                    texts.append(content.text)
                else:
                    texts.append(f"[{content.type} content]")
                    
            if result.isError:
                logger.warning(f"MCP tool {tool_name} returned error: {texts}")
                return f"Error from tool: {''.join(texts)}"
                
            return "\n".join(texts)
        except Exception as e:
            logger.error(f"Exception calling MCP tool {tool_name}: {e}")
            return f"Error executing tool: {e}"

    def get_all_tools_schema(self) -> List[Dict[str, Any]]:
        """Get all tools from all connected servers in the format expected by the LLM."""
        all_tools = []
        for tools in self.server_tools.values():
            for t in tools:
                all_tools.append({
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                    "risk_level": t["risk_level"]
                })
        return all_tools

# Global instance
mcp_manager = MCPClientManager()
