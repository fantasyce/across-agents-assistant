from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from typing import Any, Mapping

from ..goal_contract.protocol import normalize_goal_change_proposal, normalize_goal_contract
from .database import Database


class GoalContractStoreError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class GoalContractStore:
    def __init__(self, db: Database):
        self.db = db

    def create_revision(
        self,
        contract: Mapping[str, Any],
        *,
        expected_revision: int,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        normalized = normalize_goal_contract(contract)
        payload_json = _canonical(normalized)
        payload_sha256 = _sha256(payload_json)
        key = _optional_key(idempotency_key)
        with self.db.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if key:
                replay = conn.execute(
                    "SELECT * FROM goal_contract_revisions WHERE idempotency_key = ?", (key,)
                ).fetchone()
                if replay:
                    if replay["payload_sha256"] != payload_sha256 or replay["expected_revision"] != expected_revision:
                        raise GoalContractStoreError(
                            "goal_idempotency_conflict",
                            "goal revision idempotency key was reused with different content",
                        )
                    return json.loads(replay["payload_json"])
            current = conn.execute(
                "SELECT MAX(revision) AS revision FROM goal_contract_revisions WHERE goal_id = ?",
                (normalized["goal_id"],),
            ).fetchone()["revision"]
            current_revision = int(current or 0)
            if expected_revision != current_revision:
                raise GoalContractStoreError(
                    "goal_revision_conflict",
                    f"expected_revision {expected_revision} does not match current revision {current_revision}",
                )
            if normalized["revision"] != current_revision + 1:
                raise GoalContractStoreError(
                    "goal_revision_non_monotonic",
                    "goal revision must increment the current revision by one",
                )
            try:
                conn.execute(
                    """INSERT INTO goal_contract_revisions
                       (goal_id, task_id, revision, schema_version, payload_json, payload_sha256,
                        expected_revision, idempotency_key, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        normalized["goal_id"], normalized["task_id"], normalized["revision"],
                        normalized["schema_version"], payload_json, payload_sha256,
                        expected_revision, key, time.time(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise GoalContractStoreError("goal_revision_conflict", "goal revision already exists") from exc
        return normalized

    def get_current(self, task_id: str) -> dict[str, Any] | None:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """SELECT * FROM goal_contract_revisions WHERE task_id = ?
                   ORDER BY revision DESC LIMIT 1""",
                (str(task_id),),
            ).fetchone()
        return _verified_revision(row) if row else None

    def list_revisions(self, goal_id: str) -> list[dict[str, Any]]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM goal_contract_revisions WHERE goal_id = ? ORDER BY revision",
                (str(goal_id),),
            ).fetchall()
        return [_verified_revision(row) for row in rows]

    def save_proposal(
        self, proposal: Mapping[str, Any], *, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        normalized = normalize_goal_change_proposal(proposal)
        payload_json = _canonical(normalized)
        payload_sha256 = _sha256(payload_json)
        key = _optional_key(idempotency_key)
        with self.db.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if key:
                replay = conn.execute(
                    "SELECT * FROM goal_change_proposals WHERE create_idempotency_key = ?", (key,)
                ).fetchone()
                if replay:
                    if replay["payload_sha256"] != payload_sha256:
                        raise GoalContractStoreError(
                            "goal_idempotency_conflict",
                            "proposal idempotency key was reused with different content",
                        )
                    return _public_proposal(replay)
            current = conn.execute(
                "SELECT MAX(revision) AS revision FROM goal_contract_revisions WHERE goal_id = ?",
                (normalized["goal_id"],),
            ).fetchone()["revision"]
            if int(current or 0) != normalized["base_goal_revision"]:
                raise GoalContractStoreError("goal_revision_conflict", "proposal base revision is stale")
            try:
                conn.execute(
                    """INSERT INTO goal_change_proposals
                       (proposal_id, goal_id, base_goal_revision, schema_version, payload_json,
                        payload_sha256, decision_state, create_idempotency_key, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        normalized["proposal_id"], normalized["goal_id"],
                        normalized["base_goal_revision"], normalized["schema_version"],
                        payload_json, payload_sha256, "pending", key, time.time(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise GoalContractStoreError("goal_proposal_conflict", "proposal already exists") from exc
            row = conn.execute(
                "SELECT * FROM goal_change_proposals WHERE proposal_id = ?",
                (normalized["proposal_id"],),
            ).fetchone()
        return _public_proposal(row)

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM goal_change_proposals WHERE proposal_id = ?", (str(proposal_id),)
            ).fetchone()
        return _public_proposal(row) if row else None

    def get_proposal_decision_replay(
        self, proposal_id: str, idempotency_key: str
    ) -> dict[str, Any] | None:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """SELECT * FROM goal_change_proposals
                   WHERE proposal_id = ? AND decision_idempotency_key = ?""",
                (str(proposal_id), str(idempotency_key)),
            ).fetchone()
        return _public_proposal(row) if row else None

    def list_pending_proposals(self, goal_id: str, revision: int) -> list[dict[str, Any]]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """SELECT * FROM goal_change_proposals
                   WHERE goal_id = ? AND base_goal_revision = ? AND decision_state = 'pending'
                   ORDER BY created_at, proposal_id""",
                (str(goal_id), int(revision)),
            ).fetchall()
        return [_public_proposal(row) for row in rows]

    def save_evidence(
        self, binding: Mapping[str, Any], *, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        payload = dict(binding)
        payload_json = _canonical(payload)
        key = _optional_key(idempotency_key)
        with self.db.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if key:
                row = conn.execute(
                    "SELECT * FROM goal_evidence_bindings WHERE idempotency_key = ?", (key,)
                ).fetchone()
                if row:
                    if row["payload_json"] != payload_json:
                        raise GoalContractStoreError(
                            "goal_idempotency_conflict",
                            "evidence idempotency key was reused with different content",
                        )
                    return json.loads(row["payload_json"])
            try:
                conn.execute(
                    """INSERT INTO goal_evidence_bindings
                       (evidence_id, goal_id, goal_revision, task_id, criterion_ids_json,
                        payload_json, trust_state, idempotency_key, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        payload["evidence_id"], payload["goal_id"], payload["goal_revision"],
                        payload["task_id"], _canonical(payload["criterion_ids"]), payload_json,
                        payload["trust_state"], key, time.time(),
                    ),
                )
            except (KeyError, sqlite3.IntegrityError) as exc:
                raise GoalContractStoreError("goal_evidence_conflict", "evidence binding is invalid or already exists") from exc
        return payload

    def list_evidence(self, goal_id: str, revision: int) -> list[dict[str, Any]]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """SELECT payload_json FROM goal_evidence_bindings
                   WHERE goal_id = ? AND goal_revision = ? ORDER BY created_at, evidence_id""",
                (str(goal_id), int(revision)),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def save_review(
        self, review: Mapping[str, Any], *, idempotency_key: str
    ) -> dict[str, Any]:
        payload = dict(review)
        payload_json = _canonical(payload)
        key = _optional_key(idempotency_key)
        with self.db.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            replay = conn.execute(
                "SELECT payload_json FROM goal_reviews WHERE idempotency_key = ?", (key,)
            ).fetchone()
            if replay:
                if replay["payload_json"] != payload_json:
                    raise GoalContractStoreError(
                        "goal_idempotency_conflict", "review idempotency key was reused with different content"
                    )
                return json.loads(replay["payload_json"])
            try:
                conn.execute(
                    """INSERT INTO goal_reviews
                       (review_id, goal_id, goal_revision, criterion_ids_json, payload_json,
                        status, idempotency_key, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        payload["review_id"], payload["goal_id"], payload["goal_revision"],
                        _canonical(payload["criterion_ids"]), payload_json, payload["status"],
                        key, time.time(),
                    ),
                )
            except (KeyError, sqlite3.IntegrityError) as exc:
                raise GoalContractStoreError("goal_review_conflict", "goal review is invalid or already exists") from exc
        return payload

    def list_reviews(self, goal_id: str, revision: int) -> list[dict[str, Any]]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """SELECT payload_json FROM goal_reviews
                   WHERE goal_id = ? AND goal_revision = ? ORDER BY created_at, review_id""",
                (str(goal_id), int(revision)),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def save_invalidation(
        self, event: Mapping[str, Any], *, idempotency_key: str | None = None
    ) -> dict[str, Any]:
        payload = dict(event)
        payload_json = _canonical(payload)
        key = _optional_key(idempotency_key)
        with self.db.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if key:
                row = conn.execute(
                    "SELECT payload_json FROM goal_invalidation_events WHERE idempotency_key = ?", (key,)
                ).fetchone()
                if row:
                    existing = json.loads(row["payload_json"])
                    immutable_existing = {
                        name: value for name, value in existing.items()
                        if name not in {"state", "attempt", "replacement_evidence_ids", "completion_idempotency_key"}
                    }
                    immutable_requested = {
                        name: value for name, value in payload.items()
                        if name not in {"state", "attempt", "replacement_evidence_ids", "completion_idempotency_key"}
                    }
                    if immutable_existing != immutable_requested:
                        raise GoalContractStoreError(
                            "goal_idempotency_conflict",
                            "revalidation idempotency key was reused with different content",
                        )
                    return existing
            try:
                conn.execute(
                    """INSERT INTO goal_invalidation_events
                       (invalidation_id, goal_id, from_revision, to_revision,
                        affected_criterion_ids_json, payload_json, idempotency_key, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        payload["invalidation_id"], payload["goal_id"], payload["from_revision"],
                        payload.get("to_revision"), _canonical(payload["criterion_ids"]),
                        payload_json, key, time.time(),
                    ),
                )
            except (KeyError, sqlite3.IntegrityError) as exc:
                raise GoalContractStoreError("goal_invalidation_conflict", "invalidation event is invalid or already exists") from exc
        return payload

    def list_invalidations(self, goal_id: str, revision: int) -> list[dict[str, Any]]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """SELECT payload_json FROM goal_invalidation_events
                   WHERE goal_id = ? AND from_revision = ? ORDER BY created_at, invalidation_id""",
                (str(goal_id), int(revision)),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def attach_revalidation_attempt(
        self,
        *,
        goal_id: str,
        revision: int,
        criterion_ids: list[str],
        attempt: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        """Durably bind a provider Attempt to matching pending invalidations."""

        selected = set(map(str, criterion_ids))
        attached: list[dict[str, Any]] = []
        with self.db.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """SELECT invalidation_id, payload_json FROM goal_invalidation_events
                   WHERE goal_id = ? AND from_revision = ? ORDER BY created_at, invalidation_id""",
                (str(goal_id), int(revision)),
            ).fetchall()
            for row in rows:
                payload = json.loads(row["payload_json"])
                affected = set(map(str, payload.get("criterion_ids") or ()))
                if payload.get("state") != "pending" or not affected or not affected.issubset(selected):
                    continue
                existing = payload.get("attempt")
                if existing is not None and existing != dict(attempt):
                    raise GoalContractStoreError(
                        "goal_revalidation_conflict",
                        "pending invalidation is already bound to a different Attempt",
                    )
                payload["attempt"] = dict(attempt)
                conn.execute(
                    "UPDATE goal_invalidation_events SET payload_json = ? WHERE invalidation_id = ?",
                    (_canonical(payload), row["invalidation_id"]),
                )
                attached.append(payload)
        if not attached:
            raise GoalContractStoreError(
                "goal_revalidation_missing", "no matching pending invalidation exists"
            )
        return attached

    def complete_invalidations(
        self,
        *,
        goal_id: str,
        revision: int,
        criterion_ids: list[str],
        attempt: Mapping[str, Any],
        evidence_id: str,
        completion_idempotency_key: str,
    ) -> list[dict[str, Any]]:
        """Complete every pending invalidation covered by one verified attempt."""
        selected = set(map(str, criterion_ids))
        completed: list[dict[str, Any]] = []
        with self.db.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """SELECT invalidation_id, payload_json FROM goal_invalidation_events
                   WHERE goal_id = ? AND from_revision = ? ORDER BY created_at, invalidation_id""",
                (str(goal_id), int(revision)),
            ).fetchall()
            for row in rows:
                payload = json.loads(row["payload_json"])
                affected = set(map(str, payload.get("criterion_ids") or ()))
                if payload.get("state") != "pending" or not affected or not affected.issubset(selected):
                    continue
                payload["state"] = "completed"
                payload["attempt"] = dict(attempt)
                payload["replacement_evidence_ids"] = [str(evidence_id)]
                payload["completion_idempotency_key"] = str(completion_idempotency_key)
                payload_json = _canonical(payload)
                conn.execute(
                    "UPDATE goal_invalidation_events SET payload_json = ? WHERE invalidation_id = ?",
                    (payload_json, row["invalidation_id"]),
                )
                completed.append(payload)
        return completed

    def decide_proposal(
        self,
        proposal_id: str,
        *,
        decision: str,
        expected_revision: int,
        decision_receipt: Mapping[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if decision not in {"accepted", "partially_accepted", "rejected", "superseded"}:
            raise GoalContractStoreError("goal_decision_invalid", "proposal decision is invalid")
        receipt_json = _canonical(dict(decision_receipt))
        request_sha256 = _sha256(_canonical({"decision": decision, "receipt": dict(decision_receipt)}))
        key = _optional_key(idempotency_key)
        with self.db.get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM goal_change_proposals WHERE proposal_id = ?", (str(proposal_id),)
            ).fetchone()
            if not row:
                raise KeyError(proposal_id)
            if row["base_goal_revision"] != expected_revision:
                raise GoalContractStoreError("goal_revision_conflict", "proposal base revision does not match expected revision")
            if key and row["decision_idempotency_key"] == key:
                if row["decision_request_sha256"] != request_sha256:
                    raise GoalContractStoreError(
                        "goal_idempotency_conflict",
                        "proposal decision idempotency key was reused with different content",
                    )
                return _public_proposal(row)
            if row["decision_state"] != "pending":
                raise GoalContractStoreError("goal_proposal_already_decided", "proposal is already decided")
            conn.execute(
                """UPDATE goal_change_proposals
                   SET decision_state = ?, decision_receipt_json = ?, decision_idempotency_key = ?,
                       decision_request_sha256 = ?, decided_at = ? WHERE proposal_id = ?""",
                (decision, receipt_json, key, request_sha256, time.time(), proposal_id),
            )
            row = conn.execute(
                "SELECT * FROM goal_change_proposals WHERE proposal_id = ?", (str(proposal_id),)
            ).fetchone()
        return _public_proposal(row)


def _verified_revision(row: sqlite3.Row) -> dict[str, Any]:
    payload = json.loads(row["payload_json"])
    if _canonical(payload) != row["payload_json"] or _sha256(row["payload_json"]) != row["payload_sha256"]:
        raise GoalContractStoreError("goal_revision_tampered", "goal revision integrity verification failed")
    return normalize_goal_contract(payload)


def _public_proposal(row: sqlite3.Row) -> dict[str, Any]:
    payload = json.loads(row["payload_json"])
    if _canonical(payload) != row["payload_json"] or _sha256(row["payload_json"]) != row["payload_sha256"]:
        raise GoalContractStoreError("goal_proposal_tampered", "goal proposal integrity verification failed")
    payload["decision_state"] = row["decision_state"]
    if row["decision_receipt_json"]:
        payload["decision_receipt"] = json.loads(row["decision_receipt_json"])
    return payload


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _optional_key(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None
