import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from across_agents_assistant.approval.receipts import (
    ApprovalReceiptError,
    ApprovalReceiptStore,
    ApprovalReceiptSubject,
    evaluate_promotion_authorization,
)
from across_agents_assistant.persistence.promotion_package_store import PromotionPackageStore
from across_agents_assistant.persistence.service import PersistenceService
from across_agents_assistant.promotion_package import package_sha256


def subject(payload=None):
    return ApprovalReceiptSubject(
        subject_type="tool_call",
        subject_id="tool-call-1",
        payload=payload or {"tool_name": "quality_check", "arguments": {"mode": "safe"}},
    )


def promotion_document():
    return {
        "schema_version": "across-promotion-package/1.0",
        "status": "ready_for_human_approval",
        "identities": {
            "run_id": "run-batch-5",
            "spec_id": "spec-repo-quality",
            "candidate_id": "candidate-batch-5",
            "task_ids": ["task-alpha", "task-zeta"],
            "plugins": [
                {"plugin_id": "across-autopilot"},
                {"plugin_id": "across-context"},
                {"plugin_id": "across-orchestrator"},
            ],
        },
        "checks": ["release_ready"],
    }


def promotion_subject(record, *, digest=None):
    return ApprovalReceiptSubject(
        subject_type="promotion_package",
        subject_id=record["package_id"],
        payload={},
        subject_sha256=digest or record["package_sha256"],
    )


def promotion_decision(store, record, *, decision="approved", proposer="agent-builder", approver="human-reviewer"):
    return store.record(
        subject=promotion_subject(record),
        scope="release_promotion",
        decision=decision,
        proposer_id=proposer,
        approver_id=approver,
    )


def authorization(package_record, decision_store, decision):
    return evaluate_promotion_authorization(
        package_record,
        decision,
        decision_store.verify_chain(),
    )


def test_latest_for_subject_uses_hashed_binding_and_returns_latest_public_decision(tmp_path):
    db_path = str(tmp_path / "lookup.db")
    packages = PromotionPackageStore(db_path)
    decisions = ApprovalReceiptStore(db_path)
    record = packages.put(promotion_document())
    promotion_decision(decisions, record, decision="approved")
    latest = promotion_decision(decisions, record, decision="rejected")

    loaded = decisions.latest_for_subject(
        scope="release_promotion",
        subject_type="promotion_package",
        subject_id=record["package_id"],
        subject_sha256=record["package_sha256"],
    )

    assert loaded == latest
    assert record["package_id"] not in json.dumps(loaded)
    with sqlite3.connect(db_path) as conn:
        index_columns = [
            row[2]
            for row in conn.execute(
                "PRAGMA index_info(idx_approval_receipts_subject_lookup)"
            ).fetchall()
        ]
    assert index_columns == [
        "scope",
        "subject_type",
        "subject_id_sha256",
        "subject_sha256",
        "sequence",
    ]


def test_promotion_authorization_requires_an_explicit_approved_decision(tmp_path):
    db_path = str(tmp_path / "explicit.db")
    packages = PromotionPackageStore(db_path)
    decisions = ApprovalReceiptStore(db_path)
    record = packages.put(promotion_document())

    no_decision = authorization(record, decisions, None)
    rejection = promotion_decision(decisions, record, decision="rejected")
    rejected = authorization(record, decisions, rejection)
    approval = promotion_decision(decisions, record, decision="approved")
    approved = authorization(record, decisions, approval)

    assert no_decision["authorized"] is False
    assert no_decision["checks"]["decision_present"] is False
    assert rejected["authorized"] is False
    assert rejected["checks"]["decision_approved"] is False
    assert approved["authorized"] is True
    assert approved["status"] == "authorized"
    assert all(approved["checks"].values())


def test_promotion_authorization_rejects_wrong_hash_and_same_actor_claims(tmp_path):
    db_path = str(tmp_path / "binding.db")
    packages = PromotionPackageStore(db_path)
    decisions = ApprovalReceiptStore(db_path)
    record = packages.put(promotion_document())
    wrong_hash = "f" * 64
    wrong = decisions.record(
        subject=promotion_subject(record, digest=wrong_hash),
        scope="release_promotion",
        decision="approved",
        proposer_id="agent-builder",
        approver_id="human-reviewer",
    )
    wrong_result = authorization(record, decisions, wrong)

    forged_actor = deepcopy(wrong)
    forged_actor.update(
        subject_sha256=record["package_sha256"],
        proposer_id="same-actor",
        approver_id="same-actor",
        integrity_status="verified",
    )
    actor_result = authorization(record, decisions, forged_actor)

    forged_decision = deepcopy(promotion_decision(decisions, record, decision="rejected"))
    forged_decision["decision"] = "approved"
    decision_result = authorization(record, decisions, forged_decision)

    assert wrong_result["authorized"] is False
    assert wrong_result["checks"]["subject_binding_matches"] is False
    assert actor_result["authorized"] is False
    assert actor_result["checks"]["separate_actors"] is False
    assert actor_result["checks"]["decision_integrity_verified"] is False
    assert decision_result["authorized"] is False
    assert decision_result["checks"]["decision_integrity_verified"] is False


def test_promotion_authorization_rejects_package_and_decision_tampering(tmp_path):
    db_path = str(tmp_path / "row-tamper.db")
    packages = PromotionPackageStore(db_path)
    decisions = ApprovalReceiptStore(db_path)
    record = packages.put(promotion_document())
    decision = promotion_decision(decisions, record)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE promotion_packages SET candidate_id = 'candidate-other' WHERE package_id = ?",
            (record["package_id"],),
        )
        conn.execute(
            "UPDATE approval_receipts SET approver_id = 'actor-other' WHERE receipt_id = ?",
            (decision["receipt_id"],),
        )

    tampered_package = packages.get(record["package_id"])
    tampered_decision = decisions.latest_for_subject(
        scope="release_promotion",
        subject_type="promotion_package",
        subject_id=record["package_id"],
        subject_sha256=record["package_sha256"],
    )
    result = authorization(tampered_package, decisions, tampered_decision)

    assert result["authorized"] is False
    assert result["checks"]["package_integrity_verified"] is False
    assert result["checks"]["decision_integrity_verified"] is False


def test_promotion_authorization_rejects_earlier_row_and_chain_anchor_tampering(tmp_path):
    for tamper in ("earlier-row", "chain-anchor"):
        db_path = str(tmp_path / f"{tamper}.db")
        packages = PromotionPackageStore(db_path)
        decisions = ApprovalReceiptStore(db_path)
        record = packages.put(promotion_document())
        earlier = decisions.record(
            subject=subject(),
            scope="tool_execution",
            decision="approved",
            proposer_id="agent",
            approver_id="human",
        )
        decision = promotion_decision(decisions, record)
        with sqlite3.connect(db_path) as conn:
            if tamper == "earlier-row":
                conn.execute(
                    "UPDATE approval_receipts SET decision = 'rejected' WHERE receipt_id = ?",
                    (earlier["receipt_id"],),
                )
            else:
                conn.execute(
                    "UPDATE approval_receipt_chain_state SET chain_tip = ? WHERE id = 1",
                    ("f" * 64,),
                )

        result = authorization(packages.get(record["package_id"]), decisions, decision)

        assert result["authorized"] is False
        assert result["checks"]["chain_integrity_verified"] is False


def test_repeated_concurrent_promotion_approval_is_idempotent_and_chain_valid(tmp_path):
    db_path = str(tmp_path / "concurrent-promotion.db")
    packages = PromotionPackageStore(db_path)
    decisions = ApprovalReceiptStore(db_path)
    record = packages.put(promotion_document())

    def approve(_index):
        return promotion_decision(decisions, record)

    with ThreadPoolExecutor(max_workers=8) as executor:
        receipts = list(executor.map(approve, range(16)))

    assert len({item["receipt_id"] for item in receipts}) == 1
    assert decisions.verify_chain()["integrity_status"] == "verified"
    assert decisions.verify_chain()["receipt_count"] == 1
    assert authorization(record, decisions, receipts[0])["authorized"] is True


def test_approval_never_mutates_the_immutable_package_bytes(tmp_path):
    db_path = str(tmp_path / "immutable.db")
    packages = PromotionPackageStore(db_path)
    decisions = ApprovalReceiptStore(db_path)
    document = promotion_document()
    record = packages.put(document)
    with sqlite3.connect(db_path) as conn:
        before = conn.execute(
            "SELECT payload_json FROM promotion_packages WHERE package_id = ?",
            (record["package_id"],),
        ).fetchone()[0]

    decision = promotion_decision(decisions, record)

    with sqlite3.connect(db_path) as conn:
        after = conn.execute(
            "SELECT payload_json FROM promotion_packages WHERE package_id = ?",
            (record["package_id"],),
        ).fetchone()[0]
    assert after == before
    assert json.loads(after) == document
    assert package_sha256(json.loads(after)) == record["package_sha256"]
    assert authorization(packages.get(record["package_id"]), decisions, decision)["authorized"] is True


def test_receipt_survives_restart_is_idempotent_and_hash_chained(tmp_path):
    db_path = str(tmp_path / "assistant.db")
    first_store = ApprovalReceiptStore(db_path)
    first = first_store.record(
        subject=subject(),
        scope="tool_execution",
        decision="approved",
        proposer_id="agent-builder",
        approver_id="human-reviewer",
        risk_level="medium",
        request_id="request-1",
        idempotency_key="decision-1",
    )
    duplicate = first_store.record(
        subject=subject(),
        scope="tool_execution",
        decision="approved",
        proposer_id="agent-builder",
        approver_id="human-reviewer",
        risk_level="medium",
        request_id="request-1",
        idempotency_key="decision-1",
    )
    assert duplicate["receipt_id"] == first["receipt_id"]

    restarted = ApprovalReceiptStore(db_path)
    loaded = restarted.get(first["receipt_id"])
    second = restarted.record(
        subject=ApprovalReceiptSubject("tool_call", "tool-call-2", {"tool_name": "tests"}),
        scope="tool_execution",
        decision="rejected",
        proposer_id="agent-builder",
        approver_id="human-reviewer",
        request_id="request-2",
    )

    assert loaded["integrity_status"] == "verified"
    assert second["previous_receipt_id"] == first["receipt_id"]
    assert second["previous_hash"] == first["receipt_hash"]
    assert restarted.verify_chain()["integrity_status"] == "verified"
    assert restarted.verify_chain()["receipt_count"] == 2


def test_concurrent_receipts_are_serialized_into_one_verified_chain(tmp_path):
    db_path = str(tmp_path / "concurrent.db")
    store = ApprovalReceiptStore(db_path)

    def record(index):
        return store.record(
            subject=ApprovalReceiptSubject(
                "tool_call",
                f"tool-call-{index}",
                {"tool_name": "quality_check", "index": index},
            ),
            scope="tool_execution",
            decision="approved",
            proposer_id="agent-builder",
            approver_id="human-reviewer",
            idempotency_key=f"concurrent-{index}",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        receipts = list(executor.map(record, range(16)))

    assert len({item["receipt_id"] for item in receipts}) == 16
    assert store.verify_chain()["integrity_status"] == "verified"
    assert store.verify_chain()["receipt_count"] == 16


def test_receipt_rejects_tampering_and_separates_sensitive_proposer_and_approver(tmp_path):
    db_path = str(tmp_path / "assistant.db")
    store = ApprovalReceiptStore(db_path)
    with pytest.raises(ApprovalReceiptError, match="separate proposer"):
        store.record(
            subject=subject(),
            scope="release_promotion",
            decision="approved",
            proposer_id="same-actor",
            approver_id="same-actor",
        )
    rejection = store.record(
        subject=subject(),
        scope="release_promotion",
        decision="rejected",
        proposer_id="same-actor",
        approver_id="same-actor",
    )
    assert rejection["decision"] == "rejected"

    receipt = store.record(
        subject=subject(),
        scope="workspace_promotion",
        decision="approved",
        proposer_id="candidate:one",
        approver_id="human-reviewer",
    )
    with sqlite3.connect(db_path) as conn:
        payload = json.loads(conn.execute(
            "SELECT payload_json FROM approval_receipts WHERE receipt_id = ?",
            (receipt["receipt_id"],),
        ).fetchone()[0])
        payload["decision"] = "rejected"
        conn.execute(
            "UPDATE approval_receipts SET payload_json = ? WHERE receipt_id = ?",
            (json.dumps(payload), receipt["receipt_id"]),
        )

    assert store.get(receipt["receipt_id"])["integrity_status"] == "tampered"
    assert store.verify_chain()["integrity_status"] == "tampered"


@pytest.mark.parametrize(("column", "value"), [("decision", "rejected"), ("scope", "tool_execution")])
def test_receipt_detects_semantic_column_tampering(tmp_path, column, value):
    db_path = str(tmp_path / f"tampered-{column}.db")
    store = ApprovalReceiptStore(db_path)
    receipt = store.record(
        subject=subject(),
        scope="workspace_promotion",
        decision="approved",
        proposer_id="agent-builder",
        approver_id="human-reviewer",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"UPDATE approval_receipts SET {column} = ? WHERE receipt_id = ?",
            (value, receipt["receipt_id"]),
        )

    assert store.get(receipt["receipt_id"])["integrity_status"] == "tampered"
    assert store.verify_chain()["integrity_status"] == "tampered"


def test_paginated_listing_reports_complete_chain_integrity(tmp_path):
    db_path = str(tmp_path / "pagination.db")
    store = ApprovalReceiptStore(db_path)
    receipts = []
    for index in range(3):
        receipts.append(store.record(
            subject=ApprovalReceiptSubject("tool_call", f"tool-{index}", {"index": index}),
            scope="tool_execution",
            decision="approved",
            proposer_id="agent",
            approver_id="human",
            idempotency_key=f"page-{index}",
        ))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE approval_receipts SET scope = 'tampered_scope' WHERE receipt_id = ?",
            (receipts[0]["receipt_id"],),
        )

    listing = store.list(limit=1, offset=0)
    assert listing["page_integrity_status"] == "verified"
    assert listing["chain_integrity_status"] == "tampered"
    assert listing["integrity_status"] == "tampered"


def test_persistence_receipt_is_not_verified_when_an_earlier_chain_row_is_tampered(tmp_path):
    db_path = str(tmp_path / "service-chain.db")
    service = PersistenceService(db_path)
    first = service.record_approval_receipt(
        subject_type="tool_call",
        subject_id="first",
        subject_payload={"tool_name": "quality_check"},
        scope="tool_execution",
        decision="approved",
        proposer_id="agent",
        approver_id="human",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE approval_receipts SET decision = 'rejected' WHERE receipt_id = ?",
            (first["receipt_id"],),
        )
    second = service.record_approval_receipt(
        subject_type="tool_call",
        subject_id="second",
        subject_payload={"tool_name": "quality_check"},
        scope="tool_execution",
        decision="approved",
        proposer_id="agent",
        approver_id="human",
    )

    assert second["receipt_integrity_status"] == "verified"
    assert second["chain_integrity_status"] == "tampered"
    assert second["integrity_status"] == "tampered"


def test_chain_anchor_detects_tail_receipt_deletion(tmp_path):
    db_path = str(tmp_path / "truncated.db")
    store = ApprovalReceiptStore(db_path)
    receipts = []
    for index in range(2):
        receipts.append(store.record(
            subject=ApprovalReceiptSubject("tool_call", f"tail-{index}", {"index": index}),
            scope="tool_execution",
            decision="approved",
            proposer_id="agent",
            approver_id="human",
            idempotency_key=f"tail-{index}",
        ))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "DELETE FROM approval_receipts WHERE receipt_id = ?",
            (receipts[-1]["receipt_id"],),
        )

    verification = store.verify_chain()
    assert verification["integrity_status"] == "tampered"
    assert verification["failures"] == [{
        "receipt_id": "chain-anchor",
        "status": "truncated_or_replaced",
    }]


@pytest.mark.asyncio
async def test_workspace_promotion_does_not_run_when_receipt_is_rejected(monkeypatch):
    import across_agents_assistant.api_server as api_server

    class FakeManager:
        promote_calls = 0

        def get(self, workspace_id):
            return {
                "workspace_id": workspace_id,
                "selected_candidate_id": "candidate-1",
                "candidates": [{
                    "candidate_id": "candidate-1",
                    "comparison": {"patch_sha256": "b" * 64},
                }],
            }

        def promote(self, *args, **kwargs):
            self.promote_calls += 1
            return {"status": "promoted"}

    manager = FakeManager()
    monkeypatch.setattr(api_server, "get_agent_workspace_manager", lambda: manager)
    monkeypatch.setattr(
        api_server,
        "_record_approval_receipt",
        lambda **kwargs: {"integrity_status": "legacy_persistence_unavailable"},
    )

    with pytest.raises(api_server.HTTPException):
        await api_server.promote_agent_workspace(
            "workspace-1",
            api_server.AgentWorkspacePromoteRequest(
                candidate_id="candidate-1",
                approved=True,
                approved_by="human-reviewer",
            ),
        )
    assert manager.promote_calls == 0


def test_receipt_output_and_database_do_not_store_paths_secrets_or_transcripts(tmp_path):
    db_path = str(tmp_path / "assistant.db")
    store = ApprovalReceiptStore(db_path)
    # Build the sentinel at runtime so the publishable test suite never embeds
    # a value that secret scanners correctly classify as a live-looking key.
    fake_secret = "sk-" + "abcdefghijklmnopqrstuv"
    receipt = store.record(
        subject=subject({
            "tool_name": "read_file",
            "path": "/Users/example/Documents/private/repo",
            "api_key": fake_secret,
            "raw_transcript": "private full conversation",
        }),
        scope="tool_execution",
        decision="approved",
        proposer_id="agent",
        approver_id="human",
    )
    raw = (tmp_path / "assistant.db").read_bytes()
    serialized = json.dumps(receipt)
    assert b"/Users/example" not in raw
    assert fake_secret.encode() not in raw
    assert b"private full conversation" not in raw
    assert "/Users/example" not in serialized
    assert fake_secret not in serialized
    assert receipt["privacy"] == {
        "subject_payload_stored": False,
        "credentials_included": False,
        "absolute_paths_included": False,
        "raw_transcripts_included": False,
    }
    with pytest.raises(ApprovalReceiptError):
        store.record(
            subject=subject(),
            scope="tool_execution",
            decision="approved",
            proposer_id="agent at /Users/example/private",
            approver_id="human",
        )


def test_legacy_database_migrates_additively_without_losing_existing_rows(tmp_path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE legacy_user_data (id TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO legacy_user_data VALUES ('keep-me', 'preserved')")

    service = PersistenceService(str(db_path))
    receipt = service.record_approval_receipt(
        subject_type="tool_call",
        subject_id="legacy-migration-check",
        subject_payload={"tool_name": "quality_check"},
        scope="tool_execution",
        decision="approved",
        proposer_id="agent",
        approver_id="human",
    )

    assert receipt["integrity_status"] == "verified"
    assert receipt["receipt_integrity_status"] == "verified"
    assert receipt["chain_integrity_status"] == "verified"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT value FROM legacy_user_data WHERE id = 'keep-me'").fetchone()[0] == "preserved"
        assert conn.execute("SELECT COUNT(*) FROM approval_receipts").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_receipt_api_lists_gets_and_verifies_without_private_payload(monkeypatch, tmp_path):
    import across_agents_assistant.api_server as api_server

    service = PersistenceService(str(tmp_path / "api.db"))
    receipt = service.record_approval_receipt(
        subject_type="tool_call",
        subject_id="api-request",
        subject_payload={"path": "/Users/example/private", "tool_name": "quality_check"},
        scope="tool_execution",
        decision="approved",
        proposer_id="agent",
        approver_id="human",
    )
    monkeypatch.setattr(api_server, "persistence", service)

    listing = await api_server.list_approval_receipts()
    loaded = await api_server.get_approval_receipt(receipt["receipt_id"])
    verified = await api_server.verify_approval_receipt_chain()

    assert listing["total"] == 1
    assert loaded["receipt_id"] == receipt["receipt_id"]
    assert loaded["integrity_status"] == "verified"
    assert verified["integrity_status"] == "verified"
    assert "/Users/example" not in json.dumps({"listing": listing, "loaded": loaded, "verified": verified})


@pytest.mark.asyncio
async def test_replay_approval_is_bound_to_snapshot_hash_and_requires_separate_actors(monkeypatch, tmp_path):
    import across_agents_assistant.api_server as api_server

    service = PersistenceService(str(tmp_path / "replay.db"))
    monkeypatch.setattr(api_server, "persistence", service)
    snapshot_sha256 = "a" * 64

    receipt = await api_server.record_replay_approval_receipt(api_server.ReplayApprovalDecision(
        source_snapshot_sha256=snapshot_sha256,
        proposer_id="agent-planner",
        approver_id="human-reviewer",
        decision="approved",
        request_id="replay-request-1",
    ))

    assert receipt["subject_sha256"] == snapshot_sha256
    assert receipt["scope"] == "replay_external_side_effects"
    assert receipt["integrity_status"] == "verified"
    assert receipt["proposer_id"] != receipt["approver_id"]

    with pytest.raises(api_server.HTTPException) as raised:
        await api_server.record_replay_approval_receipt(api_server.ReplayApprovalDecision(
            source_snapshot_sha256=snapshot_sha256,
            proposer_id="same-actor",
            approver_id="same-actor",
        ))
    assert raised.value.status_code == 422
