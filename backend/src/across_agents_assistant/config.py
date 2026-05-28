from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .paths import speech_socket_path as default_speech_socket_path


@dataclass(frozen=True)
class AppConfig:
    speech_socket_path: str = default_speech_socket_path()
    speechcli_app_path: str | None = None
    local_agent: str = "main"
    wake_word: str = "小落"
    realtime_enabled_default: bool = True
    session_timeout_sec: int = 120
    control_double_tap_ms: int = 400
    log_dir: str = "logs"
    log_file: str = "across-agents-assistant.log"


def load_config(project_root: Path) -> AppConfig:
    speechcli_app_default = str(project_root / "speech_cli" / "SpeechCLI_fixed.app")

    speechcli_app_path = os.environ.get("ACROSS_AGENTS_ASSISTANT_SPEECHCLI_APP") or speechcli_app_default
    speech_socket_path = os.environ.get("ACROSS_AGENTS_ASSISTANT_SPEECH_SOCKET") or default_speech_socket_path()
    local_agent = os.environ.get("ACROSS_AGENTS_ASSISTANT_LOCAL_AGENT") or "main"
    wake_word = os.environ.get("ACROSS_AGENTS_ASSISTANT_WAKE_WORD") or "小落小落"
    realtime_enabled_default = (os.environ.get("ACROSS_AGENTS_ASSISTANT_REALTIME_ENABLED") or "1").lower() in (
        "1",
        "true",
        "yes",
    )

    session_timeout_sec = int(os.environ.get("ACROSS_AGENTS_ASSISTANT_SESSION_TIMEOUT_SEC") or "120")
    control_double_tap_ms = int(os.environ.get("ACROSS_AGENTS_ASSISTANT_CONTROL_DOUBLE_TAP_MS") or "400")

    return AppConfig(
        speech_socket_path=speech_socket_path,
        speechcli_app_path=speechcli_app_path,
        local_agent=local_agent,
        wake_word=wake_word,
        realtime_enabled_default=realtime_enabled_default,
        session_timeout_sec=session_timeout_sec,
        control_double_tap_ms=control_double_tap_ms,
    )
