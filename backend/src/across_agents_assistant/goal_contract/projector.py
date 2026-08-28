from __future__ import annotations

from typing import Any

from .models import GoalProjectionFacts


_TERMINAL_EXECUTION_STATES = {"finished", "failed", "cancelled"}
_VALID_EVIDENCE = {"verified"}
_VALID_REVIEWS = {"passed", "waived"}


def project_goal_state(facts: GoalProjectionFacts) -> dict[str, Any]:
    contract = dict(facts.contract)
    reasons: list[str] = []
    confirmed = bool(contract.get("confirmed_by") and contract.get("confirmed_at"))
    if not confirmed:
        reasons.append("goal_needs_confirmation")

    if any(state != "satisfied" for state in facts.dependencies.values()):
        reasons.append("dependency_unsatisfied")

    coverage: list[dict[str, Any]] = []
    evidence_states: list[str] = []
    review_states: list[str] = []
    for criterion in contract.get("acceptance_criteria") or []:
        if not criterion.get("required", True):
            continue
        identifier = str(criterion.get("criterion_id") or "")
        evidence = facts.criterion_evidence.get(identifier, "missing")
        evidence_states.append(evidence)
        if evidence == "missing":
            _append_once(reasons, "criterion_evidence_missing")
        elif evidence == "stale":
            _append_once(reasons, "criterion_evidence_stale")
        elif evidence not in _VALID_EVIDENCE:
            _append_once(reasons, "criterion_evidence_failed")

        review_policy = str(criterion.get("review_policy") or "automatic")
        review = "not_required" if review_policy == "automatic" else facts.reviews.get(identifier, "pending")
        review_states.append(review)
        if review == "pending":
            _append_once(reasons, "review_pending")
        elif review not in _VALID_REVIEWS and review != "not_required":
            _append_once(reasons, "review_failed")
        coverage.append(
            {
                "criterion_id": identifier,
                "required": True,
                "evidence_state": evidence,
                "review_state": review,
                "satisfied": evidence in _VALID_EVIDENCE and review in {*_VALID_REVIEWS, "not_required"},
            }
        )

    if facts.pending_decisions:
        reasons.append("decision_pending")
    if facts.active_lease_count > 0:
        reasons.append("lease_active")
    if facts.execution_state == "failed":
        reasons.append("execution_failed")
    elif facts.execution_state == "cancelled":
        reasons.append("execution_cancelled")
    elif facts.execution_state not in _TERMINAL_EXECUTION_STATES:
        reasons.append("execution_not_terminal")

    evidence_state = _evidence_state(evidence_states)
    review_state = _review_state(review_states)
    validity_state = "revalidation_required" if "stale" in evidence_states else "valid"
    is_complete = not reasons and facts.execution_state == "finished"
    return {
        "schema_version": "across-goal-state-projection/1.0",
        "goal_id": contract.get("goal_id"),
        "goal_revision": contract.get("revision"),
        "task_id": contract.get("task_id"),
        "definition_state": "confirmed" if confirmed else "needs_confirmation",
        "execution_state": facts.execution_state,
        "evidence_state": evidence_state,
        "review_state": review_state,
        "decision_state": "change_pending" if facts.pending_decisions else "none",
        "validity_state": validity_state,
        "criterion_coverage": coverage,
        "reason_codes": reasons,
        "is_complete": is_complete,
        "display_state": _display_state(reasons, facts.execution_state, is_complete),
        "authority": {
            "goal": "aaa",
            "execution": "orchestrator_or_direct_agent",
            "evidence": "trusted_runtime",
            "decisions": "aaa",
        },
    }


def _append_once(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _evidence_state(states: list[str]) -> str:
    if not states or all(state == "missing" for state in states):
        return "none"
    if any(state not in {"verified", "missing", "stale"} for state in states):
        return "failed"
    if "stale" in states:
        return "stale"
    if all(state == "verified" for state in states):
        return "satisfied"
    return "partial"


def _review_state(states: list[str]) -> str:
    required = [state for state in states if state != "not_required"]
    if not required:
        return "not_required"
    if any(state not in {*_VALID_REVIEWS, "pending"} for state in required):
        return "failed"
    if any(state == "pending" for state in required):
        return "pending"
    return "passed"


def _display_state(reasons: list[str], execution_state: str, is_complete: bool) -> str:
    if is_complete:
        return "completed"
    if "goal_needs_confirmation" in reasons:
        return "needs_confirmation"
    if "decision_pending" in reasons:
        return "waiting_for_decision"
    if "criterion_evidence_stale" in reasons:
        return "revalidation_required"
    if "review_pending" in reasons:
        return "waiting_for_review"
    if execution_state == "running" or "lease_active" in reasons:
        return "running"
    if "criterion_evidence_missing" in reasons:
        return "waiting_for_evidence"
    return execution_state
