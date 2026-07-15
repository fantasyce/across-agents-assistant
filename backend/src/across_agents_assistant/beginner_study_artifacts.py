"""Privacy-bounded result artifacts for supervised beginner-study sessions."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from .paths import component_data_home


BEGINNER_RESULT_SCHEMA = "across-no-key-demo-result/1.0"
_RUN_ID = re.compile(r"^run-[A-Za-z0-9][A-Za-z0-9._-]{1,159}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_STUDY_PROFILE = re.compile(r"^[a-f0-9]{16}$")
_BOUNDED_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_PUBLIC_FIELDS = (
    "schema_version",
    "pattern_id",
    "mission_id",
    "run_id",
    "status",
    "verdict",
    "evidence_route",
    "gates",
    "policy",
    "evidence_sha256",
    "goal_sha256",
    "next_action_id",
    "next_action",
    "result_sha256",
)


def persist_beginner_study_result(
    payload: Mapping[str, Any],
    *,
    env: Mapping[str, str] | None = None,
) -> Path | None:
    """Persist a safe result subset when the CLI returned a real bounded run.

    Goals, transcripts, project paths, and diagnostic output are intentionally
    excluded. Invalid or incomplete results remain visible to the caller but do
    not become study evidence.
    """

    source = env if env is not None else os.environ
    if not _STUDY_PROFILE.fullmatch(str(source.get("ACROSS_STUDY_PROFILE_ID") or "")):
        return None
    sanitized = sanitized_beginner_study_result(payload)
    if sanitized is None:
        return None
    run_id = sanitized["run_id"]
    root = component_data_home(env=env) / "beginner-study-results"
    root.mkdir(parents=True, exist_ok=True)
    destination = root / f"{run_id}.json"
    temporary = root / f".{run_id}.{os.getpid()}.tmp"
    data = (json.dumps(sanitized, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def sanitized_beginner_study_result(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return the exact privacy-safe result envelope, or reject it.

    The Autopilot result hash covers this compact envelope.  Rebuilding and
    hashing the public subset here means an invalid plugin response cannot be
    persisted merely because its individual hash-shaped fields look plausible.
    """

    if payload.get("schema_version") != BEGINNER_RESULT_SCHEMA:
        return None
    run_id = str(payload.get("run_id") or "")
    if not _RUN_ID.fullmatch(run_id):
        return None
    if any(not _SHA256.fullmatch(str(payload.get(key) or "")) for key in (
        "evidence_sha256", "goal_sha256", "result_sha256"
    )):
        return None
    pattern_id = str(payload.get("pattern_id") or "")
    mission_id = str(payload.get("mission_id") or "")
    status = str(payload.get("status") or "")
    verdict = str(payload.get("verdict") or "")
    next_action_id = str(payload.get("next_action_id") or "")
    next_action = str(payload.get("next_action") or "")
    if not all(_BOUNDED_ID.fullmatch(value) for value in (pattern_id, mission_id, next_action_id)):
        return None
    if status not in {"completed", "failed", "blocked", "cancelled"}:
        return None
    if verdict not in {"verified", "needs_attention"} or not next_action.strip():
        return None
    if payload.get("evidence_route") != f"run://{run_id}/evidence":
        return None

    policy = payload.get("policy")
    gates = payload.get("gates")
    if not isinstance(policy, Mapping) or not isinstance(gates, list) or not gates:
        return None
    public = {key: payload.get(key) for key in _PUBLIC_FIELDS if key in payload}
    for required in (
        "schema_version", "pattern_id", "mission_id", "run_id", "status", "verdict",
        "evidence_route", "gates", "policy", "evidence_sha256", "goal_sha256",
        "next_action_id", "next_action", "result_sha256",
    ):
        if required not in public:
            return None
    bounded_gates: list[dict[str, Any]] = []
    gate_ids: set[str] = set()
    for gate in gates:
        if not isinstance(gate, Mapping):
            return None
        gate_id = str(gate.get("id") or "")
        gate_status = str(gate.get("status") or "")
        gate_required = gate.get("required")
        if (
            not _BOUNDED_ID.fullmatch(gate_id)
            or gate_id in gate_ids
            or gate_status not in {"passed", "failed", "blocked", "skipped"}
            or not isinstance(gate_required, bool)
        ):
            return None
        gate_ids.add(gate_id)
        bounded_gates.append({"id": gate_id, "status": gate_status, "required": gate_required})
    public["gates"] = bounded_gates
    public["policy"] = {
        "provider_key_used": policy.get("provider_key_used"),
        "network_used": policy.get("network_used"),
        "model_calls": policy.get("model_calls"),
        "external_side_effects_performed": policy.get("external_side_effects_performed"),
    }
    if public["policy"] != {
        "provider_key_used": False,
        "network_used": False,
        "model_calls": 0,
        "external_side_effects_performed": False,
    }:
        return None
    unsigned = dict(public)
    result_sha256 = str(unsigned.pop("result_sha256"))
    canonical = json.dumps(
        unsigned,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != result_sha256:
        return None
    return public
