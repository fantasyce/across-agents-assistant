from __future__ import annotations

import collections
import logging
import queue
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

import numpy as np

@dataclass
class SpeechResult:
    text: str
    is_final: bool
    error: Optional[str] = None

class SpeechClient:
    def __init__(
        self,
        socket_path: str = "/tmp/speech_cli.sock",
        speechcli_app_path: Optional[str] = None,
        locale: str = "zh-CN",
        auto_start: bool = True,
        exit_on_close: bool = False,
    ):
        self.locale = locale
        self._model = None
        self._vad = None
        self._connected = False
        self._is_recording = False
        self._audio_queue = queue.Queue()
        self._stream = None

    def ensure_server_running(self) -> bool:
        return True

    def connect(self) -> bool:
        import sys
        import os
        logger = logging.getLogger("across_agents_assistant")
        if self._connected:
            return True
        logger.info("⏳ 正在加载本地语音识别模型 (Faster-Whisper)...")
        try:
            from faster_whisper import WhisperModel
            import webrtcvad

            # Determine model path
            if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
                base_path = sys._MEIPASS
            else:
                # If running normally, root is 4 levels up from this file
                base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            
            model_path = os.path.join(base_path, "models", "whisper-small")
            if not os.path.exists(model_path):
                logger.warning(f"Local model not found at {model_path}, falling back to download 'small'")
                model_path = "small"

            # Load the model
            # Use small for better accuracy while keeping fast CPU inference
            self._model = WhisperModel(model_path, device="cpu", compute_type="int8")
            
            # Initialize VAD
            self._vad = webrtcvad.Vad(2) # 0 to 3, 3 is most aggressive
            
            self._connected = True
            logger.info("✅ 本地语音识别模型加载完成")
            return True
        except Exception as e:
            logger.error(f"Failed to load local ASR model: {e}")
            return False

    def close(self):
        import logging
        logger = logging.getLogger("across_agents_assistant")
        logger.info("🧹 正在关闭音频流并释放模型资源...")
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
            
        self.stop()
        
        # Force model cleanup
        if hasattr(self, '_model') and self._model is not None:
            import gc
            self._model = None
            gc.collect()
            
        self._connected = False
        logger.info("✅ 语音模块已安全关闭")

    def exit_server(self) -> bool:
        self.close()
        return True

    def start(self) -> bool:
        import sounddevice as sd
        logger = logging.getLogger("across_agents_assistant")
        if not self._connected:
            self.connect()

        if self._is_recording:
            return True

        self._audio_queue = queue.Queue()

        def audio_callback(indata, frames, time_info, status):
            if status:
                pass
            if self._is_recording:
                self._audio_queue.put(indata.copy())

        if self._stream is None:
            try:
                self._stream = sd.InputStream(
                    samplerate=16000,
                    channels=1,
                    dtype="int16",
                    blocksize=480, # 30ms at 16kHz
                    callback=audio_callback,
                )
                self._stream.start()
            except Exception as e:
                logger.error(f"Failed to start audio stream: {e}")
                return False
        else:
            try:
                if not self._stream.active:
                    self._stream.start()
            except Exception as e:
                logger.error(f"Failed to resume audio stream: {e}")
                return False
                
        self._is_recording = True
        return True

    def stop(self) -> bool:
        self._is_recording = False
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                pass
        return True

    def _transcribe(self, audio_frames: List[np.ndarray]) -> str:
        if not audio_frames or not self._model:
            return ""
        
        # Concatenate frames
        audio_data = np.concatenate(audio_frames, axis=0)
        
        # Convert to float32 between -1 and 1
        audio_float32 = audio_data.astype(np.float32) / 32768.0
        
        # Ensure 1D
        if len(audio_float32.shape) > 1:
            audio_float32 = audio_float32.squeeze()
            
        try:
            segments, info = self._model.transcribe(
                audio_float32, 
                language="zh",
                beam_size=5,
                vad_filter=True,
                without_timestamps=True,
                initial_prompt="以下是普通话的句子，这是一段简体中文。"
            )
            
            text = "".join(segment.text for segment in segments)
            return text.strip()
        except Exception as e:
            logging.getLogger("across_agents_assistant").error(f"Transcription error: {e}")
            return ""

    def listen(self, timeout: float = 10.0, stop_condition: Optional[Callable[[], bool]] = None) -> List[SpeechResult]:
        logger = logging.getLogger("across_agents_assistant")
        if not self._is_recording:
            self.start()

        # 开始监听前，清空队列里积压的脏数据（比如TTS播放时的回音）
        if hasattr(self, '_audio_queue') and self._audio_queue:
            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except queue.Empty:
                    break

        start_time = time.time()
        
        # Parameters for VAD
        frame_duration_ms = 30
        sample_rate = 16000
        
        # Ring buffer to keep some pre-speech audio
        num_padding_frames = int(300 / frame_duration_ms) # 300ms
        ring_buffer = collections.deque(maxlen=num_padding_frames)
        
        triggered = False
        voiced_frames = []
        
        # Require multiple consecutive voiced frames to trigger
        trigger_threshold = 3
        voiced_count = 0
        
        # Require multiple consecutive unvoiced frames to stop
        # Decrease stop threshold to make it more responsive when user finishes talking
        stop_threshold = int(600 / frame_duration_ms) # 0.6 seconds of silence
        unvoiced_count = 0
        
        results = []
        last_transcribe_time = time.time()
        
        final_text_cached = None
        
        while True:
            if stop_condition and stop_condition():
                break
                
            elapsed = time.time() - start_time
            if not triggered and elapsed > timeout:
                break
                
            try:
                frame = self._audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            # Check VAD
            is_speech = self._vad.is_speech(frame.tobytes(), sample_rate)
            
            if not triggered:
                ring_buffer.append(frame)
                if is_speech:
                    voiced_count += 1
                    if voiced_count >= trigger_threshold:
                        triggered = True
                        voiced_frames.extend(ring_buffer)
                        ring_buffer.clear()
                else:
                    voiced_count = max(0, voiced_count - 1)
            else:
                voiced_frames.append(frame)
                
                # Periodically provide partial results if speech is long
                if time.time() - last_transcribe_time > 1.0 and len(voiced_frames) > 10:
                    partial_text = self._transcribe(voiced_frames)
                    if partial_text:
                        results.append(SpeechResult(text=partial_text, is_final=False))
                        last_transcribe_time = time.time()
                
                if is_speech:
                    unvoiced_count = 0
                else:
                    unvoiced_count += 1
                    if unvoiced_count >= stop_threshold:
                        # 校验这段“声音”是否真的是语音，而不是背景噪音
                        check_text = self._transcribe(voiced_frames)
                        if check_text:
                            final_text_cached = check_text
                            break
                        else:
                            # 只是噪音（False alarm），重置状态并继续监听，直到超时
                            triggered = False
                            voiced_frames = []
                            voiced_count = 0
                            unvoiced_count = 0
                            ring_buffer.clear()
                        
            # hard timeout for safety
            if elapsed > 60.0:
                break

        if triggered and voiced_frames:
            final_text = final_text_cached or self._transcribe(voiced_frames)
            if final_text:
                results.append(SpeechResult(text=final_text, is_final=True))
                
        return results

    def listen_continuous(self, callback: Callable[[SpeechResult], None], stop_condition: Callable[[], bool]):
        logger = logging.getLogger("across_agents_assistant")
        if not self._is_recording:
            return

        # Parameters for VAD
        frame_duration_ms = 30
        sample_rate = 16000
        
        num_padding_frames = int(300 / frame_duration_ms) # 300ms
        ring_buffer = collections.deque(maxlen=num_padding_frames)
        
        triggered = False
        voiced_frames = []
        
        trigger_threshold = 3
        voiced_count = 0
        
        stop_threshold = int(800 / frame_duration_ms) # 0.8 seconds of silence
        unvoiced_count = 0
        
        last_transcribe_time = time.time()
        
        while True:
            if stop_condition and stop_condition():
                break
                
            try:
                frame = self._audio_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            is_speech = self._vad.is_speech(frame.tobytes(), sample_rate)
            
            if not triggered:
                ring_buffer.append(frame)
                if is_speech:
                    voiced_count += 1
                    if voiced_count >= trigger_threshold:
                        triggered = True
                        voiced_frames.extend(ring_buffer)
                        ring_buffer.clear()
                else:
                    voiced_count = max(0, voiced_count - 1)
            else:
                voiced_frames.append(frame)
                
                if time.time() - last_transcribe_time > 1.0 and len(voiced_frames) > 10:
                    partial_text = self._transcribe(voiced_frames)
                    if partial_text:
                        callback(SpeechResult(text=partial_text, is_final=False))
                        last_transcribe_time = time.time()
                
                if is_speech:
                    unvoiced_count = 0
                else:
                    unvoiced_count += 1
                    if unvoiced_count >= stop_threshold:
                        final_text = self._transcribe(voiced_frames)
                        if final_text:
                            callback(SpeechResult(text=final_text, is_final=True))
                        
                        # Reset for next utterance
                        triggered = False
                        voiced_frames = []
                        voiced_count = 0
                        unvoiced_count = 0
                        ring_buffer.clear()

def kill_speechcli_process():
    # No-op in Option 2
    pass
