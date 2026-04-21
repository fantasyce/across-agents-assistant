from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import edge_tts
import requests

from .playback import NSSoundPlayback

# Ensure MOSS-TTS-Nano is accessible
MOSS_TTS_PATH = "/Users/fanhcy/Documents/moss_tts_test/MOSS-TTS-Nano"
if MOSS_TTS_PATH not in sys.path:
    sys.path.insert(0, MOSS_TTS_PATH)

try:
    from onnx_tts_runtime import OnnxTtsRuntime
except ImportError:
    OnnxTtsRuntime = None


@dataclass(frozen=True)
class SpeakResult:
    interrupted: bool
    cached_text: str
    elapsed_sec: float


class TTSService:
    def __init__(self, temp_dir: Path):
        self._temp_dir = temp_dir
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        self._fallback_to_edge = False
        
        self._moss_runtime = None
        if OnnxTtsRuntime is not None:
            try:
                self._moss_runtime = OnnxTtsRuntime(
                    model_dir="/Users/fanhcy/Documents/moss_tts_test/models",
                    thread_count=4,
                    max_new_frames=1000,
                    do_sample=True,
                    sample_mode="fixed",
                )
            except Exception as e:
                import logging
                logging.getLogger("across_agents_assistant").error(f"Failed to initialize MOSS-TTS-Nano: {e}")
                self._moss_runtime = None

    def speak_interruptible(
        self,
        text: str,
        interrupt_monitor_factory,
        external_interrupt: Optional[threading.Event] = None,
        voice_edge: str = "zh-CN-XiaoxiaoNeural",
    ) -> SpeakResult:
        t0 = time.time()

        audio_path = self._generate_audio(text, voice_edge=voice_edge)
        generate_elapsed = time.time() - t0

        stop_playback = threading.Event()
        monitor_done = threading.Event()
        cached_text_holder = {"text": ""}
        external_interrupt = external_interrupt or threading.Event()

        def stop_all():
            stop_playback.set()
            monitor_done.set()

        playback = NSSoundPlayback()

        def playback_worker():
            ok = playback.play_mp3(audio_path)
            stop_all()
            return ok

        def monitor_worker():
            def on_final(final_text: str):
                cached_text_holder["text"] = final_text
                stop_playback.set()
                playback.stop()
                monitor_done.set()

            interrupt_monitor = interrupt_monitor_factory(on_final)
            try:
                interrupt_monitor.run(stop_condition=lambda: monitor_done.is_set())
            finally:
                monitor_done.set()

        play_thread = threading.Thread(target=playback_worker, daemon=True)
        monitor_thread = threading.Thread(target=monitor_worker, daemon=True)

        play_thread.start()
        monitor_thread.start()

        while play_thread.is_alive():
            if stop_playback.is_set() or external_interrupt.is_set():
                playback.stop()
                stop_playback.set()
            time.sleep(0.05)

        monitor_done.set()
        monitor_thread.join(timeout=2.0)
        cached = cached_text_holder["text"]
        interrupted = bool(cached) or external_interrupt.is_set()
        
        # return the time taken to generate the audio, not including playback time
        return SpeakResult(interrupted=interrupted, cached_text=cached, elapsed_sec=generate_elapsed)

    def _generate_audio(self, text: str, voice_edge: str) -> Path:
        if not self._fallback_to_edge and self._moss_runtime is not None:
            audio_path = self._temp_dir / "voice_reply.wav"
            try:
                self._generate_wav_moss(text, audio_path)
                return audio_path
            except Exception as e:
                import logging
                logging.getLogger("across_agents_assistant").error(f"MOSS-TTS-Nano failed: {e}. Falling back to edge_tts.")
                self._fallback_to_edge = True

        audio_path = self._temp_dir / "voice_reply.mp3"
        asyncio.run(self._generate_mp3_edge(text, audio_path, voice=voice_edge))
        return audio_path

    def _generate_wav_moss(self, text: str, output_path: Path):
        # We use zh_6.wav as the default voice for Nano
        voice_path = os.path.join(MOSS_TTS_PATH, "assets", "audio", "zh_6.wav")
        
        prepared = self._moss_runtime.prepare_synthesis_text(
            text=text,
            voice="",
            enable_wetext=False, # Because pynini might fail
            enable_normalize_tts_text=True,
        )
        
        self._moss_runtime.synthesize(
            text=prepared["text"],
            prompt_audio_path=voice_path,
            output_audio_path=str(output_path),
            sample_mode="fixed",
            do_sample=True,
            streaming=False,
            voice_clone_max_text_tokens=150,
            enable_wetext=False,
        )

    async def _generate_mp3_edge(self, text: str, mp3_path: Path, voice: str):
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(mp3_path))
