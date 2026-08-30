import copy

import pytest

from across_agents_assistant.goal_contract.models import GoalProjectionFacts


def _contract() -> dict:
    return {
        "schema_version": "across-goal-contract/1.0",
        "goal_id": "goal-1",
        "revision": 1,
        "task_id": "task-1",
        "statement": "Ship",
        "success_outcome": "A verified result",
        "scope": {"includes": ["implementation"], "excludes": ["release"]},
        "acceptance_criteria": [
            {
                "criterion_id": "criterion-a",
                "description": "Tests pass",
                "required": True,
                "validator_kind": "test_suite",
                "review_policy": "automatic",
                "source": "user_confirmed",
            },
            {
                "criterion_id": "criterion-b",
                "description": "Human reviews result",
                "required": True,
                "validator_kind": "installed_user_journey",
                "review_policy": "human",
                "source": "user_confirmed",
            },
        ],
        "dependencies": [],
        "execution_profile": "orchestrated",
        "source": "user",
        "confirmed_by": "human:user",
        "confirmed_at": "2026-08-28T00:00:00Z",
        "created_at": "2026-08-28T00:00:00Z",
    }


def _facts() -> GoalProjectionFacts:
    return GoalProjectionFacts(
        contract=_contract(),
        dependencies={"dependency-a": "satisfied"},
        criterion_evidence={"criterion-a": "verified", "criterion-b": "verified"},
        reviews={"criterion-b": "passed"},
        pending_decisions=(),
        active_lease_count=0,
        execution_state="finished",
    )


def test_projector_derives_completed_without_a_writable_completed_fact():
    from across_agents_assistant.goal_contract.projector import project_goal_state

    projection = project_goal_state(_facts())
    assert projection["schema_version"] == "across-goal-state-projection/1.0"
    assert projection["display_state"] == "completed"
    assert projection["is_complete"] is True
    assert projection["reason_codes"] == []
    assert "completed" not in _facts().__dict__


@pytest.mark.parametrize(
    ("mutate", "reason_code"),
    [
        (lambda facts: facts.contract.pop("confirmed_by"), "goal_needs_confirmation"),
        (lambda facts: facts.dependencies.update({"dependency-a": "pending"}), "dependency_unsatisfied"),
        (lambda facts: facts.criterion_evidence.pop("criterion-a"), "criterion_evidence_missing"),
        (lambda facts: facts.criterion_evidence.update({"criterion-a": "stale"}), "criterion_evidence_stale"),
        (lambda facts: facts.reviews.update({"criterion-b": "pending"}), "review_pending"),
        (lambda facts: setattr(facts, "pending_decisions", ("proposal-1",)), "decision_pending"),
        (lambda facts: setattr(facts, "active_lease_count", 1), "lease_active"),
        (lambda facts: setattr(facts, "execution_state", "running"), "execution_not_terminal"),
        (lambda facts: setattr(facts, "execution_state", "failed"), "execution_failed"),
        (lambda facts: setattr(facts, "execution_state", "cancelled"), "execution_cancelled"),
    ],
)
def test_each_required_fact_blocks_completion_with_a_stable_reason(mutate, reason_code):
    from across_agents_assistant.goal_contract.projector import project_goal_state

    facts = copy.deepcopy(_facts())
    mutate(facts)
    projection = project_goal_state(facts)
    assert projection["is_complete"] is False
    assert reason_code in projection["reason_codes"]


def test_failed_evidence_and_review_are_explicit_blockers():
    from across_agents_assistant.goal_contract.projector import project_goal_state

    facts = _facts()
    facts.criterion_evidence["criterion-a"] = "failed"
    facts.reviews["criterion-b"] = "failed"
    projection = project_goal_state(facts)
    assert projection["evidence_state"] == "failed"
    assert projection["review_state"] == "failed"
    assert "criterion_evidence_failed" in projection["reason_codes"]
    assert "review_failed" in projection["reason_codes"]


def test_rejected_review_is_a_visible_repair_state_not_a_hidden_error_surface():
    from across_agents_assistant.goal_contract.projector import project_goal_state

    facts = _facts()
    facts.reviews["criterion-b"] = "rejected"
    projection = project_goal_state(facts)

    assert projection["display_state"] == "repair_required"
    assert projection["is_complete"] is False
