"""Pure composition of bounded, verified promotion evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
import math
import re
from typing import Any

from .agent_interop_e2e import plugin_provenance_digest
from .autopilot_promotion_review import build_promotion_review_packet
from .execution_trajectory import verify_evidence_receipt


PROMOTION_PACKAGE_SCHEMA = "across-promotion-package/1.0"
EVIDENCE_GRAPH_SCHEMA = "across-evidence-graph/1.0"
COMPATIBILITY_SCHEMA = "across-first-party-mcp-compatibility/1.0"
REQUIRED_PLUGIN_IDS = frozenset(
    {
        "across-context",
        "across-orchestrator",
        "across-autopilot",
    }
)

_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_HEX_40 = re.compile(r"[0-9a-f]{40}")
_HEX_64 = re.compile(r"[0-9a-f]{64}")
_WINDOWS_ABSOLUTE = re.compile(r"[A-Za-z]:[/\\]")
_MAX_TASKS = 256
_MAX_CHANGED_FILES = 256
_MAX_GRAPH_NODES = 10_000
_MAX_GRAPH_EDGES = 20_000
_MAX_TREE_DEPTH = 64

_PASSED_CHECK_IDS = (
    "autopilot_evidence_valid",
    "candidate_binding_matches",
    "candidate_review_ready",
    "changed_paths_safe",
    "evidence_graph_valid",
    "finite_values",
    "identifiers_valid",
    "plugin_compatibility_ready",
    "plugin_lifecycle_ready",
    "plugin_provenance_matches",
    "plugin_set_complete",
    "plugin_versions_match",
    "release_ready",
    "run_binding_matches",
    "run_completed",
    "task_receipt_bindings_match",
    "task_receipts_ready",
    "task_receipts_verified",
    "task_set_complete",
)


class PromotionPackageBlocked(ValueError):
    """Fixed public failure containing only sorted package check identifiers."""

    def __init__(self, check_ids: Sequence[str]):
        self.check_ids = tuple(sorted({str(check_id) for check_id in check_ids if check_id}))
        super().__init__("promotion package evidence is blocked")


def package_sha256(document: Mapping[str, Any]) -> str:
    """Return the canonical content digest for an immutable package document."""

    try:
        encoded = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise ValueError("promotion package document is invalid") from exc
    return sha256(encoded).hexdigest()


def build_promotion_package(
    *,
    run_id: str,
    run_status: Mapping[str, Any],
    autopilot_evidence: Mapping[str, Any],
    task_evidence: Sequence[Mapping[str, Any]],
    evidence_graph: Mapping[str, Any],
    plugin_rows: Sequence[Mapping[str, Any]],
    plugin_descriptors: Mapping[str, Mapping[str, Any]],
    compatibility_report: Mapping[str, Any],
    release_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Compose one deterministic package from already-loaded host evidence."""

    inputs = (
        run_id,
        run_status,
        autopilot_evidence,
        task_evidence,
        evidence_graph,
        plugin_rows,
        plugin_descriptors,
        compatibility_report,
        release_evidence,
    )
    if not _finite_tree(inputs):
        raise PromotionPackageBlocked(("finite_values",))

    failed: set[str] = set()
    if not _identifier(run_id):
        failed.add("identifiers_valid")

    status_run_id = _string(run_status.get("run_id"))
    evidence_run_id = _string(autopilot_evidence.get("run_id"))
    spec_id = _string(autopilot_evidence.get("spec_id"))
    if not all(_identifier(value) for value in (status_run_id, evidence_run_id, spec_id)):
        failed.add("identifiers_valid")
    if not (run_id == status_run_id == evidence_run_id):
        failed.add("run_binding_matches")
    if run_status.get("status") != "completed" or autopilot_evidence.get("status") != "completed":
        failed.add("run_completed")
    if autopilot_evidence.get("schema_version") != "across-loop-evidence/1.0":
        failed.add("autopilot_evidence_valid")

    candidate = _mapping(autopilot_evidence.get("candidate"))
    producer_package = _mapping(candidate.get("promotion_package"))
    candidate_id = _string(candidate.get("candidate_id"))
    producer_candidate_id = _string(producer_package.get("candidate_id"))
    if not _identifier(candidate_id) or not _identifier(producer_candidate_id):
        failed.add("identifiers_valid")
    if not candidate_id or candidate_id != producer_candidate_id:
        failed.add("candidate_binding_matches")

    changed_files = _changed_files(candidate.get("changed_files"))
    if changed_files is None:
        failed.add("changed_paths_safe")
        changed_files = []

    expected_task_ids = _expected_task_ids(autopilot_evidence, failed)
    task_receipts = _task_receipts(
        task_evidence,
        expected_task_ids=expected_task_ids,
        failed=failed,
    )

    graph_component = _graph_component(
        evidence_graph,
        run_id=run_id,
        spec_id=spec_id,
        failed=failed,
    )

    plugin_identities, compatibility_component = _plugin_components(
        plugin_rows,
        plugin_descriptors=plugin_descriptors,
        compatibility_report=compatibility_report,
        failed=failed,
    )

    release_component = _release_component(release_evidence, failed=failed)
    review = build_promotion_review_packet(autopilot_evidence)
    if (
        review.get("status") != "ready_for_human_review"
        or review.get("promotion_ready") is not True
    ):
        failed.add("candidate_review_ready")

    if failed:
        raise PromotionPackageBlocked(failed)

    public_review = _public_review(review, changed_files=changed_files)
    autopilot_digest = _digest(autopilot_evidence)
    graph_digest = _digest(evidence_graph)
    if autopilot_digest is None or graph_digest is None:
        raise PromotionPackageBlocked(("finite_values",))
    graph_component["digest"] = graph_digest

    source_tasks = [
        {
            "task_id": item["task_id"],
            "source": item["source"],
            "schema_version": item["schema_version"],
            "digest_algorithm": item["digest_algorithm"],
            "digest": item["digest"],
        }
        for item in task_receipts
    ]
    return {
        "schema_version": PROMOTION_PACKAGE_SCHEMA,
        "status": "ready_for_human_approval",
        "identities": {
            "run_id": run_id,
            "spec_id": spec_id,
            "candidate_id": candidate_id,
            "task_ids": expected_task_ids,
            "plugins": plugin_identities,
        },
        "source_digests": {
            "autopilot_evidence_sha256": autopilot_digest,
            "tasks": source_tasks,
        },
        "components": {
            "candidate_review": public_review,
            "task_receipts": task_receipts,
            "evidence_graph": graph_component,
            "compatibility": compatibility_component,
            "lifecycle_provenance": {"plugins": plugin_identities},
            "release_readiness": release_component,
        },
        "checks": list(_PASSED_CHECK_IDS),
        "policy": {
            "human_approval_required": True,
            "approval_scope": "release_promotion",
            "merge_blocked": True,
            "tag_blocked": True,
            "release_blocked": True,
            "signing_blocked": True,
        },
        "audit": {
            "receipt_checked_before_redaction": True,
            "secrets_redacted": True,
            "raw_payload_exposed": False,
        },
    }


def _expected_task_ids(evidence: Mapping[str, Any], failed: set[str]) -> list[str]:
    orchestrator = _mapping(evidence.get("orchestrator"))
    raw_tasks = orchestrator.get("tasks")
    if not isinstance(raw_tasks, list) or not 1 <= len(raw_tasks) <= _MAX_TASKS:
        failed.add("task_set_complete")
        return []
    task_ids: list[str] = []
    for item in raw_tasks:
        task_id = _string(_mapping(item).get("task_id"))
        if not _identifier(task_id):
            failed.add("identifiers_valid")
            continue
        task_ids.append(task_id)
    result = sorted(set(task_ids))
    if not result or len(result) > _MAX_TASKS:
        failed.add("task_set_complete")
    return result


def _task_receipts(
    values: Sequence[Mapping[str, Any]],
    *,
    expected_task_ids: Sequence[str],
    failed: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= _MAX_TASKS:
        failed.add("task_set_complete")
        return []
    items: list[tuple[str, Mapping[str, Any]]] = []
    observed_ids: list[str] = []
    for value in values:
        if not isinstance(value, Mapping):
            failed.add("task_set_complete")
            continue
        task_id = _string(value.get("task_id"))
        if not _identifier(task_id):
            failed.add("identifiers_valid")
            continue
        observed_ids.append(task_id)
        items.append((task_id, value))
    if sorted(observed_ids) != list(expected_task_ids) or len(set(observed_ids)) != len(observed_ids):
        failed.add("task_set_complete")

    public: list[dict[str, Any]] = []
    for task_id, item in sorted(items, key=lambda pair: pair[0]):
        source = _string(item.get("source"))
        if source not in {"orchestrator_evidence", "worker_projection"}:
            failed.add("task_receipts_verified")
            continue
        bound_task_id = _string(item.get("bound_task_id"))
        raw_receipt = item.get("raw_receipt")
        verified = verify_evidence_receipt(source=source, raw_receipt=raw_receipt)
        if verified.get("integrity_state") != "hash_valid" or not _digest_value(verified.get("digest")):
            failed.add("task_receipts_verified")
            continue
        raw_task_id = _string(raw_receipt.get("task_id")) if isinstance(raw_receipt, Mapping) else ""
        if bound_task_id != task_id or (
            source == "orchestrator_evidence" and raw_task_id != task_id
        ):
            failed.add("task_receipt_bindings_match")
        if verified.get("verdict") != "ready":
            failed.add("task_receipts_ready")
        public.append(
            {
                "task_id": task_id,
                "source": source,
                "schema_version": verified.get("schema_version"),
                "integrity_state": "hash_valid",
                "digest_algorithm": "sha256",
                "digest": verified.get("digest"),
                "verdict": verified.get("verdict"),
            }
        )
    return public


def _graph_component(
    graph: Mapping[str, Any],
    *,
    run_id: str,
    spec_id: str,
    failed: set[str],
) -> dict[str, Any]:
    valid = isinstance(graph, Mapping) and graph.get("schema_version") == EVIDENCE_GRAPH_SCHEMA
    nodes = graph.get("nodes") if isinstance(graph, Mapping) else None
    edges = graph.get("edges") if isinstance(graph, Mapping) else None
    summary = _mapping(graph.get("summary")) if isinstance(graph, Mapping) else {}
    valid = valid and isinstance(nodes, list) and isinstance(edges, list)
    valid = valid and len(nodes or []) <= _MAX_GRAPH_NODES and len(edges or []) <= _MAX_GRAPH_EDGES
    valid = valid and graph.get("run_id") == run_id and graph.get("spec_id") == spec_id
    valid = valid and type(summary.get("node_count")) is int and summary.get("node_count") == len(nodes or [])
    valid = valid and type(summary.get("edge_count")) is int and summary.get("edge_count") == len(edges or [])

    node_ids: list[str] = []
    if isinstance(nodes, list):
        for node in nodes:
            node_id = _string(_mapping(node).get("id"))
            if not _identifier(node_id):
                valid = False
            node_ids.append(node_id)
    if len(set(node_ids)) != len(node_ids):
        valid = False
    if isinstance(edges, list):
        for edge in edges:
            row = _mapping(edge)
            if (
                _string(row.get("from")) not in node_ids
                or _string(row.get("to")) not in node_ids
                or not _identifier(_string(row.get("relation")))
            ):
                valid = False
    if not valid:
        failed.add("evidence_graph_valid")
    return {
        "schema_version": EVIDENCE_GRAPH_SCHEMA,
        "run_id": run_id,
        "spec_id": spec_id,
        "node_count": len(nodes) if isinstance(nodes, list) else 0,
        "edge_count": len(edges) if isinstance(edges, list) else 0,
    }


def _plugin_components(
    rows: Sequence[Mapping[str, Any]],
    *,
    plugin_descriptors: Mapping[str, Mapping[str, Any]],
    compatibility_report: Mapping[str, Any],
    failed: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows_list = list(rows) if isinstance(rows, (list, tuple)) else []
    row_ids = [_string(row.get("plugin_id")) for row in rows_list if isinstance(row, Mapping)]
    descriptor_ids = set(plugin_descriptors) if isinstance(plugin_descriptors, Mapping) else set()
    raw_compatibility_plugins = compatibility_report.get("plugins")
    compatibility_plugins = (
        raw_compatibility_plugins if isinstance(raw_compatibility_plugins, Mapping) else {}
    )
    exact_sets = (
        len(rows_list) == len(REQUIRED_PLUGIN_IDS)
        and len(set(row_ids)) == len(REQUIRED_PLUGIN_IDS)
        and set(row_ids) == REQUIRED_PLUGIN_IDS
        and descriptor_ids == REQUIRED_PLUGIN_IDS
        and set(compatibility_plugins) == REQUIRED_PLUGIN_IDS
    )
    if not exact_sets:
        failed.add("plugin_set_complete")
        return [], _empty_compatibility_component()

    if (
        compatibility_report.get("schema_version") != COMPATIBILITY_SCHEMA
        or compatibility_report.get("status") != "compatible"
        or compatibility_report.get("compatible_plugin_count") != 3
        or compatibility_report.get("incompatible_plugin_count") != 0
    ):
        failed.add("plugin_compatibility_ready")

    rows_by_id = {str(row["plugin_id"]): row for row in rows_list}
    identities: list[dict[str, Any]] = []
    public_plugins: list[dict[str, Any]] = []
    for plugin_id in sorted(REQUIRED_PLUGIN_IDS):
        row = rows_by_id[plugin_id]
        descriptor = plugin_descriptors[plugin_id]
        compatibility = _mapping(compatibility_plugins[plugin_id])
        version = _string(row.get("version"))
        descriptor_version = _string(descriptor.get("version"))
        producer_commit = _string(descriptor.get("commit")).lower()
        payload_sha = _string(descriptor.get("sha256")).lower()
        provenance = plugin_provenance_digest(row, descriptor)
        if not _identifier(plugin_id) or not version:
            failed.add("identifiers_valid")
        if not (
            row.get("status") == "installed"
            and row.get("installed") is True
            and row.get("available") is True
            and row.get("integrity_ok") is True
        ):
            failed.add("plugin_lifecycle_ready")
        if compatibility.get("status") != "compatible":
            failed.add("plugin_compatibility_ready")
        if not (
            version
            and descriptor_version == version
            and compatibility.get("version") == version
        ):
            failed.add("plugin_versions_match")
        if (
            _HEX_40.fullmatch(producer_commit) is None
            or _HEX_64.fullmatch(payload_sha) is None
            or compatibility.get("provenance_digest") != provenance
        ):
            failed.add("plugin_provenance_matches")
        identity = {
            "plugin_id": plugin_id,
            "version": version,
            "producer_commit": producer_commit,
            "payload_sha256": payload_sha,
            "provenance_digest": provenance,
        }
        identities.append(identity)
        public_plugins.append(
            {
                "plugin_id": plugin_id,
                "status": compatibility.get("status"),
                "version": _string(compatibility.get("version")),
                "provenance_digest": _string(compatibility.get("provenance_digest")),
                "tool_count": _nonnegative_int(compatibility.get("tool_count")),
                "tool_set_digest": _public_digest(compatibility.get("tool_set_digest")),
            }
        )
    return identities, {
        "schema_version": COMPATIBILITY_SCHEMA,
        "status": "compatible",
        "compatible_plugin_count": 3,
        "incompatible_plugin_count": 0,
        "portable_tool_count": _nonnegative_int(compatibility_report.get("portable_tool_count")),
        "plugins": public_plugins,
    }


def _release_component(
    release: Mapping[str, Any],
    *,
    failed: set[str],
) -> dict[str, Any]:
    evaluation = _mapping(release.get("release_evaluation"))
    gates = _mapping(release.get("pre_release_gate_summary"))
    if release.get("status") != "ready" or evaluation.get("release_readiness") != "ready":
        failed.add("release_ready")
    return {
        "schema_version": _string(release.get("schema_version")),
        "status": _string(release.get("status")),
        "release_readiness": _string(evaluation.get("release_readiness")),
        "evaluated_task_count": _nonnegative_int(evaluation.get("evaluated_task_count")),
        "release_evidence_count": _nonnegative_int(evaluation.get("release_evidence_count")),
        "passed_evidence_count": _nonnegative_int(evaluation.get("passed_evidence_count")),
        "required_missing": _nonnegative_int(gates.get("required_missing")),
        "required_manual": _nonnegative_int(gates.get("required_manual")),
        "required_unverified": _nonnegative_int(gates.get("required_unverified")),
        "passed_gate_count": _nonnegative_int(gates.get("passed")),
    }


def _public_review(review: Mapping[str, Any], *, changed_files: Sequence[str]) -> dict[str, Any]:
    attestation = _mapping(review.get("promotion_attestation"))
    scores = _mapping(review.get("reviewer_scores"))
    checklist = []
    for value in review.get("checklist") if isinstance(review.get("checklist"), list) else []:
        item = _mapping(value)
        identifier = _string(item.get("id"))
        status = _string(item.get("status"))
        if _identifier(identifier) and status in {"passed", "failed", "not_evaluable"}:
            checklist.append({"id": identifier, "status": status})
    return {
        "schema_version": _string(review.get("schema_version")),
        "status": _string(review.get("status")),
        "promotion_ready": review.get("promotion_ready") is True,
        "candidate_id": _string(review.get("candidate_id")),
        "changed_files": list(changed_files),
        "checklist": sorted(checklist, key=lambda item: item["id"]),
        "reviewer_scores": {
            "product_value_score": _finite_number(scores.get("product_value_score")),
            "maintainability_score": _finite_number(scores.get("maintainability_score")),
            "risk_score": _finite_number(scores.get("risk_score")),
            "merge_recommendation": _string(scores.get("merge_recommendation")),
        },
        "promotion_attestation": {
            "schema_version": _string(attestation.get("schema_version")),
            "digest_status": _string(attestation.get("digest_status")),
            "algorithm": _string(attestation.get("algorithm")),
            "digest": _public_digest(attestation.get("digest")),
            "human_approval_required": attestation.get("human_approval_required") is True,
            "merge_release_signing_blocked": attestation.get("merge_release_signing_blocked") is True,
        },
    }


def _changed_files(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not 1 <= len(value) <= _MAX_CHANGED_FILES:
        return None
    result: list[str] = []
    for item in value:
        if type(item) is not str:
            return None
        path = item.replace("\\", "/").strip()
        segments = path.split("/")
        if (
            not path
            or len(path) > 512
            or path.startswith(("/", "~"))
            or _WINDOWS_ABSOLUTE.match(item) is not None
            or "\x00" in path
            or any(segment in {"", ".", ".."} for segment in segments)
        ):
            return None
        result.append(path)
    return sorted(set(result))


def _finite_tree(value: Any, *, _depth: int = 0, _seen: set[int] | None = None) -> bool:
    if _depth > _MAX_TREE_DEPTH:
        return False
    if isinstance(value, float):
        return math.isfinite(value)
    if value is None or isinstance(value, (str, int, bool)):
        return True
    if _seen is None:
        _seen = set()
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in _seen:
            return False
        _seen.add(identity)
        valid = all(
            _finite_tree(key, _depth=_depth + 1, _seen=_seen)
            and _finite_tree(item, _depth=_depth + 1, _seen=_seen)
            for key, item in value.items()
        )
        _seen.remove(identity)
        return valid
    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in _seen:
            return False
        _seen.add(identity)
        valid = all(_finite_tree(item, _depth=_depth + 1, _seen=_seen) for item in value)
        _seen.remove(identity)
        return valid
    return False


def _digest(value: Any) -> str | None:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        return None
    return sha256(encoded).hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string(value: Any) -> str:
    return value.strip() if type(value) is str else ""


def _identifier(value: Any) -> bool:
    return type(value) is str and _SAFE_ID.fullmatch(value) is not None


def _digest_value(value: Any) -> bool:
    return type(value) is str and _HEX_64.fullmatch(value) is not None


def _public_digest(value: Any) -> str | None:
    return value if _digest_value(value) else None


def _nonnegative_int(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _finite_number(value: Any) -> float | int | None:
    if type(value) is int:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    return None


def _empty_compatibility_component() -> dict[str, Any]:
    return {
        "schema_version": COMPATIBILITY_SCHEMA,
        "status": "incompatible",
        "compatible_plugin_count": 0,
        "incompatible_plugin_count": len(REQUIRED_PLUGIN_IDS),
        "portable_tool_count": 0,
        "plugins": [],
    }
