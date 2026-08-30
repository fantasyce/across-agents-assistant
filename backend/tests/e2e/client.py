"""Shared E2E HTTP client utilities.

The packaged macOS app exposes the backend through a Unix domain socket. These
helpers keep the external E2E tests aligned with that product path while still
allowing a plain HTTP URL for development servers.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

import httpx

DEFAULT_SOCKET = os.path.expanduser("~/.across/run/across-agents-assistant/across-agents.sock")
SOCKET = os.path.expanduser(os.environ.get("ACROSS_AGENTS_SOCKET", DEFAULT_SOCKET))
BASE = os.environ.get("ACROSS_AGENTS_API")
LOCAL_AGENT_PRIORITY = ("codex", "kimi", "claude", "claude-desktop", "opencode", "cursor", "hermes", "openclaw")


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


def require_live_model_route() -> dict[str, str]:
    """Resolve one real model route or fail the release gate.

    An isolated release profile commonly has no copied cloud credentials. A
    runnable, authenticated local Agent is an equally real model route and is
    preferred when explicitly selected for the gate.
    """
    requested_agent = os.environ.get("ACROSS_AGENTS_LIVE_E2E_AGENT", "").strip().lower()
    detected = request("GET", "/api/agents/detect")
    if requested_agent:
        state = detected.get(requested_agent) if isinstance(detected, dict) else None
        if not isinstance(state, dict) or not state.get("available"):
            raise AssertionError(
                f"Requested live E2E Agent is unavailable: {requested_agent}"
            )
        return {"kind": "local_agent", "id": requested_agent}

    providers = configured_providers()
    if providers:
        return {"kind": "provider", "id": providers[0]}

    if isinstance(detected, dict):
        for agent_id in LOCAL_AGENT_PRIORITY:
            state = detected.get(agent_id)
            if isinstance(state, dict) and state.get("available"):
                return {"kind": "local_agent", "id": agent_id}

    raise AssertionError(
        "Live E2E requires a real model route; configure a cloud provider or an available local Agent"
    )


def live_task_agent_fields(route: dict[str, str] | None = None) -> dict[str, Any]:
    selected = route or require_live_model_route()
    model_id = str(selected.get("id") or "").strip()
    if not model_id:
        raise AssertionError("Live E2E model route has no id")
    return {
        "owner_agent": model_id,
        "allowed_subtask_agents": [model_id],
    }


def live_project_dir(label: str) -> Path:
    """Create a uniquely attributable project under the runner-owned root."""
    root_value = os.environ.get("ACROSS_AGENTS_LIVE_E2E_PROJECT_ROOT", "").strip()
    if not root_value:
        raise AssertionError("ACROSS_AGENTS_LIVE_E2E_PROJECT_ROOT is required")
    root = Path(root_value).expanduser().resolve()
    slug = re.sub(r"[^a-z0-9]+", "-", str(label).strip().lower()).strip("-") or "task"
    project = root / f"{slug}-{uuid.uuid4().hex[:12]}"
    project.mkdir(parents=True, exist_ok=False)
    return project


def assert_release_task_checkpoint(info: dict[str, Any]) -> None:
    """Require deterministic delivery gates before a real human UI review.

    Generic goals intentionally stop at ``manual_required`` because an
    automated runner must not impersonate the user. The installed-App journey
    performs that final decision separately.
    """
    status = str(info.get("status") or "unknown")
    assert status == "completed", f"Task ended with unexpected status: {status}"
    artifacts = info.get("artifacts") or []
    assert artifacts, f"Task produced no artifacts: {info}"
    records = info.get("acceptance_records") or []
    assert records, f"Task has no acceptance records: {info}"
    gate = str((info.get("delivery_report") or {}).get("quality_gate") or "")
    assert gate in {"passed", "manual_required"}, f"Delivery gate did not pass: {gate}"
    record = records[0]
    assert record.get("deterministic_passed") is True, (
        f"Task did not pass deterministic acceptance gates: {record}"
    )
    assert not (record.get("failed_checks") or []), f"Acceptance checks failed: {record}"
    if gate == "manual_required":
        assert record.get("decision") == "review", record
