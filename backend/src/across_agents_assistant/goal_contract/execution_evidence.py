from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Any, Mapping


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_BLOCKING_QUALITY = {"failed", "failure", "partial", "blocked", "error", "inconsistent"}


def _digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _artifact_identity(artifact: Mapping[str, Any], index: int) -> str:
    return str(
        artifact.get("id")
        or artifact.get("artifact_id")
        or artifact.get("logical_name")
        or artifact.get("name")
        or artifact.get("path")
        or f"artifact-{index + 1}"
    )


def _artifact_digest(artifact: Mapping[str, Any]) -> str:
    supplied = str(artifact.get("sha256") or artifact.get("digest") or "").lower()
    return supplied if _SHA256.fullmatch(supplied) else _digest(dict(artifact))


def _matches_deliverable(artifact: Mapping[str, Any], deliverable: str) -> bool:
    expected = deliverable.replace("\\", "/").strip("/").lower()
    expected_path = PurePosixPath(expected)
    expected_names = {expected, expected_path.name, expected_path.stem}
    for field in ("id", "artifact_id", "logical_name", "name", "path"):
        raw = str(artifact.get(field) or "").replace("\\", "/").strip("/").lower()
        if not raw:
            continue
        path = PurePosixPath(raw)
        candidates = {raw, path.name, path.stem}
        if raw.endswith(expected) or expected_names.intersection(candidates):
            return True
    return False


def _valid_runtime_receipt(runtime_evidence: Mapping[str, Any] | None) -> tuple[bool, str | None, dict[str, Any]]:
    if not runtime_evidence or "goal_execution_receipt" not in runtime_evidence:
        return True, None, {}
    receipt = runtime_evidence.get("goal_execution_receipt")
    if not isinstance(receipt, Mapping):
        return False, None, {}
    receipt_hash = str(receipt.get("receipt_hash") or "").lower()
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    if not _SHA256.fullmatch(receipt_hash) or _digest(unsigned) != receipt_hash:
        return False, None, {}
    return True, receipt_hash, dict(receipt)


def build_execution_evidence_material(
    contract: Mapping[str, Any],
    task_payload: Mapping[str, Any],
    runtime_evidence: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build one verified execution material record per satisfied criterion output."""

    if str(task_payload.get("status") or "") != "completed":
        return []
    quality_values = {
        str(dict(task_payload.get("quality_health") or {}).get("quality_gate") or "").lower(),
        str(dict(task_payload.get("quality_health") or {}).get("delivery_quality") or "").lower(),
        str(dict(task_payload.get("delivery_report") or {}).get("quality_gate") or "").lower(),
    }
    if _BLOCKING_QUALITY.intersection(value for value in quality_values if value):
        return []
    receipt_valid, receipt_hash, receipt = _valid_runtime_receipt(runtime_evidence)
    if not receipt_valid:
        return []

    artifacts = [dict(item) for item in task_payload.get("artifacts") or () if isinstance(item, Mapping)]
    includes = [str(item) for item in dict(contract.get("scope") or {}).get("includes") or ()]
    criteria = [item for item in contract.get("acceptance_criteria") or () if item.get("required", True)]
    direct = str(contract.get("execution_profile") or "") == "direct" or (
        not task_payload.get("external_task") and str(task_payload.get("delivery_mode") or "") == "direct"
    )
    executor = "aaa-direct-agent" if direct else "across-orchestrator"
    remote = dict(task_payload.get("remote_execution") or {})
    if remote and not direct:
        executor = "across-worker"

    task_id = str(task_payload.get("task_id") or contract.get("task_id") or "")
    identity_seed = {
        "task_id": task_id,
        "artifacts": artifacts,
        "direct_response": task_payload.get("direct_response"),
        "remote_execution": remote,
        "receipt_hash": receipt_hash,
    }
    identity_hash = _digest(identity_seed)
    run_id = str(receipt.get("run_id") or remote.get("run_id") or "").strip()
    if not run_id:
        run_id = f"{'direct' if direct else 'orchestrator'}-run-{identity_hash[:20]}"
    attempt_id = str(receipt.get("attempt_id") or remote.get("attempt_id") or "").strip()
    if not attempt_id:
        attempt_id = f"{'direct' if direct else 'orchestrator'}-attempt-{identity_hash[20:40]}"

    result: list[dict[str, Any]] = []
    for index, criterion in enumerate(criteria):
        criterion_id = str(criterion.get("criterion_id") or "")
        deliverable = includes[index] if index < len(includes) else ""
        matched = [artifact for artifact in artifacts if deliverable and _matches_deliverable(artifact, deliverable)]
        if not matched and len(criteria) == 1 and len(artifacts) == 1:
            matched = artifacts
        artifact_digests = {
            _artifact_identity(artifact, artifact_index): _artifact_digest(artifact)
            for artifact_index, artifact in enumerate(matched)
        }
        if not artifact_digests and direct and len(criteria) == 1:
            response = str(task_payload.get("direct_response") or "").strip()
            if response:
                artifact_digests = {"direct-response": hashlib.sha256(response.encode("utf-8")).hexdigest()}
        if not criterion_id or not artifact_digests:
            continue
        input_fingerprint = _digest(
            {
                "goal_id": contract.get("goal_id"),
                "goal_revision": contract.get("revision"),
                "criterion_id": criterion_id,
                "task_identity": identity_seed,
                "artifact_digests": artifact_digests,
            }
        )
        result.append(
            {
                "criterion_id": criterion_id,
                "artifact_digests": artifact_digests,
                "executor": executor,
                "run_id": run_id,
                "attempt_id": attempt_id,
                "validator_id": "aaa-host:direct-result-validator" if direct else "aaa-host:artifact-validator",
                "validator_authority": "aaa-host",
                "verdict": "verified",
                "input_fingerprint": input_fingerprint,
                "receipt_hash": receipt_hash,
            }
        )
    return result
