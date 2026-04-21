import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

from .agent_manager import AgentManager
from .openclaw.client import UniversalAgentClient

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

# Global instances
agent_manager = AgentManager()
agent_client = UniversalAgentClient(agent_manager)

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
