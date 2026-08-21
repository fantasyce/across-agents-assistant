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
WORKER_TASK_RECEIPT_BINDING_SCHEMA = "across-worker-task-receipt-binding/1.0"
REQUIRED_PLUGIN_IDS = frozenset(
    {
        "across-context",
        "across-orchestrator",
        "across-autopilot",
    }
)

_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_SAFE_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z._+-]{0,63}")
_SAFE_RELATIVE_PATH = re.compile(r"[A-Za-z0-9._@+-]+(?:/[A-Za-z0-9._@+-]+)*")
_HEX_40 = re.compile(r"[0-9a-f]{40}")
_HEX_64 = re.compile(r"[0-9a-f]{64}")
_WINDOWS_ABSOLUTE = re.compile(r"[A-Za-z]:[/\\]")
_MAX_TASKS = 256
_MAX_CHANGED_FILES = 256
_MAX_GRAPH_NODES = 10_000
_MAX_GRAPH_EDGES = 20_000
_MAX_TREE_DEPTH = 64

PROMOTION_PACKAGE_CHECK_IDS = (
    "autopilot_evidence_valid",
    "candidate_binding_matches",
    "candidate_review_ready",
    "changed_paths_safe",
    "evidence_graph_valid",
    "evidence_graph_task_set_complete",
    "finite_values",
    "identifiers_valid",
    "input_shapes_valid",
    "plugin_compatibility_ready",
    "plugin_lifecycle_ready",
    "plugin_provenance_matches",
    "plugin_set_complete",
    "plugin_versions_match",
    "release_ready",
    "release_task_set_matches",
    "run_binding_matches",
    "run_completed",
    "task_receipt_bindings_match",
    "task_receipts_ready",
    "task_receipts_verified",
    "task_set_complete",
    "worker_receipt_binding_valid",
    "worker_receipt_replay_absent",
)
_PASSED_CHECK_IDS = PROMOTION_PACKAGE_CHECK_IDS


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


def build_worker_task_receipt_binding(
    *,
    task_link: Mapping[str, Any],
    raw_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind an authoritative AAA Worker task link to one hash-valid receipt."""

    if not isinstance(task_link, Mapping) or not isinstance(raw_receipt, Mapping):
        raise PromotionPackageBlocked(("worker_receipt_binding_valid",))
    receipt_state = verify_evidence_receipt(
        source="worker_projection",
        raw_receipt=raw_receipt,
    )
    node = _mapping(raw_receipt.get("node"))
    task_id = _string(task_link.get("task_id"))
    job_id = _string(task_link.get("job_id"))
    run_id = _string(task_link.get("run_id"))
    node_id = _string(task_link.get("node_id"))
    manifest_hash = _string(task_link.get("manifest_hash"))
    terminal_state = _string(task_link.get("status"))
    receipt_hash = _string(raw_receipt.get("receipt_hash"))
    if not (
        task_link.get("schema_version") == "across-aaa-worker-task-link/1.0"
        and receipt_state.get("integrity_state") == "hash_valid"
        and receipt_state.get("verdict") == "ready"
        and _identifier(task_id)
        and _identifier(job_id)
        and _identifier(run_id)
        and _identifier(node_id)
        and _digest_value(manifest_hash)
        and _digest_value(receipt_hash)
        and job_id == raw_receipt.get("job_id")
        and run_id == raw_receipt.get("run_id")
        and node_id == node.get("node_id")
        and manifest_hash == raw_receipt.get("manifest_hash")
        and terminal_state == raw_receipt.get("terminal_state") == "completed"
    ):
        raise PromotionPackageBlocked(("worker_receipt_binding_valid",))
    binding = {
        "schema_version": WORKER_TASK_RECEIPT_BINDING_SCHEMA,
        "link_schema_version": "across-aaa-worker-task-link/1.0",
        "task_id": task_id,
        "job_id": job_id,
        "run_id": run_id,
        "node_id": node_id,
        "manifest_hash": manifest_hash,
        "terminal_state": terminal_state,
        "receipt_hash": receipt_hash,
    }
    binding["binding_sha256"] = _digest(binding)
    return binding


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
    if not (
        isinstance(run_status, Mapping)
        and isinstance(autopilot_evidence, Mapping)
        and isinstance(task_evidence, (list, tuple))
        and isinstance(evidence_graph, Mapping)
        and isinstance(plugin_rows, (list, tuple))
        and isinstance(plugin_descriptors, Mapping)
        and isinstance(compatibility_report, Mapping)
        and isinstance(release_evidence, Mapping)
    ):
        raise PromotionPackageBlocked(("input_shapes_valid",))

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
        expected_task_ids=expected_task_ids,
        failed=failed,
    )

    plugin_identities, compatibility_component = _plugin_components(
        plugin_rows,
        plugin_descriptors=plugin_descriptors,
        compatibility_report=compatibility_report,
        failed=failed,
    )

    release_component = _release_component(
        release_evidence,
        expected_task_ids=expected_task_ids,
        failed=failed,
    )
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
    worker_receipt_tasks: dict[str, str] = {}
    worker_job_tasks: dict[tuple[str, str], str] = {}
    for task_id, item in sorted(items, key=lambda pair: pair[0]):
        source = _string(item.get("source"))
        if source not in {"orchestrator_evidence", "worker_projection"}:
            failed.add("task_receipts_verified")
            continue
        raw_receipt = item.get("raw_receipt")
        verified = verify_evidence_receipt(source=source, raw_receipt=raw_receipt)
        if verified.get("integrity_state") != "hash_valid" or not _digest_value(verified.get("digest")):
            failed.add("task_receipts_verified")
            continue
        if source == "orchestrator_evidence":
            raw_task_id = _string(raw_receipt.get("task_id")) if isinstance(raw_receipt, Mapping) else ""
            if raw_task_id != task_id:
                failed.add("task_receipt_bindings_match")
        else:
            if not _valid_worker_binding(
                task_id=task_id,
                raw_receipt=raw_receipt,
                raw_binding=item.get("worker_binding"),
            ):
                failed.add("worker_receipt_binding_valid")
            receipt_digest = _string(verified.get("digest"))
            raw_worker_receipt = _mapping(raw_receipt)
            job_key = (
                _string(raw_worker_receipt.get("run_id")),
                _string(raw_worker_receipt.get("job_id")),
            )
            if (
                receipt_digest in worker_receipt_tasks
                and worker_receipt_tasks[receipt_digest] != task_id
            ) or (
                job_key in worker_job_tasks
                and worker_job_tasks[job_key] != task_id
            ):
                failed.add("worker_receipt_replay_absent")
            worker_receipt_tasks[receipt_digest] = task_id
            worker_job_tasks[job_key] = task_id
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


def _valid_worker_binding(
    *,
    task_id: str,
    raw_receipt: Any,
    raw_binding: Any,
) -> bool:
    if not isinstance(raw_receipt, Mapping) or not isinstance(raw_binding, Mapping):
        return False
    required_fields = {
        "schema_version",
        "link_schema_version",
        "task_id",
        "job_id",
        "run_id",
        "node_id",
        "manifest_hash",
        "terminal_state",
        "receipt_hash",
        "binding_sha256",
    }
    if set(raw_binding) != required_fields:
        return False
    binding = dict(raw_binding)
    expected = binding.pop("binding_sha256", None)
    if not _digest_value(expected) or _digest(binding) != expected:
        return False
    node = _mapping(raw_receipt.get("node"))
    receipt_hash = _string(raw_receipt.get("receipt_hash"))
    if not (
        binding.get("schema_version") == WORKER_TASK_RECEIPT_BINDING_SCHEMA
        and binding.get("link_schema_version") == "across-aaa-worker-task-link/1.0"
        and binding.get("task_id") == task_id
        and _identifier(_string(binding.get("job_id")))
        and _identifier(_string(binding.get("run_id")))
        and _identifier(_string(binding.get("node_id")))
        and binding.get("job_id") == raw_receipt.get("job_id")
        and binding.get("run_id") == raw_receipt.get("run_id")
        and binding.get("node_id") == node.get("node_id")
        and binding.get("manifest_hash") == raw_receipt.get("manifest_hash")
        and binding.get("terminal_state") == raw_receipt.get("terminal_state") == "completed"
        and binding.get("receipt_hash") == receipt_hash
        and _digest_value(binding.get("manifest_hash"))
        and _digest_value(receipt_hash)
    ):
        return False
    return True


def _graph_component(
    graph: Mapping[str, Any],
    *,
    run_id: str,
    spec_id: str,
    expected_task_ids: Sequence[str],
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

    expected_task_set = set(expected_task_ids)
    task_nodes: dict[str, str] = {}
    if isinstance(nodes, list):
        for node in nodes:
            row = _mapping(node)
            if row.get("type") != "task":
                continue
            task_id = _string(row.get("task_id"))
            node_id = _string(row.get("id"))
            if not _identifier(task_id) or node_id != f"task:{task_id}" or task_id in task_nodes:
                task_nodes["__invalid__"] = node_id
                continue
            task_nodes[task_id] = node_id
    run_node_id = f"run:{run_id}"
    run_node_present = any(
        _mapping(node).get("id") == run_node_id and _mapping(node).get("type") == "run"
        for node in nodes or []
    )
    task_edges = [
        (_string(_mapping(edge).get("from")), _string(_mapping(edge).get("to")))
        for edge in edges or []
        if _mapping(edge).get("relation") == "contains"
        and _string(_mapping(edge).get("from")) == run_node_id
    ]
    expected_task_edges = {(run_node_id, f"task:{task_id}") for task_id in expected_task_set}
    if (
        not run_node_present
        or set(task_nodes) != expected_task_set
        or len(task_edges) != len(expected_task_edges)
        or set(task_edges) != expected_task_edges
    ):
        failed.add("evidence_graph_task_set_complete")
    return {
        "schema_version": EVIDENCE_GRAPH_SCHEMA,
        "run_id": run_id,
        "spec_id": spec_id,
        "node_count": len(nodes) if isinstance(nodes, list) else 0,
        "edge_count": len(edges) if isinstance(edges, list) else 0,
        "task_node_count": len(expected_task_ids),
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

    top_level_invalid = (
        compatibility_report.get("schema_version") != COMPATIBILITY_SCHEMA
        or compatibility_report.get("status") != "compatible"
        or type(compatibility_report.get("compatible_plugin_count")) is not int
        or compatibility_report.get("compatible_plugin_count") != 3
        or type(compatibility_report.get("incompatible_plugin_count")) is not int
        or compatibility_report.get("incompatible_plugin_count") != 0
        or _nonnegative_int(compatibility_report.get("portable_tool_count")) is None
    )
    if top_level_invalid:
        failed.add("plugin_compatibility_ready")

    rows_by_id = {str(row["plugin_id"]): row for row in rows_list}
    identities: list[dict[str, Any]] = []
    public_plugins: list[dict[str, Any]] = []
    aggregate_tool_count = 0
    for plugin_id in sorted(REQUIRED_PLUGIN_IDS):
        row = rows_by_id[plugin_id]
        raw_descriptor = plugin_descriptors[plugin_id]
        compatibility = _mapping(compatibility_plugins[plugin_id])
        tool_count = _nonnegative_int(compatibility.get("tool_count"))
        tool_set_digest = _string(compatibility.get("tool_set_digest"))
        profiles = compatibility.get("profiles")
        findings = compatibility.get("findings")
        profiles_valid = (
            isinstance(profiles, Mapping)
            and set(profiles) == {"mcp_core", "claude_desktop_portable"}
            and all(
                isinstance(profiles.get(profile_id), Mapping)
                and set(profiles[profile_id]) == {"status", "finding_count"}
                and profiles[profile_id].get("status") == "compatible"
                and type(profiles[profile_id].get("finding_count")) is int
                and profiles[profile_id].get("finding_count") == 0
                for profile_id in ("mcp_core", "claude_desktop_portable")
            )
        )
        compatibility_shape_valid = (
            tool_count is not None
            and _digest_value(tool_set_digest)
            and profiles_valid
            and isinstance(findings, list)
            and not findings
        )
        if not compatibility_shape_valid:
            failed.add("plugin_compatibility_ready")
        if tool_count is not None:
            aggregate_tool_count += tool_count
        if not isinstance(raw_descriptor, Mapping):
            failed.add("plugin_provenance_matches")
            continue
        descriptor = raw_descriptor
        version = _string(row.get("version"))
        descriptor_version = _string(descriptor.get("version"))
        producer_commit = _string(descriptor.get("commit")).lower()
        source_sha = _string(descriptor.get("source_sha256") or descriptor.get("sha256")).lower()
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
            _SAFE_VERSION.fullmatch(version) is not None
            and _SAFE_VERSION.fullmatch(descriptor_version) is not None
            and descriptor_version == version
            and compatibility.get("version") == version
        ):
            failed.add("plugin_versions_match")
        if (
            _HEX_40.fullmatch(producer_commit) is None
            or _HEX_64.fullmatch(source_sha) is None
            or _HEX_64.fullmatch(payload_sha) is None
            or compatibility.get("provenance_digest") != provenance
        ):
            failed.add("plugin_provenance_matches")
        identity = {
            "plugin_id": plugin_id,
            "version": version,
            "producer_commit": producer_commit,
            "source_sha256": source_sha,
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
                "tool_count": tool_count,
                "tool_set_digest": _public_digest(tool_set_digest),
                "profiles": {
                    profile_id: {
                        "status": profiles[profile_id].get("status"),
                        "finding_count": profiles[profile_id].get("finding_count"),
                    }
                    for profile_id in ("mcp_core", "claude_desktop_portable")
                } if profiles_valid else {},
            }
        )
    portable_tool_count = _nonnegative_int(compatibility_report.get("portable_tool_count"))
    if portable_tool_count != aggregate_tool_count:
        failed.add("plugin_compatibility_ready")
    return identities, {
        "schema_version": COMPATIBILITY_SCHEMA,
        "status": "compatible",
        "compatible_plugin_count": 3,
        "incompatible_plugin_count": 0,
        "portable_tool_count": portable_tool_count,
        "plugins": public_plugins,
    }


def _release_component(
    release: Mapping[str, Any],
    *,
    expected_task_ids: Sequence[str],
    failed: set[str],
) -> dict[str, Any]:
    evaluation = _mapping(release.get("release_evaluation"))
    task_scope = _mapping(release.get("task_scope"))
    gates = _mapping(release.get("pre_release_gate_summary"))
    evaluated_task_count = _nonnegative_int(evaluation.get("evaluated_task_count"))
    terminal_task_count = _nonnegative_int(evaluation.get("terminal_task_count"))
    passed_task_count = _nonnegative_int(evaluation.get("passed_task_count"))
    blocked_task_count = _nonnegative_int(evaluation.get("blocked_task_count"))
    manual_task_count = _nonnegative_int(evaluation.get("manual_task_count"))
    skipped_task_count = _nonnegative_int(evaluation.get("skipped_task_count"))
    release_evidence_count = _nonnegative_int(evaluation.get("release_evidence_count"))
    passed_evidence_count = _nonnegative_int(evaluation.get("passed_evidence_count"))
    scoped_task_ids = task_scope.get("task_ids")
    evaluated_task_ids = evaluation.get("task_ids")
    exact_task_scope = (
        task_scope.get("schema_version") == "across-release-task-scope/1.0"
        and isinstance(scoped_task_ids, list)
        and scoped_task_ids == list(expected_task_ids)
        and len(scoped_task_ids) == len(set(scoped_task_ids))
        and isinstance(evaluated_task_ids, list)
        and evaluated_task_ids == list(expected_task_ids)
        and len(evaluated_task_ids) == len(set(evaluated_task_ids))
        and evaluated_task_count == len(expected_task_ids)
        and terminal_task_count == len(expected_task_ids)
        and passed_task_count == len(expected_task_ids)
    )
    task_set_was_valid = not {"identifiers_valid", "task_set_complete"}.intersection(failed)
    if task_set_was_valid and not exact_task_scope:
        failed.add("release_task_set_matches")
    gate_total = _nonnegative_int(gates.get("total"))
    gate_passed = _nonnegative_int(gates.get("passed"))
    zero_gate_fields = (
        "configured",
        "manual_required",
        "missing",
        "failed",
        "required_missing",
        "required_manual",
        "required_failed",
        "required_unverified",
    )
    ready = (
        release.get("schema_version") == "1.0"
        and release.get("status") == "ready"
        and evaluation.get("release_readiness") == "ready"
        and blocked_task_count == 0
        and manual_task_count == 0
        and skipped_task_count == 0
        and release_evidence_count is not None
        and release_evidence_count >= evaluated_task_count
        and passed_evidence_count == release_evidence_count
        and gate_total is not None
        and gate_total > 0
        and gate_passed == gate_total
        and all(_nonnegative_int(gates.get(field)) == 0 for field in zero_gate_fields)
    )
    if not ready:
        failed.add("release_ready")
    return {
        "schema_version": "1.0",
        "status": "ready",
        "release_readiness": "ready",
        "task_ids": list(expected_task_ids) if exact_task_scope else [],
        "evaluated_task_count": evaluated_task_count,
        "terminal_task_count": terminal_task_count,
        "passed_task_count": passed_task_count,
        "blocked_task_count": blocked_task_count,
        "manual_task_count": manual_task_count,
        "skipped_task_count": skipped_task_count,
        "release_evidence_count": release_evidence_count,
        "passed_evidence_count": passed_evidence_count,
        "gate_total": gate_total,
        "passed_gate_count": gate_passed,
        "required_missing": _nonnegative_int(gates.get("required_missing")),
        "required_manual": _nonnegative_int(gates.get("required_manual")),
        "required_failed": _nonnegative_int(gates.get("required_failed")),
        "required_unverified": _nonnegative_int(gates.get("required_unverified")),
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
        "schema_version": "across-autopilot-promotion-review/1.0",
        "status": "ready_for_human_review",
        "promotion_ready": review.get("promotion_ready") is True,
        "candidate_id": _string(review.get("candidate_id")),
        "changed_files": list(changed_files),
        "checklist": sorted(checklist, key=lambda item: item["id"]),
        "reviewer_scores": {
            "product_value_score": _bounded_score(scores.get("product_value_score")),
            "maintainability_score": _bounded_score(scores.get("maintainability_score")),
            "risk_score": _bounded_score(scores.get("risk_score")),
        },
        "promotion_attestation": {
            "schema_version": "across-autopilot-promotion-attestation/1.0",
            "digest_status": "passed",
            "algorithm": "sha256",
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
        path = item
        segments = path.split("/")
        if (
            not path
            or len(path) > 512
            or "\\" in path
            or _SAFE_RELATIVE_PATH.fullmatch(path) is None
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
    return value if type(value) is str else ""


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


def _bounded_score(value: Any) -> float | int | None:
    number = _finite_number(value)
    if number is None or not 0 <= number <= 100:
        return None
    return number


def _empty_compatibility_component() -> dict[str, Any]:
    return {
        "schema_version": COMPATIBILITY_SCHEMA,
        "status": "incompatible",
        "compatible_plugin_count": 0,
        "incompatible_plugin_count": len(REQUIRED_PLUGIN_IDS),
        "portable_tool_count": 0,
        "plugins": [],
    }
