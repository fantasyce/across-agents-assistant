import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import asyncio
import os
import subprocess
import shutil

# Patch PATH globally so that npx, uvx, python3 etc can be found even when launched from macOS App
try:
    # Just use standard paths without spawning a shell to save startup time
    current_path = os.environ.get("PATH", "")
    path_parts = [p for p in current_path.split(":") if p]
    extras = [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        os.path.expanduser("~/.local/bin"),
        os.path.expanduser("~/.cargo/bin"),
        os.path.expanduser("~/.bun/bin"),
        os.path.expanduser("~/.nvm/versions/node/v20.0.0/bin"),
        os.path.expanduser("~/.nvm/versions/node/v21.0.0/bin"),
        os.path.expanduser("~/.nvm/versions/node/v22.0.0/bin")
    ]
    
    # Optionally attempt to find node via glob if needed, but standard homebrew is usually enough
    for extra in extras:
        if os.path.isdir(extra) and extra not in path_parts:
            path_parts.insert(0, extra)
    os.environ["PATH"] = ":".join(path_parts)
except Exception as e:
    print(f"Warning: Failed to patch PATH: {e}")

from .agent_manager import AgentManager
from .openclaw.client import UniversalAgentClient
from .openclaw.intent_parser import ToolIntentParser

# Ensure builtin tools are registered
from .tools import builtin_tools
from .tools.tool_registry import registry
from .tools.mcp_client import mcp_manager
from .db.database import db

# LLM Gateway imports
from .llm_gateway.gateway import get_gateway, LLMGateway
from .llm_gateway.config import load_llm_config

# Task Manager imports
from .task_manager.state import TaskState
from .task_manager.dispatcher import TaskDispatcher
from .task_manager.task_decomposer import TaskDecomposer
from .task_manager.models import TaskType, JobStatus

# Global Task Manager instances
_task_state = TaskState()
_task_decomposer: Optional[TaskDecomposer] = None

def get_task_decomposer() -> TaskDecomposer:
    global _task_decomposer
    if _task_decomposer is None:
        from .llm_gateway.gateway import get_gateway
        _task_decomposer = TaskDecomposer(get_gateway())
    return _task_decomposer

_task_dispatcher: Optional[TaskDispatcher] = None

def get_task_dispatcher() -> TaskDispatcher:
    global _task_dispatcher
    if _task_dispatcher is None:
        from .openclaw.client import UniversalAgentClient
        from .agent_manager import AgentManager
        agent_manager = AgentManager()
        openclaw_client = UniversalAgentClient(agent_manager)
        _task_dispatcher = TaskDispatcher(_task_state, openclaw_client)
    return _task_dispatcher

app = FastAPI(title="Across Agents Assistant API")

class MCPConnectRequest(BaseModel):
    server_id: str
    command: str
    args: List[str]
    env: Optional[Dict[str, str]] = None

@app.post("/api/mcp/connect")
async def connect_mcp_server(req: MCPConnectRequest):
    """Register and connect to an MCP server dynamically."""
    try:
        # Intercept built-in Python MCP servers so they run via the bundled backend
        if req.command == "python3" and req.args and req.args[0] == "-m" and req.args[1] in ["mcp_local_kb", "mcp_external_rag"]:
            import sys
            import os
            server_name = req.args[1].replace("mcp_", "") # e.g., "local_kb"
            req.command = sys.executable
            if getattr(sys, 'frozen', False):
                # We are running as PyInstaller bundled binary
                req.args = ["mcp", server_name] + req.args[2:]
            else:
                # We are running in dev mode, sys.executable is python
                # Find the path to main.py
                main_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "main.py"))
                req.args = [main_path, "mcp", server_name] + req.args[2:]
                
        mcp_manager.register_server(req.server_id, req.command, req.args, req.env)
        success = await mcp_manager.connect_server(req.server_id)
        if success:
            return {"status": "success", "message": f"Connected to MCP server: {req.server_id}"}
        else:
            raise HTTPException(status_code=500, detail=f"Failed to connect to MCP server: {req.server_id}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class MCPDisconnectRequest(BaseModel):
    server_id: str

@app.post("/api/mcp/disconnect")
async def disconnect_mcp_server(req: MCPDisconnectRequest):
    """Disconnect an MCP server."""
    try:
        await mcp_manager.disconnect_server(req.server_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class ContextPack(BaseModel):
    frontmost_app: Optional[str] = None
    window_title: Optional[str] = None
    clipboard_text: Optional[str] = None

class ChatRequest(BaseModel):
    text: str
    context: Optional[ContextPack] = None
    session_id: Optional[str] = None
    agent_id: Optional[str] = None

class ChatResponse(BaseModel):
    text: str
    session_id: Optional[str] = None
    audio_path: Optional[str] = None
    requires_approval: bool = False
    approval_request: Optional[Dict[str, Any]] = None

class ApprovalDecision(BaseModel):
    session_id: str
    decision: str # "approve", "reject", "always_allow"
    tool_name: str
    tool_args: Dict[str, Any]
    agent_id: str = "openclaw"

# Global instances
agent_manager = AgentManager()
agent_client = UniversalAgentClient(agent_manager)

@app.get("/api/history/{session_id}")
async def get_chat_history(session_id: str):
    """Retrieve chat history for a specific session"""
    try:
        messages = db.get_messages(session_id)
        return {"session_id": session_id, "messages": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tools", response_model=List[Dict[str, Any]])
async def get_tools():
    local_tools = registry.get_all_tools_schema()
    mcp_tools = mcp_manager.get_all_tools_schema()
    return local_tools + mcp_tools

@app.post("/api/approve", response_model=ChatResponse)
async def approve_tool_execution(req: ApprovalDecision):
    tool_def = registry.get_tool(req.tool_name)
    risk_level = tool_def.risk_level if tool_def else "unknown"
    
    # DB: Log the audit decision
    db.add_audit_log(
        session_id=req.session_id,
        tool_name=req.tool_name,
        tool_args=req.tool_args,
        risk_level=risk_level,
        decision=req.decision
    )
    
    if req.decision == "always_allow":
        db.set_tool_authorization(req.tool_name, True)
    
    if req.decision in ["approve", "always_allow"]:
        # Check if it's an MCP tool or a local tool
        is_mcp = False
        tool_name = req.tool_name
        tool_def = registry.get_tool(tool_name)
        
        if not tool_def:
            schemas = mcp_manager.get_all_tools_schema()
            normalized_target = tool_name.replace("-", "_")
            for t in schemas:
                normalized_schema_name = t["name"].replace("-", "_")
                if normalized_schema_name == normalized_target or normalized_schema_name.endswith(f"__{normalized_target}"):
                    is_mcp = True
                    tool_name = t["name"]
                    break
                
        if is_mcp:
            # Execute MCP tool
            parts = tool_name.split("__", 1)
            if len(parts) == 2:
                server_id = parts[0]
                actual_tool_name = parts[1]
                
                try:
                    result = await mcp_manager.call_tool(server_id, actual_tool_name, req.tool_args)
                    result_text = f"✅ MCP 工具 {tool_name} 执行成功！结果：\n{result}"
                    db.add_message(session_id=req.session_id, role="tool", content=result_text)
                    
                    # Fetch recent chat history to remind the agent of the context
                    recent_messages = db.get_messages(req.session_id)
                    original_question = "用户之前的问题"
                    if len(recent_messages) >= 2:
                        # The last message is usually the tool call, the one before is the user's question
                        for msg in reversed(recent_messages):
                            if msg["role"] == "user":
                                original_question = msg["content"]
                                break

                    continuation_req = ChatRequest(
                        text=f"【工具执行反馈】\n刚才你调用的 MCP 工具 `{tool_name}` 已执行完毕，结果如下：\n<tool_result>\n{result}\n</tool_result>\n\n请基于上述结果继续你的任务。如果还需要其他信息，可以继续调用工具；如果已经收集到足够信息，请直接回答用户最初的问题：\n<original_question>\n{original_question}\n</original_question>",
                        context=None,
                        session_id=req.session_id,
                        agent_id=req.agent_id
                    )
                    return await chat_endpoint(continuation_req)
                except Exception as e:
                    error_text = f"❌ MCP 工具执行失败: {str(e)}"
                    db.add_message(session_id=req.session_id, role="tool", content=error_text)
                    continuation_req = ChatRequest(
                        text=f"MCP 工具 {tool_name} 执行失败，报错信息：\n{str(e)}\n请告诉用户执行失败了，或者尝试其他方法。",
                        context=None,
                        session_id=req.session_id,
                        agent_id=req.agent_id
                    )
                    return await chat_endpoint(continuation_req)
            return ChatResponse(text="MCP工具名称解析失败", session_id=req.session_id)
            
        # Execute local tool
        elif tool_def:
            try:
                # The tool_args coming from the Swift client will be a dict of {key: value}
                # But since we use AnyCodableValue in Swift, simple types like Int/String should map correctly
                result = tool_def.handler(**req.tool_args)
                result_text = f"✅ 工具 {req.tool_name} 执行成功！结果：\n{result}"
                db.add_message(session_id=req.session_id, role="tool", content=result_text)
                
                # --- AUTO CONTINUATION ---
                recent_messages = db.get_messages(req.session_id)
                original_question = "用户之前的问题"
                if len(recent_messages) >= 2:
                    for msg in reversed(recent_messages):
                        if msg["role"] == "user":
                            original_question = msg["content"]
                            break

                continuation_req = ChatRequest(
                    text=f"【工具执行反馈】\n刚才你调用的工具 `{req.tool_name}` 已执行完毕，结果如下：\n<tool_result>\n{result}\n</tool_result>\n\n请基于上述结果继续你的任务。如果还需要其他信息，可以继续调用工具；如果已经收集到足够信息，请直接回答用户最初的问题：\n<original_question>\n{original_question}\n</original_question>",
                    context=None, # We don't need to resend tier1 context for the continuation
                    session_id=req.session_id,
                    agent_id=req.agent_id # Pass through the original agent
                )
                return await chat_endpoint(continuation_req)
                
            except Exception as e:
                error_text = f"❌ 工具执行失败: {str(e)}"
                db.add_message(session_id=req.session_id, role="tool", content=error_text)
                
                continuation_req = ChatRequest(
                    text=f"工具 {req.tool_name} 执行失败，报错信息：\n{str(e)}\n请告诉用户执行失败了，或者尝试其他方法。",
                    context=None,
                    session_id=req.session_id,
                    agent_id=req.agent_id # Pass through the original agent
                )
                return await chat_endpoint(continuation_req)
        return ChatResponse(text="未找到对应的工具", session_id=req.session_id)
    else:
        cancel_text = "用户已取消执行工具操作。"
        db.add_message(session_id=req.session_id, role="tool", content=cancel_text)
        continuation_req = ChatRequest(
            text="用户拒绝了你的工具调用请求。请告知用户已取消，或者提供其他建议。",
            context=None,
            session_id=req.session_id,
            agent_id=req.agent_id
        )
        return await chat_endpoint(continuation_req)

class ChatCancelRequest(BaseModel):
    session_id: str

class LLMProviderResponse(BaseModel):
    provider_id: str
    name: str
    enabled: bool
    available: bool  # Has API key
    models: List[Dict[str, Any]]

class LLMModelInfo(BaseModel):
    model_id: str
    name: str
    supports_function_calling: bool
    max_tokens: int

class LLMSwitchRequest(BaseModel):
    provider_id: str
    model_id: Optional[str] = None

@app.get("/api/llm/providers", response_model=List[LLMProviderResponse])
async def list_llm_providers():
    """List all configured LLM providers."""
    try:
        config = load_llm_config()
        gw = LLMGateway(config)
        result = []
        for provider in config.providers:
            adapter = gw._adapters.get(provider.provider_id)
            available = adapter.is_available() if adapter else False
            result.append(LLMProviderResponse(
                provider_id=provider.provider_id,
                name=provider.name,
                enabled=provider.enabled,
                available=available,
                models=[
                    {
                        "model_id": m.model_id,
                        "name": m.name,
                        "supports_function_calling": m.supports_function_calling,
                        "max_tokens": m.max_tokens
                    }
                    for m in provider.models
                ]
            ))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/llm/models/{provider_id}", response_model=List[LLMModelInfo])
async def list_llm_models(provider_id: str):
    """List all models for a specific provider."""
    try:
        config = load_llm_config()
        gw = LLMGateway(config)
        models = gw.list_models(provider_id)
        return [
            LLMModelInfo(
                model_id=m.model_id,
                name=m.name,
                supports_function_calling=m.supports_function_calling,
                max_tokens=m.max_tokens
            )
            for m in models
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/llm/switch")
async def switch_llm_provider(req: LLMSwitchRequest):
    """Switch the active LLM provider."""
    try:
        gw = get_gateway()
        success = gw.switch_provider(req.provider_id)
        if not success:
            raise HTTPException(status_code=400, detail="Provider not available or no API key")
        return {"status": "success", "provider_id": req.provider_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/llm/status")
async def get_llm_status():
    """Get current LLM provider status."""
    try:
        gw = get_gateway()
        current = gw.get_current_provider_id()
        config = load_llm_config()
        provider = next((p for p in config.providers if p.provider_id == current), None)
        return {
            "current_provider": current,
            "provider_name": provider.name if provider else None,
            "available": gw.get_current_adapter().is_available() if gw.get_current_adapter() else False
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class LLMChatRequest(BaseModel):
    message: str
    system_prompt: Optional[str] = None
    context: Optional[Dict[str, str]] = None
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2048

class LLMChatResponse(BaseModel):
    text: str
    model: str
    provider: str
    finish_reason: str
    usage: Optional[Dict[str, int]] = None

@app.post("/api/llm/chat", response_model=LLMChatResponse)
async def llm_chat(req: LLMChatRequest):
    """Direct LLM chat endpoint (for testing the gateway)."""
    try:
        gw = get_gateway()
        response = await gw.chat(
            message=req.message,
            system_prompt=req.system_prompt,
            context=req.context,
            model=req.model,
            temperature=req.temperature,
            max_tokens=req.max_tokens
        )
        return LLMChatResponse(
            text=response.text,
            model=response.model,
            provider=response.provider,
            finish_reason=response.finish_reason,
            usage=response.usage
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat/cancel")
async def cancel_chat(req: ChatCancelRequest):
    """Cancel a running chat request for a specific session."""
    try:
        success = agent_client.cancel(req.session_id)
        if success:
            db.add_message(session_id=req.session_id, role="system", content="用户已手动终止对话生成。")
            return {"status": "success", "message": "Chat cancelled"}
        return {"status": "ignored", "message": "No active chat found to cancel"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    # DB: Record the user's message
    db.add_message(session_id=req.session_id, role="user", content=req.text)
    
    # 1. Build prompt with context and inject Tool Schema (M4 Integration)
    prompt = req.text
    
    # Generate Tool Schema instructions
    # We must combine local tools AND MCP tools
    tool_schemas = registry.get_all_tools_schema()
    mcp_schemas = mcp_manager.get_all_tools_schema()
    all_schemas = tool_schemas + mcp_schemas
    
    print(f"\n========== [DEBUG] 当前获取到的所有 Schema 数量: {len(all_schemas)} (MCP: {len(mcp_schemas)}) ==========\n")
    
    schema_str = "【系统可用外部系统列表 (External Systems)】\n"
    for ts in all_schemas:
        import json
        schema_str += f"- {ts['name']}: {ts['description']}\n  参数: {json.dumps(ts['parameters'], ensure_ascii=False)}\n"
        
    schema_str += """
【CRITICAL INSTRUCTION FOR EXTERNAL SYSTEMS】
You are running inside a wrapper called "Across Agents Assistant".
The external systems listed above (e.g. local_kb__search_local_wiki) are NOT in your native tool registry. THEY ARE NOT TOOLS.
DO NOT TRY TO USE `<invoke>`, `<function_calls>`, OR ANY NATIVE TOOL CALLING SYNTAX FOR THEM! Your orchestrator will block it and say "No such tool".

Instead, to request data from these external systems, you MUST output a raw markdown JSON code block in your response text. The wrapper will parse your text, intercept this JSON block, fetch the data, and return it to you in the next message.

When the user asks you to search or retrieve information from the knowledge base, you MUST use the `local_kb__search_local_wiki` external system FIRST. DO NOT rely on your internal knowledge for domain-specific questions; ALWAYS query the knowledge base!

You must output EXACTLY this JSON format in your response:
```json
{
  "plan_summary": "I am going to search the local knowledge base.",
  "tool_calls": [
    {"name": "local_kb__search_local_wiki", "args": {"query": "target keyword"}}
  ]
}
```
Only output the JSON block and wait for the results. Do not attempt to use native tools for this.
"""

    if req.context:
        ctx_parts = []
        if req.context.frontmost_app:
            ctx_parts.append(f"当前应用: {req.context.frontmost_app}")
        if req.context.window_title:
            ctx_parts.append(f"窗口标题: {req.context.window_title}")
        if req.context.clipboard_text:
            ctx_parts.append(f"剪贴板内容: {req.context.clipboard_text}")
            
        if ctx_parts:
            prompt = f"{schema_str}\n\n【系统上下文】\n" + "\n".join(ctx_parts) + f"\n\n【用户指令】\n{req.text}"
    else:
        prompt = f"{schema_str}\n\n【用户指令】\n{req.text}"

    print(f"\n========== [DEBUG] 发送给大模型的 PROMPT ==========\n{prompt}\n==================================================\n")

    while True:
        # 2. Call Agent (Real LLM Execution)
        reply = agent_client.send(
            message=prompt,
            session_id=req.session_id,
            target_agent=req.agent_id
        )
        
        print(f"\n========== [DEBUG] 大模型返回的 RAW TEXT ==========\n{reply.text}\n==================================================\n")
        
        # 3. Parse Intent & Trigger Real Approval Flow
        # Add defensive checking for reply.text being None
        reply_text = reply.text if reply.text else ""
        intent = ToolIntentParser.parse_intent(reply_text)
        
        if intent and "tool_calls" in intent and len(intent["tool_calls"]) > 0:
            # We got a valid tool call from the LLM!
            tool_call = intent["tool_calls"][0]
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("args", {})
            
            # Verify tool exists in registry (local or MCP)
            tool_def = registry.get_tool(tool_name)
            
            # The tool name format for MCP is "server_id__tool_name"
            is_mcp = False
            if tool_name and not tool_def:
                # We check if it matches an MCP schema, with forgiving naming
                schemas = mcp_manager.get_all_tools_schema()
                normalized_target = tool_name.replace("-", "_")
                
                for t in schemas:
                    normalized_schema_name = t["name"].replace("-", "_")
                    # Match exact (with prefix) OR match just the tool name (LLM forgot prefix)
                    if normalized_schema_name == normalized_target or normalized_schema_name.endswith(f"__{normalized_target}"):
                        is_mcp = True
                        tool_name = t["name"] # Auto-correct to the real schema name (e.g. local_kb__search-local-wiki)
                        break
            
            if tool_def or is_mcp:
                plan_summary = intent.get("plan_summary", f"大模型请求调用工具：{tool_name}")
                
                # Check if tool is "always allowed"
                is_always_allowed = db.get_tool_authorization(tool_name)
                
                if is_always_allowed:
                    # Auto-approve and execute
                    risk_level = tool_def.risk_level if tool_def else "medium"
                    db.add_audit_log(
                        session_id=reply.session_id,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        risk_level=risk_level,
                        decision="auto_approve"
                    )
                    
                    try:
                        if is_mcp:
                            parts = tool_name.split("__", 1)
                            server_id = parts[0]
                            actual_tool_name = parts[1]
                            result = await mcp_manager.call_tool(server_id, actual_tool_name, tool_args)
                        else:
                            result = tool_def.handler(**tool_args)
                            
                        result_text = f"✅ 工具 {tool_name} (自动授权) 执行成功！结果：\n{result}"
                        db.add_message(session_id=req.session_id, role="tool", content=result_text)
                        
                        recent_messages = db.get_messages(req.session_id)
                        original_question = "用户之前的问题"
                        if len(recent_messages) >= 2:
                            for msg in reversed(recent_messages):
                                if msg["role"] == "user":
                                    original_question = msg["content"]
                                    break
                                    
                        prompt = f"【工具执行反馈】\n刚才你调用的工具 `{tool_name}` 已执行完毕，结果如下：\n<tool_result>\n{result}\n</tool_result>\n\n请基于上述结果继续你的任务。如果还需要其他信息，可以继续调用工具；如果已经收集到足够信息，请直接回答用户最初的问题：\n<original_question>\n{original_question}\n</original_question>"
                        continue
                        
                    except Exception as e:
                        error_text = f"❌ 工具 (自动授权) 执行失败: {str(e)}"
                        db.add_message(session_id=req.session_id, role="tool", content=error_text)
                        
                        prompt = f"工具 {tool_name} 执行失败，报错信息：\n{str(e)}\n请告诉用户执行失败了，或者尝试其他方法。"
                        continue
                
                # Retrieve description safely
                if tool_def:
                    desc = tool_def.description
                    risk = tool_def.risk_level
                else:
                    # Look it up from mcp_manager if possible
                    schemas = mcp_manager.get_all_tools_schema()
                    matched = next((t for t in schemas if t["name"] == tool_name), None)
                    desc = matched["description"] if matched else "MCP 外部工具"
                    risk = matched["risk_level"] if matched else "medium"
                    
                # Hide JSON payload from user if possible
                display_text = plan_summary
                
                return ChatResponse(
                    text=display_text,
                    session_id=reply.session_id,
                    requires_approval=True,
                    approval_request={
                        "tool_name": tool_name,
                        "risk_level": risk,
                        "tool_args": tool_args,
                        "description": desc
                    }
                )
            else:
                # If the parser found JSON but the tool is NOT registered (hallucinated tool)
                # Feed it back to the LLM automatically to correct its mistake
                error_msg = f"错误：工具 `{tool_name}` 不存在。请严格检查【系统可用工具列表】，使用正确的工具名称（如 list_directory），或者直接回复纯文本。"
                prompt = error_msg
                continue
            
        # We no longer generate or play audio in Python.
        # The Swift client will handle TTS natively.

        db.add_message(session_id=req.session_id, role="assistant", content=reply.text)
        return ChatResponse(
            text=reply.text,
            session_id=reply.session_id,
            audio_path=None
        )

def start_api_server(host="127.0.0.1", port=8000):
    uvicorn.run(app, host=host, port=port)

@app.get("/api/tools/authorizations")
async def get_tool_authorizations():
    """Retrieve the list of all tools that are 'Always Allowed'"""
    try:
        auths = db.get_all_authorizations()
        return {"authorizations": auths}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class RevokeRequest(BaseModel):
    tool_name: str

@app.post("/api/tools/authorizations/revoke")
async def revoke_tool_authorization(req: RevokeRequest):
    """Revoke the 'Always Allow' authorization for a specific tool"""
    try:
        db.set_tool_authorization(req.tool_name, False)
        return {"status": "success", "tool_name": req.tool_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Task Manager Models
class TaskCreateRequest(BaseModel):
    description: str
    context: Optional[Dict[str, Any]] = None
    decompose_with_llm: bool = True

class SubTaskInfo(BaseModel):
    subtask_id: str
    description: str
    agent_id: str
    priority: int
    status: str
    progress: float
    dependencies: List[str]

class TaskInfo(BaseModel):
    task_id: str
    description: str
    task_type: str
    subtasks: List[SubTaskInfo]
    can_handle_directly: bool
    direct_response: Optional[str]
    progress: float
    created_at: float
    updated_at: float

class TaskCreateResponse(BaseModel):
    task_id: str
    description: str
    task_type: str
    subtasks: List[SubTaskInfo]
    can_handle_directly: bool
    direct_response: Optional[str]
    progress: float

@app.post("/api/tasks", response_model=TaskCreateResponse)
async def create_task(req: TaskCreateRequest):
    """Create a new task, optionally decomposing it with LLM."""
    try:
        task = _task_state.create_task(req.description)

        if req.decompose_with_llm:
            decomposer = get_task_decomposer()
            context = req.context or {}
            await decomposer.decompose(task, context)

        progress = _task_state.get_task_progress(task.task_id)

        return TaskCreateResponse(
            task_id=task.task_id,
            description=task.description,
            task_type=task.task_type.value,
            subtasks=[
                SubTaskInfo(
                    subtask_id=st.subtask_id,
                    description=st.description,
                    agent_id=st.agent_id,
                    priority=st.priority,
                    status=st.status.value,
                    progress=st.progress,
                    dependencies=st.dependencies
                )
                for st in task.subtasks
            ],
            can_handle_directly=task.can_handle_directly,
            direct_response=task.direct_response,
            progress=progress
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class TaskDispatchRequest(BaseModel):
    subtask_ids: Optional[List[str]] = None

class JobInfo(BaseModel):
    job_id: str
    subtask_id: str
    agent_id: str
    task_description: str
    status: str
    progress: float
    logs: List[str]
    result: Optional[str]
    error: Optional[str]

class TaskDispatchResponse(BaseModel):
    task_id: str
    dispatched_jobs: List[JobInfo]
    ready_remaining: int

@app.post("/api/tasks/{task_id}/dispatch", response_model=TaskDispatchResponse)
async def dispatch_task(task_id: str, req: TaskDispatchRequest):
    """Dispatch subtasks to agents."""
    try:
        task = _task_state.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        if req.subtask_ids:
            subtasks_to_dispatch = [st for st in task.subtasks if st.subtask_id in req.subtask_ids]
        else:
            subtasks_to_dispatch = _task_state.get_ready_subtasks(task_id)

        dispatcher = get_task_dispatcher()
        dispatched = []

        for subtask in subtasks_to_dispatch:
            job = dispatcher.dispatch_subtask(subtask)
            if job:
                dispatched.append(JobInfo(
                    job_id=job.job_id,
                    subtask_id=job.subtask_id,
                    agent_id=job.agent_id,
                    task_description=job.task_description,
                    status=job.status.value,
                    progress=job.progress,
                    logs=job.logs,
                    result=job.result,
                    error=job.error
                ))

        remaining = len(_task_state.get_ready_subtasks(task_id))

        return TaskDispatchResponse(
            task_id=task_id,
            dispatched_jobs=dispatched,
            ready_remaining=remaining
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tasks/{task_id}", response_model=TaskInfo)
async def get_task(task_id: str):
    """Get task details and progress."""
    try:
        task = _task_state.get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        progress = _task_state.get_task_progress(task_id)

        return TaskInfo(
            task_id=task.task_id,
            description=task.description,
            task_type=task.task_type.value,
            subtasks=[
                SubTaskInfo(
                    subtask_id=st.subtask_id,
                    description=st.description,
                    agent_id=st.agent_id,
                    priority=st.priority,
                    status=st.status.value,
                    progress=st.progress,
                    dependencies=st.dependencies
                )
                for st in task.subtasks
            ],
            can_handle_directly=task.can_handle_directly,
            direct_response=task.direct_response,
            progress=progress,
            created_at=task.created_at,
            updated_at=task.updated_at
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tasks", response_model=List[TaskInfo])
async def list_tasks():
    """List all tasks."""
    try:
        tasks = _task_state.get_all_tasks()
        return [
            TaskInfo(
                task_id=t.task_id,
                description=t.description,
                task_type=t.task_type.value,
                subtasks=[
                    SubTaskInfo(
                        subtask_id=st.subtask_id,
                        description=st.description,
                        agent_id=st.agent_id,
                        priority=st.priority,
                        status=st.status.value,
                        progress=st.progress,
                        dependencies=st.dependencies
                    )
                    for st in t.subtasks
                ],
                can_handle_directly=t.can_handle_directly,
                direct_response=t.direct_response,
                progress=_task_state.get_task_progress(t.task_id),
                created_at=t.created_at,
                updated_at=t.updated_at
            )
            for t in tasks
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tasks/{task_id}/jobs/{job_id}", response_model=JobInfo)
async def get_job(task_id: str, job_id: str):
    """Get job details."""
    try:
        job = _task_state.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return JobInfo(
            job_id=job.job_id,
            subtask_id=job.subtask_id,
            agent_id=job.agent_id,
            task_description=job.task_description,
            status=job.status.value,
            progress=job.progress,
            logs=job.logs,
            result=job.result,
            error=job.error
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tasks/{task_id}/jobs/{job_id}/cancel")
async def cancel_job(task_id: str, job_id: str):
    """Cancel a running job."""
    try:
        dispatcher = get_task_dispatcher()
        success = dispatcher.cancel_job(job_id)
        if not success:
            raise HTTPException(status_code=400, detail=f"Cannot cancel job {job_id}")
        return {"status": "success", "job_id": job_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    start_api_server()
