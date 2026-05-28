"""Shared E2E HTTP client utilities.

The packaged macOS app exposes the backend through a Unix domain socket. These
helpers keep the external E2E tests aligned with that product path while still
allowing a plain HTTP URL for development servers.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

DEFAULT_SOCKET = os.path.expanduser("~/.across_agents/run/across-agents.sock")
SOCKET = os.path.expanduser(os.environ.get("ACROSS_AGENTS_SOCKET", DEFAULT_SOCKET))
BASE = os.environ.get("ACROSS_AGENTS_API")


def _use_socket() -> bool:
    return not BASE or BASE == "http://backend" or BASE.startswith("unix://")


def base_label() -> str:
    if _use_socket():
        return f"unix://{SOCKET}"
    return BASE or "http://backend"


def request(method: str, path: str, body: dict[str, Any] | None = None, expect: int = 200) -> dict[str, Any]:
    if _use_socket():
        if not Path(SOCKET).exists():
            raise AssertionError(f"Backend socket is not available: {SOCKET}")
        transport = httpx.HTTPTransport(uds=SOCKET)
        url = f"http://backend{path}"
    else:
        transport = None
        url = f"{BASE}{path}"

    with httpx.Client(transport=transport, timeout=30) as client:
        response = client.request(method, url, json=body)

    if response.status_code != expect:
        raise AssertionError(f"Expected status {expect}, got {response.status_code}: {response.text}")
    if not response.content:
        return {}
    return response.json()


def configured_providers() -> list[str]:
    status = request("GET", "/api/keys/status")
    providers = status.get("providers", [])
    if isinstance(providers, dict):
        return [
            provider_id
            for provider_id, provider_status in providers.items()
            if provider_status == "configured"
        ]
    return [
        provider["provider_id"]
        for provider in providers
        if provider.get("status") == "configured"
    ]
