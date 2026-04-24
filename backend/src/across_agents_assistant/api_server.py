import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import asyncio

from .agent_manager import AgentManager
from .openclaw.client import UniversalAgentClient
from .openclaw.intent_parser import ToolIntentParser

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
    return registry.get_all_tools_schema()

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
        tool_def = registry.get_tool(req.tool_name)
        if "__" in req.tool_name and not tool_def:
            schemas = mcp_manager.get_all_tools_schema()
            if any(t["name"] == req.tool_name for t in schemas):
                is_mcp = True
                
        if is_mcp:
            # Execute MCP tool
            parts = req.tool_name.split("__", 1)
            if len(parts) == 2:
                server_id = parts[0]
                actual_tool_name = parts[1]
                
                try:
                    result = await mcp_manager.call_tool(server_id, actual_tool_name, req.tool_args)
                    result_text = f"✅ MCP 工具 {req.tool_name} 执行成功！结果：\n{result}"
                    db.add_message(session_id=req.session_id, role="tool", content=result_text)
                    
                    continuation_req = ChatRequest(
                        text=f"MCP 工具 {req.tool_name} 已执行，结果如下：\n{result}\n请基于此结果继续回答用户的问题。",
                        context={},
                        session_id=req.session_id,
                        agent_id=req.agent_id
                    )
                    return await chat_endpoint(continuation_req)
                except Exception as e:
                    error_text = f"❌ MCP 工具执行失败: {str(e)}"
                    db.add_message(session_id=req.session_id, role="tool", content=error_text)
                    continuation_req = ChatRequest(
                        text=f"MCP 工具 {req.tool_name} 执行失败，报错信息：\n{str(e)}\n请告诉用户执行失败了，或者尝试其他方法。",
                        context={},
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
                continuation_req = ChatRequest(
                    text=f"工具 {req.tool_name} 已执行，结果如下：\n{result}\n请基于此结果继续回答用户的问题。",
                    context={}, # We don't need to resend tier1 context for the continuation
                    session_id=req.session_id,
                    agent_id=req.agent_id # Pass through the original agent
                )
                return await chat_endpoint(continuation_req)
                
            except Exception as e:
                error_text = f"❌ 工具执行失败: {str(e)}"
                db.add_message(session_id=req.session_id, role="tool", content=error_text)
                
                continuation_req = ChatRequest(
                    text=f"工具 {req.tool_name} 执行失败，报错信息：\n{str(e)}\n请告诉用户执行失败了，或者尝试其他方法。",
                    context={},
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
            context={},
            session_id=req.session_id,
            agent_id=req.agent_id
        )
        return await chat_endpoint(continuation_req)

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    # DB: Record the user's message
    db.add_message(session_id=req.session_id, role="user", content=req.text)
    
    # 1. Build prompt with context and inject Tool Schema (M4 Integration)
    prompt = req.text
    
    # Generate Tool Schema instructions
    tool_schemas = registry.get_all_tools_schema()
    schema_str = "【系统可用工具列表 (Tools)】\n"
    for ts in tool_schemas:
        import json
        schema_str += f"- {ts['name']}: {ts['description']}\n  参数: {json.dumps(ts['parameters'], ensure_ascii=False)}\n"
        
    schema_str += """
【执行规则】
如果用户要求你执行上述工具列表中的动作，请你**必须且只能**输出一个 JSON 代码块，不要包含任何其他文字解释。
JSON 格式必须严格如下：
```json
{
  "plan_summary": "向用户解释你要干什么，比如：我将为你创建邮件草稿",
  "tool_calls": [
    {"name": "工具名称", "args": {"参数1": "值"}}
  ]
}
```
如果你不需要调用工具，直接回复普通文本即可，不要输出 JSON。
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
            if "__" in tool_name and not tool_def:
                # We check if it matches an MCP schema
                schemas = mcp_manager.get_all_tools_schema()
                if any(t["name"] == tool_name for t in schemas):
                    is_mcp = True
            
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
                        
                        prompt = f"工具 {tool_name} 已执行，结果如下：\n{result}\n请基于此结果继续回答用户的问题。"
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

if __name__ == "__main__":
    start_api_server()
