import uvicorn
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any
from pathlib import Path

from .agent_manager import AgentManager
from .openclaw.client import UniversalAgentClient
from .tts.tts_service import TTSService
from .tts.playback import NSSoundPlayback

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
tts_service = TTSService(Path("./temp_tts"))
playback = NSSoundPlayback()

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, background_tasks: BackgroundTasks):
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
    
    # 3. Generate Audio
    # Generate audio in background to not block the text response if needed?
    # No, for M2 we want to wait for audio or return path and play it.
    # Actually, let's just generate it synchronously and return the path, or play it directly.
    try:
        audio_path = tts_service._generate_audio(reply.text, voice_edge="zh-CN-XiaoxiaoNeural")
        
        # Schedule playback
        def play_audio(path):
            playback.play_mp3(path)
            
        background_tasks.add_task(play_audio, audio_path)
        audio_path_str = str(audio_path)
    except Exception as e:
        import logging
        logging.getLogger("across_agents_assistant").error(f"TTS failed: {e}")
        audio_path_str = None

    return ChatResponse(
        text=reply.text,
        session_id=reply.session_id,
        audio_path=audio_path_str
    )

def start_api_server(host="127.0.0.1", port=8000):
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    start_api_server()
