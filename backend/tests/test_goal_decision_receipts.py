import copy
import json
from pathlib import Path

import pytest

from across_agents_assistant.approval.receipts import (
    ApprovalReceiptError,
    ApprovalReceiptStore,
    ApprovalReceiptSubject,
    verify_approval_receipt_purpose,
)


FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "goal-contract"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def test_goal_decision_receipt_is_purpose_and_revision_bound(tmp_path):
    store = ApprovalReceiptStore(str(tmp_path / "receipts.db"))
    goal = _fixture("simple.json")
    subject = ApprovalReceiptSubject(
        "goal_revision",
        f"{goal['goal_id']}:{goal['revision']}",
        goal,
    )
    receipt = store.record(
        subject=subject,
        scope="goal_change_decision",
        purpose="goal_change_decision",
        decision="approved",
        proposer_id="autopilot",
        approver_id="local-human",
        idempotency_key="goal-decision-1",
    )

    assert receipt["purpose"] == "goal_change_decision"
    assert verify_approval_receipt_purpose(
        receipt,
        expected_purpose="goal_change_decision",
        subject_type="goal_revision",
        subject_id=f"{goal['goal_id']}:{goal['revision']}",
        subject_payload=goal,
    )

    with pytest.raises(ApprovalReceiptError, match="purpose"):
        verify_approval_receipt_purpose(
            receipt,
            expected_purpose="goal_review_waiver",
            subject_type="goal_revision",
            subject_id=f"{goal['goal_id']}:{goal['revision']}",
            subject_payload=goal,
        )

    revised = copy.deepcopy(goal)
    revised["revision"] = 2
    with pytest.raises(ApprovalReceiptError, match="subject"):
        verify_approval_receipt_purpose(
            receipt,
            expected_purpose="goal_change_decision",
            subject_type="goal_revision",
            subject_id=f"{goal['goal_id']}:2",
            subject_payload=revised,
        )


def test_unknown_explicit_receipt_purpose_fails_closed(tmp_path):
    store = ApprovalReceiptStore(str(tmp_path / "receipts.db"))
    with pytest.raises(ApprovalReceiptError, match="purpose"):
        store.record(
            subject=ApprovalReceiptSubject("goal_revision", "goal-1:1", {"revision": 1}),
            scope="goal_change_decision",
            purpose="plugin_self_approval",
            decision="approved",
            proposer_id="plugin",
            approver_id="plugin",
        )
