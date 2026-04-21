from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Deque

from pynput import keyboard


class ControlDoubleTapListener:
    def __init__(self, on_trigger: Callable[[], None], window_ms: int = 400):
        self._on_trigger = on_trigger
        self._window_ms = window_ms
        self._tap_times: Deque[float] = deque(maxlen=10)
        self._listener = None
        self._lock = threading.Lock()

    def start(self):
        if self._listener:
            return
        self._listener = keyboard.Listener(on_press=self._on_press)
        self._listener.start()

    def stop(self):
        if not self._listener:
            return
        self._listener.stop()
        self._listener = None

    def _on_press(self, key):
        if key not in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            return

        now = time.time()
        with self._lock:
            self._tap_times.append(now)
            while self._tap_times and (now - self._tap_times[0]) > 1.0:
                self._tap_times.popleft()

            if len(self._tap_times) < 2:
                return

            t0, t1 = self._tap_times[-2], self._tap_times[-1]
            if (t1 - t0) * 1000 < self._window_ms:
                self._tap_times.clear()
                self._on_trigger()

