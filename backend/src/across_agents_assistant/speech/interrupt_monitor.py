from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .speech_client import SpeechClient
from ..wakeword import contains_wake_word

@dataclass
class SpeechInterruptMonitor:
    speech_client: SpeechClient
    on_final: Callable[[str], None]
    wake_word: str

    def run(self, stop_condition: Callable[[], bool]):
        # Just to be safe, delay start of interrupt listening
        import time
        time.sleep(0.5)

        # Connect explicitly
        if not self.speech_client.connect():
            return

        if not self.speech_client.start():
            self.speech_client.close()
            return

        def handle_result(result):
            if result.error:
                return
            if result.is_final and result.text:
                # 只在命中唤醒词时打断，防止被自己的 TTS 声音或其他噪音误触发
                if contains_wake_word(result.text, self.wake_word):
                    self.on_final(result.text)

        try:
            self.speech_client.listen_continuous(handle_result, stop_condition=stop_condition)
        finally:
            try:
                self.speech_client.stop()
            except Exception:
                pass
