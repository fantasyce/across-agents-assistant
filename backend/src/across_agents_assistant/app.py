from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from .config import AppConfig
from .logging_setup import setup_logger
from .openclaw import OpenClawClient
from .agent_manager import AgentManager
from .speech import SpeechClient, SpeechInterruptMonitor
from .tts import TTSService
from .wakeword import contains_wake_word, is_exit_word, is_hallucination


@dataclass
class AppState:
    cached_speech_final: str = ""
    active_session_ids: Dict[str, str] = None
    last_asr_error: Optional[str] = None
    last_asr_error_ts: float = 0.0

    def __post_init__(self):
        if self.active_session_ids is None:
            self.active_session_ids = {}


class AcrossAgentsAssistantApp:
    def __init__(self, project_root: Path, config: AppConfig):
        self._project_root = project_root
        self._config = config
        self._log_dir = project_root / config.log_dir
        self._logger = setup_logger(self._log_dir, config.log_file, debug=True)

        self._events: "queue.Queue[str]" = queue.Queue()
        self._text_queue: "queue.Queue[str]" = queue.Queue()
        self._shutdown = threading.Event()
        self._hotkey_interrupt = threading.Event() # Used for interrupting the whole conversation loop
        self._tts_interrupt = threading.Event()    # Used for interrupting TTS only
        self._voice_mode_enabled = threading.Event()
        self._voice_mode_enabled.clear() # Default OFF
        self._continuous_mode = threading.Event()
        self._continuous_mode.clear() # Default OFF (🤐)
        self._silent_mode = threading.Event()
        self._manual_listen = threading.Event()
        self._state = AppState()
        self._worker: Optional[threading.Thread] = None

        self._agent_manager = AgentManager()
        from .llm_client import OrchestratorClient
        self._openclaw = OrchestratorClient(config_manager=self._agent_manager)
        self._tts = TTSService(temp_dir=Path("/tmp/across-agents-assistant"))
        
        self.on_message_callback = None  # To send messages to UI
        
        self._speech_client = SpeechClient(
            socket_path=self._config.speech_socket_path,
            speechcli_app_path=self._config.speechcli_app_path,
            locale="zh-CN",
            auto_start=True,
        )

        self._last_config_mtime = 0
        self._start_config_watcher()

    def _start_config_watcher(self):
        def watch():
            import os
            import time
            from .agent_manager import AGENTS_CONFIG_FILE
            while not self._shutdown.is_set():
                try:
                    if AGENTS_CONFIG_FILE.exists():
                        mtime = os.path.getmtime(AGENTS_CONFIG_FILE)
                        if self._last_config_mtime != 0 and mtime > self._last_config_mtime:
                            # Config changed! Reload it instantly
                            self._agent_manager.config = self._agent_manager._load_config()
                            new_active = self._agent_manager.get_active_agent()
                            if getattr(self._openclaw, 'agent_id', None) != new_active:
                                self._logger.info(f"🔄 检测到配置变化，热切换到智能体: {new_active}")
                                self._openclaw.initialized = False
                                self._openclaw.initialize()
                        self._last_config_mtime = mtime
                except Exception:
                    pass
                time.sleep(1)
                
        threading.Thread(target=watch, daemon=True).start()

    def run(self):
        self._logger.info("=" * 50)
        self._logger.info("across-agents-assistant")
        self._logger.info(f"  - 唤醒词: {self._config.wake_word}")
        self._logger.info("  - 退出词: 再见 / 拜拜 / 退出 等")
        self._logger.info("=" * 50)

        try:
            self._worker_loop()
        except KeyboardInterrupt:
            self._logger.info("👋 退出")
        finally:
            self.shutdown()

    def start_background(self):
        if self._worker and self._worker.is_alive():
            return
        if self._voice_mode_enabled.is_set():
            self.ensure_speechcli_running()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def shutdown(self):
        if self._shutdown.is_set():
            return
        self._logger.info("🛑 正在关闭应用并释放资源...")
        self._voice_mode_enabled.clear()
        self._continuous_mode.clear()
        self._hotkey_interrupt.set()
        self._shutdown.set()
            
        self.stop_speechcli()
        
        # Explicitly delete the Whisper model to trigger memory release
        if hasattr(self._speech_client, '_model'):
            self._logger.info("🧹 正在从内存中卸载 Faster-Whisper 模型...")
            import gc
            self._speech_client._model = None
            gc.collect()
            
        if self._worker:
            self._worker.join(timeout=2.0)
            
        self._logger.info("✅ 所有资源已释放，进程即将退出")

    def get_status_text(self) -> str:
        if self._state.last_asr_error and (time.time() - self._state.last_asr_error_ts) < 15.0:
            if self._state.last_asr_error == "failed":
                return "ASR失败(权限/设备)"
            return f"ASR错误: {self._state.last_asr_error}"
        return "实时对话中" if self._continuous_mode.is_set() else "待机"

    def is_realtime_enabled(self) -> bool:
        return self._continuous_mode.is_set() and self._voice_mode_enabled.is_set()

    def set_realtime_enabled(self, enabled: bool):
        if enabled:
            self._voice_mode_enabled.set()
            self._continuous_mode.set()
            self.ensure_speechcli_running()
        else:
            self._continuous_mode.clear()
            self._hotkey_interrupt.set()

    def ensure_speechcli_running(self) -> bool:
        if not self._voice_mode_enabled.is_set():
            return False
        return self._speech_client.ensure_server_running()

    def is_speechcli_running(self) -> bool:
        client = SpeechClient(
            socket_path=self._config.speech_socket_path,
            speechcli_app_path=self._config.speechcli_app_path,
            locale="zh-CN",
            auto_start=False,
        )
        ok = client.connect()
        client.close()
        return ok

    def stop_speechcli(self):
        try:
            self._speech_client.close()
        except Exception:
            pass

    def pause_speechcli(self):
        try:
            self._speech_client.stop()
        except Exception:
            pass

    def _worker_loop(self):
        self._logger.info("🛠️ 后台工作线程已启动，进入主循环。")
        
        # Start background initialization for agent_client if needed
        # We don't need to initialize OpenClaw anymore as it's handled by OrchestratorClient on-the-fly
        # threading.Thread(target=self._openclaw.initialize, daemon=True).start()
        
        while not self._shutdown.is_set():
            try:
                text_msg = self._text_queue.get_nowait()
                self._hotkey_interrupt.clear()
                self._handle_user_text(text_msg)
                continue
            except queue.Empty:
                pass
                
            if self._manual_listen.is_set():
                self._manual_listen.clear()
                self._hotkey_interrupt.clear()
                self._handle_single_turn()
                continue

            if not self._voice_mode_enabled.is_set():
                time.sleep(0.2)
                continue

            # Voice input is enabled, check mode
            if self._continuous_mode.is_set():
                # If continuous mode is enabled, enter conversation loop directly
                self._conversation_loop()
                # 连续对话结束后，主动关闭麦克风
                try:
                    self._speech_client.stop()
                except Exception:
                    pass
                time.sleep(0.5)
            else:
                time.sleep(0.2)

    def _conversation_loop(self):
        self._logger.info("🟢 连续对话循环已启动")
        
        while not self._shutdown.is_set() and not self._hotkey_interrupt.is_set():
            if not self._continuous_mode.is_set() or not self._voice_mode_enabled.is_set():
                self._logger.info("⏱️  连续对话已关闭，返回待机模式")
                return
                
            if self._manual_listen.is_set():
                self._manual_listen.clear()
                self._hotkey_interrupt.clear()
                self._handle_single_turn()
                continue
                
            if self._state.cached_speech_final:
                text = self._state.cached_speech_final
                self._state.cached_speech_final = ""
                self._logger.info(f"🎙️ 处理缓存的语音: {text}")
            else:
                self._logger.info("🎙️  [连续对话中] 等待语音输入...")
                text = self._listen_once(timeout=20.0, interrupt_on_realtime_disable=True)

            if not text or not text.strip() or is_hallucination(text):
                if not self._continuous_mode.is_set() or not self._voice_mode_enabled.is_set():
                    self._logger.info("⏱️  连续对话已关闭，返回待机模式")
                    break
                elif self._state.last_asr_error:
                    self._logger.warning("🎙️ ASR发生错误，重新初始化模型...")
                    try:
                        self.stop_speechcli()
                        self._speech_client = SpeechClient(
                            locale="zh-CN",
                            auto_start=True,
                        )
                        self._speech_client.connect()
                    except Exception as e:
                        self._logger.error(f"恢复 ASR 失败: {e}")
                else:
                    continue
                
            actual = text.strip()
            
            if not actual or len(actual.replace("。", "").replace("，", "").replace("？", "").replace(".", "").strip()) == 0:
                continue
            
            if is_exit_word(text):
                self._logger.info("👋 检测到退出指令，自动关闭连续对话")
                import os
                os.system("afplay /System/Library/Sounds/Funk.aiff &")
                self._state.cached_speech_final = ""
                self._continuous_mode.clear()
                self._voice_mode_enabled.clear()
                if self.on_message_callback:
                    self.on_message_callback("system", "Continuous_Off", None)
                break

            # 连续对话中，同步等待大模型处理完毕
            self._handle_user_text_sync(actual)
            
            # 模型处理和播报完毕后，发出提示音，表示可以接收下一句了
            if self._continuous_mode.is_set() and not self._hotkey_interrupt.is_set():
                import os
                os.system("afplay /System/Library/Sounds/Glass.aiff &")

    def _handle_single_turn(self):
        self._logger.info("🎙️  单次对话：等待语音输入...")
        text = self._listen_once(timeout=15.0)
        
        # 单次录音结束后，关闭麦克风
        try:
            self._speech_client.stop()
        except Exception:
            pass
            
        if text and text.strip() and not is_hallucination(text):
            actual = text.strip()
            
            if not actual or len(actual.replace("。", "").replace("，", "").replace("？", "").replace(".", "").strip()) == 0:
                self._logger.info("⏱️  未检测到有效语音内容，结束单次对话")
                import os
                os.system("afplay /System/Library/Sounds/Funk.aiff &")
                return
                
            if is_exit_word(text):
                self._logger.info("👋 取消本次对话")
                import os
                os.system("afplay /System/Library/Sounds/Funk.aiff &")
                self._state.cached_speech_final = ""
                return
                
            self._handle_user_text(actual)
            self._logger.info("✅ 单次对话结束")
            import os
            os.system("afplay /System/Library/Sounds/Funk.aiff &")
        else:
            self._logger.info("⏱️  未检测到语音，结束单次对话")
            import os
            os.system("afplay /System/Library/Sounds/Funk.aiff &")

    def _handle_user_text_sync(self, text: str, target_agent: Optional[str] = None):
        target_agent = target_agent or self._agent_manager.get_active_agent()
        import os
        self._logger.info(f"🗣️ 用户 ({target_agent}): {text}")
        if self.on_message_callback:
            self.on_message_callback("user", text, target_agent)
            
        os.system("afplay /System/Library/Sounds/Pop.aiff &")
        
        # 同步处理，确保听完大模型说话才返回
        self._process_agent_reply(text, target_agent)

    def _handle_user_text(self, text: str, target_agent: Optional[str] = None):
        target_agent = target_agent or self._agent_manager.get_active_agent()
        import os
        self._logger.info(f"🗣️ 用户 ({target_agent}): {text}")
        if self.on_message_callback:
            self.on_message_callback("user", text, target_agent)
            
        os.system("afplay /System/Library/Sounds/Pop.aiff &")
        
        # 放到独立线程中处理，支持多智能体并发请求
        threading.Thread(target=self._process_agent_reply, args=(text, target_agent), daemon=True).start()

    def _handle_user_structured_text(self, structured_content, target_agent: Optional[str] = None):
        parts = []
        if isinstance(structured_content, list):
            for item in structured_content:
                if isinstance(item, dict):
                    t = item.get("type")
                    if t == "text":
                        content = item.get("content") or ""
                        if isinstance(content, str):
                            parts.append(content.replace("\\n", "\n"))
                    elif t == "file":
                        p = item.get("path") or item.get("name") or ""
                        if isinstance(p, str) and p:
                            parts.append(f"\n{p}\n")
                elif isinstance(item, str):
                    parts.append(item)

        text = "".join(parts).strip()
        if not text:
            return
        self._handle_user_text(text, target_agent=target_agent)

    def _process_agent_reply(self, text: str, target_agent: str):
        try:
            self._logger.debug(f"🧠 {target_agent} 请求中...")
            t0 = time.time()
            
            session_id = self._state.active_session_ids.get(target_agent)
            
            import asyncio
            from .db.database import db
            from .tools.tool_registry import registry
            from .tools.mcp_client import mcp_manager
            
            # Use db messages for history just like api_server
            # For simplicity in voice mode, we just pass the current text if session is new
            # If we want full history we could fetch it.
            if not session_id:
                import uuid
                session_id = "voice-" + str(uuid.uuid4())
                self._state.active_session_ids[target_agent] = session_id
                
            db.add_message(session_id=session_id, role="user", content=text)
            messages = db.get_messages(session_id)
            
            # Format messages for Orchestrator
            formatted_messages = []
            system_msg = "You are a helpful AI assistant running in a macOS desktop environment. You are NOT Claude. You are NOT Hermes. You are NOT OpenClaw. You are the Across Agents Copilot, a versatile tool for macOS users. Keep your answers brief and suitable for voice synthesis."
            formatted_messages.append({"role": "system", "content": system_msg})
            
            for m in messages:
                if m["role"] in ["user", "assistant"]:
                    formatted_messages.append({"role": m["role"], "content": m["content"] or ""})
            
            all_schemas = registry.get_all_tools_schema() + mcp_manager.get_all_tools_schema()
            
            # Run the async chat method in a new event loop
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            reply = loop.run_until_complete(
                self._openclaw.chat(
                    agent_id=target_agent,
                    messages=formatted_messages,
                    tools=all_schemas
                )
            )
            
            db.add_message(session_id=session_id, role="assistant", content=reply.text or "")
            
            elapsed_sec = time.time() - t0
            self._logger.info(f"💬 {target_agent} 回复 (耗时: {elapsed_sec:.2f}s): {(reply.text or '')[:120]}".replace("\n", " "))

            if self.on_message_callback:
                self.on_message_callback("agent", reply.text or "", target_agent)

            # 只有当前激活的 agent 的回复才会触发语音播报，避免多后台回复抢占 TTS
            if target_agent == self._agent_manager.get_active_agent():
                if not self._silent_mode.is_set():
                    self._speak(reply.text or "")
                else:
                    self._logger.debug("🔇 静音模式已开启，跳过语音播报")
                    # Clear any pending TTS interrupt when skipping playback
                    self._tts_interrupt.clear()

        except Exception as e:
            self._logger.error(f"处理 {target_agent} 输入异常: {e}")
            # Ensure UI lock is cleared on error
            if self.on_message_callback:
                self.on_message_callback("agent", f"抱歉，发生了内部错误: {e}", target_agent)
            
            if target_agent == self._agent_manager.get_active_agent():
                if not self._silent_mode.is_set():
                    self._speak("抱歉，我刚刚脑子卡壳了，请再说一遍。")

    def _speak(self, text: str):
        # 清空之前的缓存
        self._state.cached_speech_final = ""
        
        speak_result = self._tts.speak_interruptible(
            text,
            interrupt_monitor_factory=self._build_interrupt_monitor,
            external_interrupt=self._tts_interrupt,
        )
        # Clear the TTS interrupt flag after playback ends
        self._tts_interrupt.clear()
        
        self._logger.debug(f"🔊 TTS 语音生成 (生成耗时: {speak_result.elapsed_sec:.2f}s, 打断: {speak_result.interrupted}): {text[:20]}...".replace("\n", " "))
        self._logger.info("🔊 播报结束或被打断")
        if speak_result.cached_text:
            self._state.cached_speech_final = speak_result.cached_text
            self._logger.info(f"🔔 播放中检测到说话: {self._state.cached_speech_final}")

    def _build_interrupt_monitor(self, on_final):
        # With pure Python ASR, we can safely reuse the main speech client.
        return SpeechInterruptMonitor(speech_client=self._speech_client, on_final=on_final, wake_word=self._config.wake_word)

    def _listen_once(self, timeout: float, interrupt_on_realtime_disable: bool = False) -> str:
        # Clear any old errors before starting
        self._state.last_asr_error = None
        
        # Explicitly connect if needed
        if not self._speech_client.connect():
            self._state.last_asr_error = "failed"
            self._state.last_asr_error_ts = time.time()
            return ""
            
        if not self._speech_client.start():
            self._state.last_asr_error = "failed"
            self._state.last_asr_error_ts = time.time()
            return ""

        partials = []
        final_text = ""
        
        def stop_cond():
            if self._hotkey_interrupt.is_set():
                return True
            if interrupt_on_realtime_disable and (not self._continuous_mode.is_set() or not self._voice_mode_enabled.is_set()):
                return True
            return False
            
        results = self._speech_client.listen(timeout=timeout, stop_condition=stop_cond)
        
        for r in results:
            if r.error:
                self._state.last_asr_error = r.error
                self._state.last_asr_error_ts = time.time()
                self._logger.info(f"🎙️ ASR错误: {r.error}")
                continue
            if r.is_final:
                final_text = r.text
            else:
                if r.text:
                    partials.append(r.text)

        if not final_text and partials:
            final_text = partials[-1]
            
        final_text = final_text.strip()
        if final_text:
            self._logger.info(f"🎙️ ASR 识别: {final_text}")
        return final_text

    def _listen_once_with_wakeword(self, timeout: float) -> Tuple[str, bool]:
        # Clear any old errors before starting
        self._state.last_asr_error = None
        
        # Explicitly connect if needed
        if not self._speech_client.connect():
            self._state.last_asr_error = "failed"
            self._state.last_asr_error_ts = time.time()
            return "", False
            
        if not self._speech_client.start():
            # If start fails, it means the engine threw an immediate error or disconnected
            self._state.last_asr_error = "failed"
            self._state.last_asr_error_ts = time.time()
            return "", False

        partials = []
        final_text = ""
        wakeword = False
        
        def stop_cond():
            return self._hotkey_interrupt.is_set() or not self._voice_mode_enabled.is_set()

        results = self._speech_client.listen(timeout=timeout, stop_condition=stop_cond)
        
        for r in results:
            if r.error:
                self._state.last_asr_error = r.error
                self._state.last_asr_error_ts = time.time()
                self._logger.info(f"🎙️ ASR错误: {r.error}")
                continue
            if r.is_final:
                final_text = r.text
            else:
                if r.text:
                    partials.append(r.text)
            
            if r.text and contains_wake_word(r.text, wake_word=self._config.wake_word):
                wakeword = True
                final_text = r.text
                self._logger.info(f"💡 提前命中唤醒词，中止本次监听。内容: {r.text}")
                break

        try:
            self._speech_client.stop()
        except Exception:
            pass

        if not final_text and partials:
            final_text = partials[-1]
            
        final_text = final_text.strip()
        if final_text:
            self._logger.info(f"🎙️ ASR 唤醒监听 (命中唤醒词: {wakeword}): {final_text}")
        return final_text, wakeword

    def _drain_hotkey_event(self) -> bool:
        try:
            while True:
                evt = self._events.get_nowait()
                if evt == "hotkey":
                    return True
        except queue.Empty:
            return False
