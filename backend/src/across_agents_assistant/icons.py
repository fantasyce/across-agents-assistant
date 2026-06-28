from __future__ import annotations

import base64
from pathlib import Path


_ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"

_MIME_BY_SUFFIX = {
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}

_AGENT_ICON_FILES = {
    "openclaw": "agent.openclaw.webp",
    "local": "agent.local.webp",
    "hermes": "agent.hermes.webp",
    "claude": "agent.claude.svg",
    "claude-desktop": "agent.claude-desktop.svg",
    "codex": "agent.codex.webp",
    "kimi": "agent.kimi.svg",
    "opencode": "agent.opencode.svg",
    "cursor": "agent.cursor.svg",
    "agnes": "agent.agnes.svg",
    "deepseek": "agent.deepseek.svg",
    "minimax": "agent.minimax.svg",
}


def _asset_data_url(filename: str) -> str:
    path = _ICON_DIR / filename
    mime = _MIME_BY_SUFFIX.get(path.suffix)
    if mime is None:
        raise ValueError(f"Unsupported icon type: {filename}")
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


AGENT_ICONS = {agent_id: _asset_data_url(filename) for agent_id, filename in _AGENT_ICON_FILES.items()}
