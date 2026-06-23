from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any, Mapping


PROMOTION_REVIEW_SCHEMA_VERSION = "across-autopilot-promotion-review/1.0"
PROMOTION_ATTESTATION_SCHEMA_VERSION = "across-autopilot-promotion-attestation/1.0"


def build_promotion_review_packet(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Build a bounded human-review packet from an Autopilot evidence envelope."""

    candidate = _dict(evidence.get("candidate"))
    package = _dict(candidate.get("promotion_package"))
    reviewer = _dict(candidate.get("independent_reviewer"))
    validation = _dict(candidate.get("validation"))
    self_hosting_probe = _dict(candidate.get("self_hosting_probe"))
    source_ref_pins = _dict(package.get("source_ref_pins"))
    quality_findings = _list(candidate.get("quality_findings"))
    required_gates = [gate for gate in _list(evidence.get("gates")) if _dict(gate).get("required") is not False]
    gate_failures = [
        _dict(gate)
        for gate in required_gates
        if _dict(gate).get("status") != "passed"
    ]
    model_separation = _dict(reviewer.get("model_separation"))
    attestation = build_promotion_attestation(evidence)
    checklist = [
        _check("promotion_package_present", bool(package), "Promotion package is present."),
        _check(
            "source_a_unchanged",
            package.get("source_a_unchanged") is True,
            "Source A remained unchanged during candidate mutation.",
        ),
        _check(
            "source_refs_pinned",
            source_ref_pins.get("status") == "passed" and len(_list(source_ref_pins.get("repos"))) >= 4,
            "Promotion package pins source refs for the Across repository set.",
            details={
                "missing_required_repos": _list(source_ref_pins.get("missing_required_repos")),
                "missing_pins": _list(source_ref_pins.get("missing_pins")),
                "changed_sources": _list(source_ref_pins.get("changed_sources")),
            },
        ),
        _check(
            "candidate_has_diff",
            len(_list(candidate.get("changed_files"))) > 0,
            "Candidate contains reviewable changes.",
        ),
        _check(
            "validation_passed",
            validation.get("status") == "passed",
            "Candidate validation commands passed.",
        ),
        _check(
            "self_hosting_probe_passed",
            not self_hosting_probe.get("required") or self_hosting_probe.get("status") == "passed",
            "Required self-hosting probe passed or was not required.",
        ),
        _check(
            "semantic_alignment_passed",
            candidate.get("semantic_alignment_status") == "passed",
            "Semantic alignment review passed.",
        ),
        _check(
            "distinct_reviewer_model_passed",
            model_separation.get("required") is not True or model_separation.get("status") == "passed",
            "Reviewer model is distinct from builder when required.",
        ),
        _check(
            "promotion_attestation_present",
            attestation.get("digest_status") == "passed",
            "Promotion package provenance digest is present.",
            details={
                "signing_status": attestation.get("signing_status"),
                "signature_required_for_release": attestation.get("signature_required_for_release"),
            },
        ),
        _check(
            "required_gates_passed",
            not gate_failures,
            "All required gates passed.",
            details=[gate.get("id") or gate.get("type") for gate in gate_failures],
        ),
        _check(
            "no_blocking_quality_findings",
            not [item for item in quality_findings if _dict(item).get("severity") == "error"],
            "No blocking deterministic quality findings.",
        ),
    ]
    ready = bool(candidate.get("promotion_ready")) and all(item["status"] == "passed" for item in checklist)
    reviewer_scores = _dict(package.get("reviewer_scores")) or {
        "product_value_score": reviewer.get("product_value_score"),
        "maintainability_score": reviewer.get("maintainability_score"),
        "risk_score": reviewer.get("risk_score"),
        "merge_recommendation": reviewer.get("merge_recommendation"),
    }
    return {
        "schema_version": PROMOTION_REVIEW_SCHEMA_VERSION,
        "status": "ready_for_human_review" if ready else "needs_attention",
        "human_approval_required": True,
        "promotion_ready": ready,
        "run_id": evidence.get("run_id"),
        "spec_id": evidence.get("spec_id"),
        "candidate_id": candidate.get("candidate_id") or package.get("candidate_id"),
        "selected_target_id": (_dict(candidate.get("research_strategy")).get("selected_target_id")),
        "changed_files": _list(candidate.get("changed_files")),
        "checklist": checklist,
        "quality_findings": quality_findings,
        "known_risks": _list(package.get("known_risks")),
        "source_ref_pins": source_ref_pins,
        "promotion_attestation": attestation,
        "reviewer_scores": reviewer_scores,
        "model_separation": model_separation,
        "recommended_pr": _dict(package.get("recommended_pr")),
        "allowed_actions": {
            "open_review_pr": ready,
            "merge": False,
            "tag": False,
            "release": False,
            "sign": False,
        },
        "blocked_actions": [
            "merge",
            "tag",
            "release",
            "sign",
        ],
        "next_step": "open_review_pr" if ready else "repair_or_re-run_before_review",
    }


def build_promotion_attestation(evidence: Mapping[str, Any]) -> dict[str, Any]:
    candidate = _dict(evidence.get("candidate"))
    package = _dict(candidate.get("promotion_package"))
    reviewer = _dict(candidate.get("independent_reviewer"))
    source_ref_pins = _dict(package.get("source_ref_pins"))
    payload = {
        "run_id": evidence.get("run_id"),
        "spec_id": evidence.get("spec_id"),
        "candidate_id": candidate.get("candidate_id") or package.get("candidate_id"),
        "promotion_ready": candidate.get("promotion_ready"),
        "changed_files": _list(candidate.get("changed_files")) or _list(package.get("changed_files")),
        "source_ref_pins": source_ref_pins,
        "reviewer_scores": _dict(package.get("reviewer_scores")),
        "model_separation": _dict(reviewer.get("model_separation")),
        "quality_findings": _list(candidate.get("quality_findings")),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    signing_key = os.environ.get("ACROSS_PROMOTION_SIGNING_KEY")
    signature = None
    signing_status = "unsigned_review_only"
    if signing_key:
        signature = hmac.new(signing_key.encode("utf-8"), digest.encode("utf-8"), hashlib.sha256).hexdigest()
        signing_status = "signed"
    return {
        "schema_version": PROMOTION_ATTESTATION_SCHEMA_VERSION,
        "digest_status": "passed",
        "algorithm": "sha256",
        "digest": digest,
        "payload_fields": sorted(payload.keys()),
        "signing_status": signing_status,
        "signature_algorithm": "hmac-sha256" if signature else None,
        "signature": signature,
        "signature_required_for_release": True,
        "human_approval_required": True,
        "merge_release_signing_blocked": True,
    }


def _check(id_: str, passed: bool, label: str, details: Any | None = None) -> dict[str, Any]:
    item = {
        "id": id_,
        "label": label,
        "status": "passed" if passed else "failed",
    }
    if details:
        item["details"] = details
    return item


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []
