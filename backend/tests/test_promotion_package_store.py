from __future__ import annotations

from copy import deepcopy
import json
import sqlite3

import pytest

from across_agents_assistant.persistence.promotion_package_store import (
    PromotionPackageStore,
    PromotionPackageStoreError,
)
from across_agents_assistant.persistence.service import PersistenceService


def promotion_document() -> dict[str, object]:
    return {
        "schema_version": "across-promotion-package/1.0",
        "status": "ready_for_human_approval",
        "identities": {
            "run_id": "run-batch-5",
            "spec_id": "spec-repo-quality",
            "candidate_id": "candidate-batch-5",
            "task_ids": ["task-alpha", "task-zeta"],
            "plugins": [
                {"plugin_id": "across-autopilot", "version": "0.5.3"},
                {"plugin_id": "across-context", "version": "0.11.0"},
                {"plugin_id": "across-orchestrator", "version": "0.10.7"},
            ],
        },
        "checks": ["candidate_review_ready", "task_set_complete"],
        "policy": {
            "human_approval_required": True,
            "approval_scope": "release_promotion",
        },
    }


def test_package_survives_restart_and_identical_insertion_is_idempotent(tmp_path):
    db_path = str(tmp_path / "promotion.db")
    document = promotion_document()
    first_store = PromotionPackageStore(db_path)

    first = first_store.put(document)
    repeated = first_store.put(deepcopy(document))
    restarted = PromotionPackageStore(db_path)
    loaded = restarted.get(first["package_id"])

    assert repeated == first
    assert loaded == first
    assert loaded["integrity_status"] == "verified"
    assert loaded["package_id"] == f"promotion-{loaded['package_sha256']}"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM promotion_packages").fetchone()[0] == 1


def test_distinct_canonical_package_bytes_receive_distinct_ids(tmp_path):
    store = PromotionPackageStore(str(tmp_path / "distinct.db"))
    first_document = promotion_document()
    second_document = deepcopy(first_document)
    second_document["checks"] = [*second_document["checks"], "release_ready"]

    first = store.put(first_document)
    second = store.put(second_document)

    assert first["package_id"] != second["package_id"]
    assert first["package_sha256"] != second["package_sha256"]


def test_store_exposes_no_update_or_delete_mutation_api(tmp_path):
    store = PromotionPackageStore(str(tmp_path / "append-only.db"))

    assert not hasattr(store, "update")
    assert not hasattr(store, "delete")
    assert not hasattr(store, "replace")


def test_payload_json_tampering_is_detected_and_cannot_be_repaired_by_put(tmp_path):
    db_path = str(tmp_path / "payload-tamper.db")
    store = PromotionPackageStore(db_path)
    record = store.put(promotion_document())
    with sqlite3.connect(db_path) as conn:
        payload = json.loads(conn.execute(
            "SELECT payload_json FROM promotion_packages WHERE package_id = ?",
            (record["package_id"],),
        ).fetchone()[0])
        payload["status"] = "authorized"
        conn.execute(
            "UPDATE promotion_packages SET payload_json = ? WHERE package_id = ?",
            (json.dumps(payload, sort_keys=True), record["package_id"]),
        )

    assert store.get(record["package_id"])["integrity_status"] == "tampered"
    with pytest.raises(PromotionPackageStoreError, match="existing promotion package differs"):
        store.put(promotion_document())


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("run_id", "run-other"),
        ("spec_id", "spec-other"),
        ("candidate_id", "candidate-other"),
        ("task_ids_json", '["task-other"]'),
        ("plugin_ids_json", '["across-context"]'),
        ("package_sha256", "f" * 64),
    ],
)
def test_semantic_column_tampering_is_detected(tmp_path, column, value):
    db_path = str(tmp_path / f"semantic-{column}.db")
    store = PromotionPackageStore(db_path)
    record = store.put(promotion_document())
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"UPDATE promotion_packages SET {column} = ? WHERE package_id = ?",
            (value, record["package_id"]),
        )

    assert store.get(record["package_id"])["integrity_status"] == "tampered"


def test_persistence_service_wires_the_shared_package_store(tmp_path):
    service = PersistenceService(str(tmp_path / "service.db"))

    stored = service.promotion_packages.put(promotion_document())

    assert service.promotion_packages.get(stored["package_id"]) == stored
