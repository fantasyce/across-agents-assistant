import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from .agent_manager import AgentManager
from .openclaw.client import UniversalAgentClient

# Ensure builtin tools are registered
from .tools import builtin_tools
from .tools.tool_registry import registry

app = FastAPI(title="Across Agents Assistant API")

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
    decision: str # "approve", "reject"
    tool_name: str
    tool_args: Dict[str, Any]

# Global instances
agent_manager = AgentManager()
agent_client = UniversalAgentClient(agent_manager)

@app.get("/api/tools", response_model=List[Dict[str, Any]])
async def get_tools():
    return registry.get_all_tools_schema()

@app.post("/api/approve", response_model=ChatResponse)
async def approve_tool_execution(req: ApprovalDecision):
    if req.decision == "approve":
        # Execute tool
        tool_def = registry.get_tool(req.tool_name)
        if tool_def:
            try:
                result = tool_def.handler(**req.tool_args)
                return ChatResponse(
                    text=f"✅ 工具 {req.tool_name} 执行成功！结果：\n{result}",
                    session_id=req.session_id
                )
            except Exception as e:
                return ChatResponse(
                    text=f"❌ 工具执行失败: {str(e)}",
                    session_id=req.session_id
                )
        return ChatResponse(text="未找到对应的工具", session_id=req.session_id)
    else:
        return ChatResponse(text="已取消执行", session_id=req.session_id)

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    # 1. Build prompt with context
    prompt = req.text
    if req.context:
        ctx_parts = []
        if req.context.frontmost_app:
            ctx_parts.append(f"当前应用: {req.context.frontmost_app}")
        if req.context.window_title:
            ctx_parts.append(f"窗口标题: {req.context.window_title}")
        if req.context.clipboard_text:
            ctx_parts.append(f"剪贴板内容: {req.context.clipboard_text}")
            
        if ctx_parts:
            prompt = f"【系统上下文】\n" + "\n".join(ctx_parts) + f"\n\n【用户指令】\n{req.text}"

    # Mock Phase 3 behavior: if the prompt asks to create an email or list directory
    if "list_directory" in prompt or "看" in prompt and "目录" in prompt:
        return ChatResponse(
            text="我将为你列出目录内容。该操作风险较低，但在执行前请您确认：",
            session_id=req.session_id,
            requires_approval=True,
            approval_request={
                "tool_name": "list_directory",
                "risk_level": "low",
                "tool_args": {"path": "~/Documents"},
                "description": "列出 ~/Documents 目录的内容"
            }
        )
        
    if "email" in prompt.lower() or "邮件" in prompt:
        return ChatResponse(
            text="好的，我将为你创建一封邮件草稿。这是一个中风险操作，请在弹窗中确认信息：",
            session_id=req.session_id,
            requires_approval=True,
            approval_request={
                "tool_name": "create_email_draft",
                "risk_level": "medium",
                "tool_args": {"recipient": "boss@company.com", "subject": "本周工作汇报", "body": "这是正文..."},
                "description": "在 Mail.app 中创建一封发给 boss@company.com 的邮件草稿"
            }
        )
        
    if "备忘录" in prompt or "笔记" in prompt or "note" in prompt.lower():
        return ChatResponse(
            text="没问题，我将为你创建一条备忘录。请确认内容：",
            session_id=req.session_id,
            requires_approval=True,
            approval_request={
                "tool_name": "create_note_draft",
                "risk_level": "medium",
                "tool_args": {"title": "会议纪要", "body": "1. 确定下季度OKR\n2. 优化APP性能"},
                "description": "在 macOS 备忘录中创建一条名为“会议纪要”的新笔记"
            }
        )
        
    # --- New Advanced Mac Tools Mocks ---
    if "浏览器" in prompt or "网页" in prompt or "网址" in prompt:
        return ChatResponse(
            text="好的，我将读取你当前浏览器的活动标签页信息：",
            session_id=req.session_id,
            requires_approval=True,
            approval_request={
                "tool_name": "get_active_browser_url",
                "risk_level": "low",
                "tool_args": {},
                "description": "获取当前 Chrome 或 Safari 的活动标签页网址和标题"
            }
        )
        
    if "暗" in prompt or "深色" in prompt or "浅色" in prompt or "亮" in prompt or "模式" in prompt:
        return ChatResponse(
            text="我将为你切换系统的外观模式：",
            session_id=req.session_id,
            requires_approval=True,
            approval_request={
                "tool_name": "toggle_system_dark_mode",
                "risk_level": "low",
                "tool_args": {},
                "description": "切换 macOS 的深色/浅色外观模式"
            }
        )
        
    if "音量" in prompt or "大点声" in prompt or "小点声" in prompt:
        return ChatResponse(
            text="好的，我将调整系统音量：",
            session_id=req.session_id,
            requires_approval=True,
            approval_request={
                "tool_name": "set_system_volume",
                "risk_level": "low",
                "tool_args": {"level": 50},
                "description": "将系统主音量设置为 50%"
            }
        )

    # 2. Call Agent
    reply = agent_client.send(
        message=prompt,
        session_id=req.session_id,
        target_agent=req.agent_id
    )
    
    # We no longer generate or play audio in Python.
    # The Swift client will handle TTS natively.

    return ChatResponse(
        text=reply.text,
        session_id=reply.session_id,
        audio_path=None
    )

def start_api_server(host="127.0.0.1", port=8000):
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    start_api_server()
