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
from .llm_client import OrchestratorClient, OrchestratorResponse

# Ensure builtin tools are registered
from .tools import builtin_tools
from .tools.tool_registry import registry
from .tools.mcp_client import mcp_manager
from .db.database import db

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
agent_client = OrchestratorClient(agent_manager)

class KeysRequest(BaseModel):
    deepseek: Optional[str] = None
    minimax: Optional[str] = None

class ActiveAgentRequest(BaseModel):
    agent_id: str

@app.post("/api/active_agent")
async def update_active_agent(req: ActiveAgentRequest):
    agent_manager.set_active_agent(req.agent_id)
    return {"status": "ok"}

@app.post("/api/keys")
async def update_keys(req: KeysRequest):
    import os
    if req.deepseek:
        os.environ["DEEPSEEK_API_KEY"] = req.deepseek
        agent_manager.update_agent("deepseek", {**agent_manager.get_agent_config("deepseek"), "api_key": req.deepseek})
    if req.minimax:
        os.environ["MINIMAX_API_KEY"] = req.minimax
        minimax_config = agent_manager.get_agent_config("minimax") or {}
        # Force update minimax config to new anthropic compatible endpoint
        minimax_config.update({
            "api_key": req.minimax,
            "type": "anthropic",
            "base_url": "https://api.minimaxi.com/anthropic",
            "model": "MiniMax-M2.7"
        })
        agent_manager.update_agent("minimax", minimax_config)
    return {"status": "ok"}


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
    
    # Prepare system message with context if provided
    system_msg = "You are a helpful AI assistant running in a macOS desktop environment. You are NOT Claude. You are NOT Hermes. You are NOT OpenClaw. You are the Across Agents Copilot, a versatile tool for macOS users. Do not use conversational filler, just act."
    if req.context:
        ctx_parts = []
        if req.context.frontmost_app:
            ctx_parts.append(f"当前应用: {req.context.frontmost_app}")
        if req.context.window_title:
            ctx_parts.append(f"窗口标题: {req.context.window_title}")
        if req.context.clipboard_text:
            ctx_parts.append(f"剪贴板内容: {req.context.clipboard_text}")
            
        if ctx_parts:
            system_msg += "\n\n【系统上下文】\n" + "\n".join(ctx_parts)
            
    # Insert system prompt to DB if missing (or update it if it exists to ensure the strong prompt is applied)
    db_messages = db.get_messages(req.session_id)
    has_system = False
    for m in db_messages:
        if m["role"] == "system":
            # Update the system prompt in DB to ensure it's always the strong one
            db.update_system_message(req.session_id, system_msg)
            has_system = True
            break
            
    if not has_system:
        db.add_message(session_id=req.session_id, role="system", content=system_msg)
        
    return await _run_agent_loop(req.session_id, req.agent_id)

async def _run_agent_loop(session_id: str, agent_id: str) -> ChatResponse:
    import json
    tool_schemas = registry.get_all_tools_schema()
    mcp_schemas = mcp_manager.get_all_tools_schema()
    all_schemas = tool_schemas + mcp_schemas
    
    messages = db.get_messages(session_id)
    
    formatted_messages = []
    for m in messages:
        role = m["role"]
        content = m["content"] or ""
        if role == "tool":
            formatted_messages.append({
                "role": "tool",
                "content": content,
                "tool_call_id": m.get("tool_call_id") or "unknown"
            })
        elif role == "assistant":
            msg = {
                "role": "assistant",
                "content": content
            }
            if m.get("tool_calls"):
                try:
                    raw_tcs = json.loads(m["tool_calls"])
                    openai_tcs = []
                    for tc in raw_tcs:
                        # Our db format is [{"id": "...", "name": "...", "arguments": {...}}]
                        openai_tcs.append({
                            "id": tc.get("id", "unknown"),
                            "type": "function",
                            "function": {
                                "name": tc.get("name"),
                                "arguments": json.dumps(tc.get("arguments", {}), ensure_ascii=False)
                            }
                        })
                    msg["tool_calls"] = openai_tcs
                except Exception:
                    pass
            formatted_messages.append(msg)
        else:
            formatted_messages.append({
                "role": role,
                "content": content
            })
            
    # Clean up history to prevent API errors from old incompatible data
    valid_messages = []
    for msg in formatted_messages:
        if msg["role"] == "system":
            valid_messages.insert(0, msg)
        elif msg["role"] == "tool":
            if valid_messages and valid_messages[-1]["role"] == "assistant" and "tool_calls" in valid_messages[-1]:
                valid_messages.append(msg)
        else:
            if valid_messages and valid_messages[-1]["role"] == "assistant" and "tool_calls" in valid_messages[-1]:
                del valid_messages[-1]["tool_calls"]
            valid_messages.append(msg)
            
    if valid_messages and valid_messages[-1]["role"] == "assistant" and "tool_calls" in valid_messages[-1]:
        del valid_messages[-1]["tool_calls"]
        
    reply = await agent_client.chat(agent_id, valid_messages, all_schemas)
    
    if reply.tool_calls:
        # Save assistant message with tool calls to history!
        db.add_message(session_id=session_id, role="assistant", content=reply.text or "", tool_calls=json.dumps(reply.tool_calls, ensure_ascii=False))
        
        tool_call = reply.tool_calls[0]
        tool_name = tool_call["name"]
        tool_args = tool_call["arguments"]
        
        # In OpenAI, the tool_call_id must match when sending tool result
        tool_call_id = tool_call.get("id", tool_name)
        
        # Determine if it's MCP or Local Tool
        tool_def = registry.get_tool(tool_name)
        is_mcp = not tool_def
        
        is_always_allowed = db.get_tool_authorization(tool_name)
        if is_always_allowed:
            db.add_audit_log(session_id, tool_name, tool_args, "medium", "auto_approve")
            
            try:
                if is_mcp:
                    parts = tool_name.split("__", 1)
                    if len(parts) == 2:
                        server_id = parts[0]
                        actual_tool_name = parts[1]
                        result = await mcp_manager.call_tool(server_id, actual_tool_name, tool_args)
                        result_text = str(result)
                    else:
                        result_text = "Error: Invalid MCP tool name format."
                else:
                    result = tool_def.handler(**tool_args)
                    result_text = str(result)
            except Exception as e:
                result_text = f"Error executing tool: {str(e)}"
                
            db.add_message(session_id=session_id, role="tool", content=result_text, tool_call_id=tool_call_id)
            
            return await _run_agent_loop(session_id, agent_id)
            
        matched = next((t for t in all_schemas if t["name"] == tool_name), None)
        desc = matched["description"] if matched else "外部工具"
        risk = matched["risk_level"] if matched else "medium"
        
        return ChatResponse(
            text=f"请求调用工具：{tool_name}",
            session_id=session_id,
            requires_approval=True,
            approval_request={
                "tool_name": tool_name,
                "risk_level": risk,
                "tool_args": tool_args,
                "description": desc
            }
        )
        
    db.add_message(session_id=session_id, role="assistant", content=reply.text or "")
    return ChatResponse(text=reply.text or "", session_id=session_id)


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

if __name__ == "__main__":
    start_api_server()
