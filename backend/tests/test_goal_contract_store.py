import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from across_agents_assistant.persistence.database import Database


FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "goal-contract"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _store(db_path: Path):
    from across_agents_assistant.persistence.goal_contract_store import GoalContractStore

    db = Database(str(db_path))
    db.init_schema()
    return GoalContractStore(db)


def test_goal_revisions_are_append_only_restart_safe_and_optimistically_locked(tmp_path):
    from across_agents_assistant.persistence.goal_contract_store import GoalContractStoreError

    db_path = tmp_path / "assistant.db"
    store = _store(db_path)
    first = _fixture("simple.json")
    created = store.create_revision(first, expected_revision=0, idempotency_key="create-goal")
    assert created == first
    assert store.get_current(first["task_id"]) == first

    second = copy.deepcopy(first)
    second["revision"] = 2
    second["statement"] = "Ship a verifiable and reviewable change"
    second["confirmed_at"] = "2026-08-28T00:10:00Z"
    assert store.create_revision(second, expected_revision=1, idempotency_key="revise-goal") == second

    with pytest.raises(GoalContractStoreError, match="expected_revision") as conflict:
        store.create_revision({**second, "revision": 3}, expected_revision=1)
    assert conflict.value.code == "goal_revision_conflict"
    assert store.get_current(first["task_id"]) == second

    restarted = _store(db_path)
    assert restarted.get_current(first["task_id"]) == second
    assert restarted.list_revisions(first["goal_id"]) == [first, second]

    with sqlite3.connect(db_path) as conn, pytest.raises(sqlite3.DatabaseError, match="immutable"):
        conn.execute(
            "UPDATE goal_contract_revisions SET payload_json = '{}' WHERE goal_id = ? AND revision = 1",
            (first["goal_id"],),
        )


def test_goal_revision_idempotency_replays_identical_content_and_rejects_key_reuse(tmp_path):
    from across_agents_assistant.persistence.goal_contract_store import GoalContractStoreError

    store = _store(tmp_path / "assistant.db")
    contract = _fixture("simple.json")
    first = store.create_revision(contract, expected_revision=0, idempotency_key="same-command")
    replay = store.create_revision(contract, expected_revision=0, idempotency_key="same-command")
    assert replay == first
    assert store.list_revisions(contract["goal_id"]) == [contract]

    changed = copy.deepcopy(contract)
    changed["statement"] = "Different content"
    with pytest.raises(GoalContractStoreError, match="idempotency") as conflict:
        store.create_revision(changed, expected_revision=0, idempotency_key="same-command")
    assert conflict.value.code == "goal_idempotency_conflict"


def test_concurrent_goal_revision_writers_cannot_overwrite_each_other(tmp_path):
    from across_agents_assistant.persistence.goal_contract_store import GoalContractStoreError

    store = _store(tmp_path / "assistant.db")
    first = _fixture("simple.json")
    store.create_revision(first, expected_revision=0)

    def write(statement: str):
        candidate = copy.deepcopy(first)
        candidate["revision"] = 2
        candidate["statement"] = statement
        candidate["confirmed_at"] = "2026-08-28T00:20:00Z"
        try:
            return ("created", store.create_revision(candidate, expected_revision=1))
        except GoalContractStoreError as exc:
            return (exc.code, None)

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(write, ("Writer A", "Writer B")))

    assert sorted(item[0] for item in outcomes) == ["created", "goal_revision_conflict"]
    assert len(store.list_revisions(first["goal_id"])) == 2


def test_proposal_decisions_are_restart_safe_and_revision_bound(tmp_path):
    from across_agents_assistant.persistence.goal_contract_store import GoalContractStoreError

    db_path = tmp_path / "assistant.db"
    store = _store(db_path)
    store.create_revision(_fixture("simple.json"), expected_revision=0)
    proposal = _fixture("change-proposal.json")
    saved = store.save_proposal(proposal, idempotency_key="proposal-create")
    assert saved["decision_state"] == "pending"

    decided = store.decide_proposal(
        proposal["proposal_id"],
        decision="rejected",
        expected_revision=1,
        decision_receipt={"receipt_id": "receipt-1", "purpose": "goal_change_decision"},
        idempotency_key="proposal-decision",
    )
    assert decided["decision_state"] == "rejected"
    assert _store(db_path).get_proposal(proposal["proposal_id"])["decision_receipt"]["receipt_id"] == "receipt-1"

    with pytest.raises(GoalContractStoreError, match="base revision") as conflict:
        store.decide_proposal(
            proposal["proposal_id"],
            decision="accepted",
            expected_revision=2,
            decision_receipt={"receipt_id": "receipt-2"},
        )
    assert conflict.value.code == "goal_revision_conflict"
