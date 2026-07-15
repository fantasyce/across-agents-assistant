from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    local_agent: str = "main"
    log_dir: str = "logs"
    log_file: str = "across-agents-assistant.log"


def load_config(project_root: Path) -> AppConfig:
    # Retained only for compatibility with historical imports. Voice input now
    # belongs to the native Swift host and has no Python socket or wake-word
    # configuration.
    _ = project_root
    return AppConfig()
