import json
from typing import Dict, Any, Callable, List
from .mcp_client import mcp_manager

class ToolDefinition:
    def __init__(self, name: str, description: str, parameters: Dict[str, Any], risk_level: str, handler: Callable):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.risk_level = risk_level # "low", "medium", "high"
        self.handler = handler

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition):
        self.tools[tool.name] = tool

    def get_tool(self, name: str) -> ToolDefinition:
        return self.tools.get(name)

    def get_all_tools_schema(self) -> List[Dict[str, Any]]:
        schemas = []
        # Add local tools
        for tool in self.tools.values():
            schemas.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "risk_level": tool.risk_level
            })

        # Add dynamic MCP tools
        schemas.extend(mcp_manager.get_all_tools_schema())
        return schemas

registry = ToolRegistry()
