from __future__ import annotations

import asyncio
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import edge_tts
import requests

from .playback import NSSoundPlayback


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

    def speak_interruptible(
        self,
        text: str,
        interrupt_monitor_factory,
        external_interrupt: Optional[threading.Event] = None,
        voice_edge: str = "zh-CN-XiaoxiaoNeural",
    ) -> SpeakResult:
        t0 = time.time()
        mp3_path = self._temp_dir / "voice_reply.mp3"

        self._generate_mp3(text, mp3_path, voice_edge=voice_edge)
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
            ok = playback.play_mp3(mp3_path)
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

    def _generate_mp3(self, text: str, mp3_path: Path, voice_edge: str):
        if not self._fallback_to_edge:
            api_key = self._get_minimax_api_key()
            if api_key:
                try:
                    self._generate_mp3_minimax(text, mp3_path, api_key=api_key)
                    return
                except Exception:
                    self._fallback_to_edge = True
            else:
                self._fallback_to_edge = True

        asyncio.run(self._generate_mp3_edge(text, mp3_path, voice=voice_edge))

    def _get_minimax_api_key(self) -> str:
        api_key = os.environ.get("MINIMAX_API_KEY", "").strip()
        if api_key:
            return api_key
        try:
            import subprocess

            result = subprocess.run(
                ["security", "find-generic-password", "-s", "openclaw.minimax.api", "-w"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            key = result.stdout.strip()
            if key:
                return key
        except Exception:
            pass
            
        return ""

    def _generate_mp3_minimax(self, text: str, mp3_path: Path, api_key: str):
        # Update to the correct new endpoint url
        url = "https://api.minimax.chat/v1/t2a_v2"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "speech-2.8-hd",
            "text": text,
            "voice_setting": {"voice_id": "female-shaonv", "speed": 1.0, "vol": 1.0, "pitch": 0},
            "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
            "stream": False,
            "output_format": "hex",
        }
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code != 200:
            raise RuntimeError(f"Minimax API Error: {response.text}")
            
        result_data = response.json()
        if result_data.get("base_resp", {}).get("status_code", 0) != 0:
            raise RuntimeError(f"Minimax Error: {result_data.get('base_resp')}")
            
        audio_hex = result_data.get("data", {}).get("audio", "")
        if not audio_hex:
            raise RuntimeError("No audio data returned")
            
        import binascii
        audio_data = binascii.unhexlify(audio_hex)
        mp3_path.write_bytes(audio_data)

    async def _generate_mp3_edge(self, text: str, mp3_path: Path, voice: str):
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(mp3_path))
