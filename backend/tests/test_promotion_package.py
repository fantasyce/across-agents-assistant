"""Focused contract tests for the unified promotion package composer."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import math

import pytest

from across_agents_assistant.agent_interop_e2e import plugin_provenance_digest
from across_agents_assistant.promotion_package import (
    PromotionPackageBlocked,
    build_promotion_package,
    build_worker_task_receipt_binding,
    package_sha256,
)


PLUGIN_IDS = (
    "across-autopilot",
    "across-context",
    "across-orchestrator",
)


def _signed_receipt(source: str, task_id: str, **extra: object) -> dict[str, object]:
    if source == "worker_projection":
        receipt: dict[str, object] = {
            "schema_version": "across-worker-evidence/1.0",
            "run_id": "worker-run-1",
            "job_id": f"job-{task_id}",
            "node": {"node_id": "node-worker-1", "platform": "macos/arm64"},
            "manifest_hash": "e" * 64,
            "terminal_state": "completed",
            **extra,
        }
        digest_field = "receipt_hash"
        ensure_ascii = False
    else:
        receipt = {
            "schema_version": "across-evidence-receipt/1.0",
            "task_id": task_id,
            "verdict": "ready",
            **extra,
        }
        digest_field = "evidence_sha256"
        ensure_ascii = True
    receipt[digest_field] = sha256(
        json.dumps(
            receipt,
            ensure_ascii=ensure_ascii,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return receipt


def _worker_binding(task_id: str, receipt: dict[str, object]) -> dict[str, object]:
    node = receipt.get("node") if isinstance(receipt.get("node"), dict) else {}
    link = {
        "schema_version": "across-aaa-worker-task-link/1.0",
        "task_id": task_id,
        "job_id": receipt.get("job_id"),
        "run_id": receipt.get("run_id"),
        "node_id": node.get("node_id"),
        "manifest_hash": receipt.get("manifest_hash"),
        "status": receipt.get("terminal_state"),
    }
    return build_worker_task_receipt_binding(task_link=link, raw_receipt=receipt)


def _candidate() -> dict[str, object]:
    return {
        "candidate_id": "candidate-batch-5",
        "promotion_ready": True,
        "changed_files": [
            "backend/src/across_agents_assistant/promotion_package.py",
            "backend/tests/test_promotion_package.py",
        ],
        "validation": {"status": "passed", "commands": [{"status": "passed"}]},
        "semantic_alignment_status": "passed",
        "self_hosting_probe": {"required": True, "status": "passed"},
        "quality_findings": [],
        "independent_reviewer": {
            "product_value_score": 95,
            "maintainability_score": 94,
            "risk_score": 6,
            "merge_recommendation": "open_review_pr",
            "model_separation": {"required": True, "status": "passed"},
        },
        "promotion_package": {
            "candidate_id": "candidate-batch-5",
            "source_a_unchanged": True,
            "source_ref_pins": {
                "schema_version": "across-autopilot-source-ref-pins/1.0",
                "status": "passed",
                "repos": [
                    {"id": "across-agents-assistant", "source_head_pre": "a" * 40},
                    {"id": "across-context", "source_head_pre": "b" * 40},
                    {"id": "across-orchestrator", "source_head_pre": "c" * 40},
                    {"id": "across-autopilot", "source_head_pre": "d" * 40},
                ],
                "missing_required_repos": [],
                "missing_pins": [],
                "changed_sources": [],
            },
            "known_risks": [],
            "private_sentinel": "private-candidate-sentinel",
        },
    }


def _plugin_inputs() -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
    rows: list[dict[str, object]] = []
    descriptors: dict[str, dict[str, object]] = {}
    for index, plugin_id in enumerate(reversed(PLUGIN_IDS), start=1):
        version = f"1.{index}.0"
        rows.append(
            {
                "plugin_id": plugin_id,
                "version": version,
                "status": "installed",
                "installed": True,
                "available": True,
                "integrity_ok": True,
                "private_path": f"/private/{plugin_id}",
            }
        )
        descriptors[plugin_id] = {
            "version": version,
            "commit": str(index) * 40,
            "source_sha256": str(index + 3) * 64,
            "sha256": str(index + 6) * 64,
            "private_archive": f"/private/{plugin_id}.tar.gz",
        }
    return rows, descriptors


def _arguments() -> dict[str, object]:
    rows, descriptors = _plugin_inputs()
    worker_receipt = _signed_receipt(
        "worker_projection",
        "task-zeta",
        private_sentinel="private-worker-sentinel",
    )
    compatibility_plugins = {
        row["plugin_id"]: {
            "status": "compatible",
            "version": row["version"],
            "provenance_digest": plugin_provenance_digest(
                row,
                descriptors[str(row["plugin_id"])],
            ),
            "tool_count": index + 10,
            "tool_set_digest": str(index + 1) * 64,
            "profiles": {},
            "findings": [],
        }
        for index, row in enumerate(rows)
    }
    return {
        "run_id": "run-batch-5",
        "run_status": {
            "run_id": "run-batch-5",
            "spec_id": "spec-repo-quality",
            "status": "completed",
            "private_sentinel": "private-run-sentinel",
        },
        "autopilot_evidence": {
            "schema_version": "across-loop-evidence/1.0",
            "run_id": "run-batch-5",
            "spec_id": "spec-repo-quality",
            "status": "completed",
            "orchestrator": {
                "tasks": [
                    {"task_id": "task-zeta"},
                    {"task_id": "task-alpha"},
                    {"task_id": "task-zeta"},
                ]
            },
            "gates": [{"id": "candidate_validation_passed", "status": "passed", "required": True}],
            "candidate": _candidate(),
            "private_sentinel": "private-evidence-sentinel",
        },
        "task_evidence": [
            {
                "task_id": "task-zeta",
                "source": "worker_projection",
                "raw_receipt": worker_receipt,
                "worker_binding": _worker_binding("task-zeta", worker_receipt),
            },
            {
                "task_id": "task-alpha",
                "source": "orchestrator_evidence",
                "raw_receipt": _signed_receipt(
                    "orchestrator_evidence",
                    "task-alpha",
                    private_sentinel="private-orchestrator-sentinel",
                ),
            },
        ],
        "evidence_graph": {
            "schema_version": "across-evidence-graph/1.0",
            "run_id": "run-batch-5",
            "spec_id": "spec-repo-quality",
            "status": "completed",
            "nodes": [
                {"id": "spec:spec-repo-quality", "type": "spec", "private": "private-node"},
                {"id": "run:run-batch-5", "type": "run"},
                {"id": "task:task-alpha", "type": "task", "task_id": "task-alpha"},
                {"id": "task:task-zeta", "type": "task", "task_id": "task-zeta"},
            ],
            "edges": [
                {
                    "from": "spec:spec-repo-quality",
                    "to": "run:run-batch-5",
                    "relation": "executes",
                },
                {"from": "run:run-batch-5", "to": "task:task-alpha", "relation": "contains"},
                {"from": "run:run-batch-5", "to": "task:task-zeta", "relation": "contains"},
            ],
            "summary": {"node_count": 4, "edge_count": 3},
        },
        "plugin_rows": rows,
        "plugin_descriptors": descriptors,
        "compatibility_report": {
            "schema_version": "across-first-party-mcp-compatibility/1.0",
            "status": "compatible",
            "compatible_plugin_count": 3,
            "incompatible_plugin_count": 0,
            "portable_tool_count": 36,
            "plugins": compatibility_plugins,
            "private_sentinel": "private-compatibility-sentinel",
        },
        "release_evidence": {
            "schema_version": "1.0",
            "status": "ready",
            "release_evaluation": {
                "release_readiness": "ready",
                "evaluated_task_count": 2,
                "terminal_task_count": 2,
                "passed_task_count": 2,
                "blocked_task_count": 0,
                "manual_task_count": 0,
                "skipped_task_count": 0,
                "release_evidence_count": 4,
                "passed_evidence_count": 4,
            },
            "pre_release_gate_summary": {
                "total": 7,
                "passed": 7,
                "configured": 0,
                "manual_required": 0,
                "missing": 0,
                "failed": 0,
                "required_missing": 0,
                "required_manual": 0,
                "required_failed": 0,
                "required_unverified": 0,
            },
            "private_sentinel": "private-release-sentinel",
        },
    }


def _blocked(arguments: dict[str, object]) -> tuple[str, ...]:
    with pytest.raises(PromotionPackageBlocked) as captured:
        build_promotion_package(**arguments)
    assert str(captured.value) == "promotion package evidence is blocked"
    return captured.value.check_ids


def test_builds_deterministic_bounded_package_for_complete_multi_task_evidence():
    arguments = _arguments()

    package = build_promotion_package(**arguments)
    repeated = build_promotion_package(**deepcopy(arguments))

    assert package == repeated
    assert package["schema_version"] == "across-promotion-package/1.0"
    assert package["status"] == "ready_for_human_approval"
    assert package["identities"]["task_ids"] == ["task-alpha", "task-zeta"]
    assert [item["plugin_id"] for item in package["identities"]["plugins"]] == list(PLUGIN_IDS)
    assert all(len(item["source_sha256"]) == 64 for item in package["identities"]["plugins"])
    assert [item["task_id"] for item in package["source_digests"]["tasks"]] == [
        "task-alpha",
        "task-zeta",
    ]
    assert package["components"]["evidence_graph"] == {
        "schema_version": "across-evidence-graph/1.0",
        "run_id": "run-batch-5",
        "spec_id": "spec-repo-quality",
        "node_count": 4,
        "edge_count": 3,
        "task_node_count": 2,
        "digest": package["components"]["evidence_graph"]["digest"],
    }
    assert package["policy"] == {
        "human_approval_required": True,
        "approval_scope": "release_promotion",
        "merge_blocked": True,
        "tag_blocked": True,
        "release_blocked": True,
        "signing_blocked": True,
    }
    assert package["audit"] == {
        "receipt_checked_before_redaction": True,
        "secrets_redacted": True,
        "raw_payload_exposed": False,
    }
    assert len(package_sha256(package)) == 64
    assert package_sha256(package) == package_sha256(deepcopy(package))
    encoded = json.dumps(package, sort_keys=True)
    assert "private-" not in encoded
    assert "/private/" not in encoded
    assert "raw_receipt" not in encoded


def test_blocked_check_ids_are_sorted_unique_and_public():
    blocked = PromotionPackageBlocked(["task_receipts_verified", "finite_values", "finite_values"])

    assert blocked.check_ids == ("finite_values", "task_receipts_verified")
    assert str(blocked) == "promotion package evidence is blocked"


@pytest.mark.parametrize(
    ("mutation", "expected_check"),
    [
        (lambda args: args["run_status"].update(run_id="run-other"), "run_binding_matches"),
        (
            lambda args: args["autopilot_evidence"]["candidate"]["promotion_package"].update(
                candidate_id="candidate-other"
            ),
            "candidate_binding_matches",
        ),
        (lambda args: args["task_evidence"].pop(), "task_set_complete"),
        (
            lambda args: args["task_evidence"][1].update(
                raw_receipt=_signed_receipt("orchestrator_evidence", "task-other")
            ),
            "task_receipt_bindings_match",
        ),
    ],
)
def test_blocks_run_candidate_and_task_binding_mismatches(mutation, expected_check):
    arguments = _arguments()
    mutation(arguments)

    assert _blocked(arguments) == (expected_check,)


def test_blocks_graph_schema_identity_and_count_mismatch():
    arguments = _arguments()
    arguments["evidence_graph"]["summary"]["node_count"] = 3

    assert _blocked(arguments) == ("evidence_graph_valid",)


@pytest.mark.parametrize("mode", ["unrelated", "missing", "extra"])
def test_graph_binds_the_exact_task_set_with_run_topology(mode: str):
    arguments = _arguments()
    graph = arguments["evidence_graph"]
    if mode == "unrelated":
        graph["nodes"][-1] = {"id": "task:task-other", "type": "task", "task_id": "task-other"}
        graph["edges"][-1]["to"] = "task:task-other"
    elif mode == "missing":
        graph["nodes"].pop()
        graph["edges"].pop()
    else:
        graph["nodes"].append({"id": "task:task-other", "type": "task", "task_id": "task-other"})
        graph["edges"].append(
            {"from": "run:run-batch-5", "to": "task:task-other", "relation": "contains"}
        )
    graph["summary"]["node_count"] = len(graph["nodes"])
    graph["summary"]["edge_count"] = len(graph["edges"])

    assert _blocked(arguments) == ("evidence_graph_task_set_complete",)


def test_graph_requires_one_run_contains_edge_per_task():
    arguments = _arguments()
    graph = arguments["evidence_graph"]
    graph["edges"][-1]["relation"] = "mentions"

    assert _blocked(arguments) == ("evidence_graph_task_set_complete",)


def test_worker_receipt_requires_hash_covered_authoritative_task_link_binding():
    arguments = _arguments()
    binding = arguments["task_evidence"][0]["worker_binding"]
    binding["task_id"] = "task-alpha"

    assert _blocked(arguments) == ("worker_receipt_binding_valid",)


def test_worker_binding_builder_rejects_task_link_receipt_mismatch():
    receipt = _signed_receipt("worker_projection", "task-zeta")
    node = receipt["node"]
    link = {
        "schema_version": "across-aaa-worker-task-link/1.0",
        "task_id": "task-zeta",
        "job_id": "job-other",
        "run_id": receipt["run_id"],
        "node_id": node["node_id"],
        "manifest_hash": receipt["manifest_hash"],
        "status": "completed",
    }

    with pytest.raises(PromotionPackageBlocked) as captured:
        build_worker_task_receipt_binding(task_link=link, raw_receipt=receipt)

    assert captured.value.check_ids == ("worker_receipt_binding_valid",)


def test_same_hash_valid_worker_receipt_cannot_be_replayed_across_task_links():
    arguments = _arguments()
    first = arguments["task_evidence"][0]
    replay = deepcopy(first)
    replay["task_id"] = "task-alpha"
    replay["worker_binding"] = _worker_binding("task-alpha", replay["raw_receipt"])
    arguments["task_evidence"][1] = replay

    assert _blocked(arguments) == ("worker_receipt_replay_absent",)


@pytest.mark.parametrize("mode", ["missing", "extra"])
def test_blocks_missing_or_extra_first_party_plugin(mode: str):
    arguments = _arguments()
    if mode == "missing":
        arguments["plugin_rows"].pop()
    else:
        arguments["plugin_rows"].append(
            {
                "plugin_id": "private-extra-plugin",
                "version": "1.0.0",
                "status": "installed",
                "installed": True,
                "available": True,
                "integrity_ok": True,
            }
        )

    assert _blocked(arguments) == ("plugin_set_complete",)


def test_blocks_plugin_that_needs_repair():
    arguments = _arguments()
    arguments["plugin_rows"][0]["status"] = "needs_repair"

    assert _blocked(arguments) == ("plugin_lifecycle_ready",)


def test_blocks_unavailable_plugin():
    arguments = _arguments()
    arguments["plugin_rows"][0]["available"] = False

    assert _blocked(arguments) == ("plugin_lifecycle_ready",)


def test_blocks_incompatible_plugin_report():
    arguments = _arguments()
    arguments["compatibility_report"]["status"] = "incompatible"
    arguments["compatibility_report"]["incompatible_plugin_count"] = 1
    plugin = arguments["compatibility_report"]["plugins"]["across-context"]
    plugin["status"] = "incompatible"

    assert _blocked(arguments) == ("plugin_compatibility_ready",)


def test_blocks_plugin_version_mismatch():
    arguments = _arguments()
    arguments["compatibility_report"]["plugins"]["across-context"]["version"] = "9.9.9"

    assert _blocked(arguments) == ("plugin_versions_match",)


def test_blocks_plugin_provenance_mismatch():
    arguments = _arguments()
    arguments["compatibility_report"]["plugins"]["across-context"]["provenance_digest"] = "f" * 64

    assert _blocked(arguments) == ("plugin_provenance_matches",)


def test_blocks_invalid_source_sha_even_when_compatibility_digest_matches():
    arguments = _arguments()
    descriptor = arguments["plugin_descriptors"]["across-context"]
    descriptor["source_sha256"] = "not-a-sha256"
    row = next(row for row in arguments["plugin_rows"] if row["plugin_id"] == "across-context")
    arguments["compatibility_report"]["plugins"]["across-context"][
        "provenance_digest"
    ] = plugin_provenance_digest(row, descriptor)

    assert _blocked(arguments) == ("plugin_provenance_matches",)


@pytest.mark.parametrize("malformed", [None, [], "private-descriptor-sentinel"])
def test_malformed_plugin_descriptor_returns_fixed_blocked_check(malformed):
    arguments = _arguments()
    arguments["plugin_descriptors"]["across-context"] = malformed

    assert _blocked(arguments) == ("plugin_provenance_matches",)


@pytest.mark.parametrize("state", ["warning", "manual", "skipped", "missing", "unknown", "attention", "blocked"])
def test_blocks_every_non_ready_release_state(state: str):
    arguments = _arguments()
    arguments["release_evidence"]["status"] = state
    arguments["release_evidence"]["release_evaluation"]["release_readiness"] = state

    assert _blocked(arguments) == ("release_ready",)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda release: release.update(schema_version="private-release-schema/99"),
        lambda release: release["pre_release_gate_summary"].update(required_missing=1),
        lambda release: release["pre_release_gate_summary"].update(required_manual=1),
        lambda release: release["pre_release_gate_summary"].update(required_unverified=1),
        lambda release: release["pre_release_gate_summary"].update(required_failed=1),
        lambda release: release["pre_release_gate_summary"].update(passed=6),
        lambda release: release["release_evaluation"].update(passed_evidence_count=3),
        lambda release: release["release_evaluation"].update(blocked_task_count=1),
    ],
)
def test_blocks_contradictory_ready_release_evidence(mutation):
    arguments = _arguments()
    mutation(arguments["release_evidence"])

    assert _blocked(arguments) == ("release_ready",)


def test_sealed_package_drops_arbitrary_reviewer_text():
    arguments = _arguments()
    sentinel = "credential-private-merge-recommendation"
    arguments["autopilot_evidence"]["candidate"]["independent_reviewer"][
        "merge_recommendation"
    ] = sentinel

    package = build_promotion_package(**arguments)

    assert sentinel not in json.dumps(package, sort_keys=True)
    assert "merge_recommendation" not in package["components"]["candidate_review"]["reviewer_scores"]


@pytest.mark.parametrize("path", ["../private.py", "backend/../../private.py", "/private/project.py", "C:\\private\\project.py"])
def test_blocks_traversal_and_absolute_changed_paths(path: str):
    arguments = _arguments()
    arguments["autopilot_evidence"]["candidate"]["changed_files"] = [path]

    assert _blocked(arguments) == ("changed_paths_safe",)


def test_blocks_malformed_identifier():
    arguments = _arguments()
    arguments["autopilot_evidence"]["candidate"]["candidate_id"] = "candidate id with spaces"
    arguments["autopilot_evidence"]["candidate"]["promotion_package"][
        "candidate_id"
    ] = "candidate id with spaces"

    assert _blocked(arguments) == ("identifiers_valid",)


def test_blocks_non_finite_values_anywhere_in_source_evidence():
    arguments = _arguments()
    arguments["autopilot_evidence"]["candidate"]["independent_reviewer"]["risk_score"] = math.nan

    assert _blocked(arguments) == ("finite_values",)


@pytest.mark.parametrize(
    ("mutation", "expected_check"),
    [
        (
            lambda task: task["raw_receipt"].update(private_sentinel="mutated-after-hash"),
            "task_receipts_verified",
        ),
        (
            lambda task: task.update(
                raw_receipt={"schema_version": "private-receipt/99", "private": "do-not-leak"}
            ),
            "task_receipts_verified",
        ),
        (lambda task: task.update(raw_receipt=None), "task_receipts_verified"),
        (
            lambda task: task.update(
                raw_receipt=_signed_receipt(
                    "orchestrator_evidence",
                    "task-alpha",
                    verdict="warning",
                )
            ),
            "task_receipts_ready",
        ),
    ],
)
def test_blocks_invalid_missing_unsupported_and_non_ready_receipts(mutation, expected_check):
    arguments = _arguments()
    task = arguments["task_evidence"][1]
    mutation(task)

    assert _blocked(arguments) == (expected_check,)
