from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .protocol import criterion_id, normalize_goal_contract


_EXPLICIT_SOURCES = {"explicit_user_request", "user_confirmed"}


def _created_at(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    text = str(value or "").strip()
    return text or "1970-01-01T00:00:00Z"


def delivery_contract_to_goal_contract(
    delivery_contract: Mapping[str, Any],
    *,
    statement: str,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Project a legacy Delivery Contract without upgrading inferred trust."""

    task_id = str(delivery_contract.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("delivery contract task_id is required")
    created_at = _created_at(delivery_contract.get("created_at"))
    criteria: list[dict[str, Any]] = []
    for probe in delivery_contract.get("acceptance_probes") or []:
        probe_id = str(probe.get("id") or "").strip()
        if not probe_id:
            raise ValueError("delivery acceptance probe id is required")
        validator_kind = str(probe.get("probe_type") or "legacy_probe").strip()
        description = str(
            probe.get("description") or probe.get("command") or f"Satisfy legacy probe {probe_id}"
        ).strip()
        source = (
            "user_confirmed"
            if str(probe.get("source") or "").strip() in _EXPLICIT_SOURCES
            else "legacy_inferred"
        )
        criteria.append(
            {
                "criterion_id": criterion_id(probe_id, "legacy_probe"),
                "description": description,
                "required": bool(probe.get("required", True)),
                "validator_kind": validator_kind,
                "review_policy": "human" if validator_kind == "installed_user_journey" else "automatic",
                "source": source,
                "legacy_probe_id": probe_id,
            }
        )
    if not criteria:
        criteria.append(
            {
                "criterion_id": criterion_id("legacy-delivery-acceptance", "legacy_probe"),
                "description": "Legacy delivery acceptance must be recorded.",
                "required": True,
                "validator_kind": "legacy_acceptance",
                "review_policy": "human",
                "source": "legacy_inferred",
                "legacy_probe_id": "legacy-delivery-acceptance",
            }
        )

    includes = [
        str(item.get("description") or item.get("path_hint") or item.get("id") or "").strip()
        for group in ("capabilities", "deliverables")
        for item in (delivery_contract.get(group) or [])
    ]
    excludes = [
        str(item.get("description") or item.get("value") or item.get("id") or "").strip()
        for item in (delivery_contract.get("constraints") or [])
    ]
    contract: dict[str, Any] = {
        "schema_version": "across-goal-contract/1.0",
        "goal_id": f"goal-{task_id}",
        "revision": 1,
        "task_id": task_id,
        "statement": statement,
        "success_outcome": statement,
        "scope": {
            "includes": [item for item in includes if item],
            "excludes": [item for item in excludes if item],
        },
        "acceptance_criteria": criteria,
        "dependencies": [],
        "execution_profile": (
            "orchestrated" if delivery_contract.get("delivery_mode") == "orchestrated" else "direct"
        ),
        "source": "migration",
        "created_at": created_at,
    }
    if confirmed:
        contract["confirmed_by"] = "human:migration"
        contract["confirmed_at"] = created_at
    return normalize_goal_contract(contract)


def project_acceptance_records(
    criteria: Iterable[Mapping[str, Any]],
    acceptance_records: Iterable[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Map legacy aggregate records into independent criterion verdicts."""

    records_by_probe: dict[str, list[Mapping[str, Any]]] = {}
    for record in acceptance_records:
        records_by_probe.setdefault(str(record.get("probe_id") or ""), []).append(record)
    result: dict[str, dict[str, Any]] = {}
    for criterion in criteria:
        identifier = str(criterion.get("criterion_id") or "")
        probe_id = str(criterion.get("legacy_probe_id") or "")
        records = records_by_probe.get(probe_id, [])
        decisions = [str(record.get("decision") or "").lower() for record in records]
        if any(decision in {"rejected", "failed"} for decision in decisions):
            verdict = "failed"
        elif any(decision in {"accepted", "approved", "passed"} for decision in decisions):
            verdict = "verified"
        else:
            verdict = "missing"
        result[identifier] = {
            "criterion_id": identifier,
            "verdict": verdict,
            "acceptance_ids": [
                str(record.get("acceptance_id")) for record in records if record.get("acceptance_id")
            ],
            "authority": "legacy_acceptance_adapter",
        }
    return result


def project_delivery_probe_results(
    delivery_contract: Mapping[str, Any],
    probe_results: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Expose legacy probe outcomes as criterion-level facts, never one aggregate pass."""

    results = {str(item.get("id") or ""): item for item in probe_results}
    projected: list[dict[str, Any]] = []
    for probe in delivery_contract.get("acceptance_probes") or []:
        if not probe.get("required", True):
            continue
        probe_id = str(probe.get("id") or "")
        result = results.get(probe_id)
        if result is None:
            verdict = "missing"
        else:
            verdict = "verified" if result.get("passed") else "failed"
        projected.append(
            {
                "criterion_id": criterion_id(probe_id, "legacy_probe"),
                "legacy_probe_id": probe_id,
                "verdict": verdict,
                "evidence_ids": (
                    [str(result["evidence_id"])] if result and result.get("evidence_id") else []
                ),
                "authority": "legacy_delivery_probe_adapter",
            }
        )
    return projected
