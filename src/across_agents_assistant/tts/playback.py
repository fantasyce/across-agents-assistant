from __future__ import annotations

import threading
import time
from pathlib import Path


class NSSoundPlayback:
    def __init__(self):
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def play_mp3(self, mp3_path: Path) -> bool:
        self._stop_event.clear()
        from AppKit import NSSound, NSURL

        url = NSURL.fileURLWithPath_(str(mp3_path))
        sound = NSSound.alloc().initWithContentsOfURL_byReference_(url, True)
        if not sound:
            return False
        sound.play()
        while sound.isPlaying():
            if self._stop_event.is_set():
                sound.stop()
                break
            time.sleep(0.05)
        return True

