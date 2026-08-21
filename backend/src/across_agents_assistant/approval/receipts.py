from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from contextlib import contextmanager
import hashlib
import json
import re
import sqlite3
import time
import uuid

from ..promotion_package import package_sha256


APPROVAL_RECEIPT_SCHEMA = "across-approval-receipt/1.0"
APPROVAL_CHAIN_SCHEMA = "across-approval-receipt-chain/1.0"
SENSITIVE_SCOPES = {"workspace_promotion", "release", "release_promotion", "replay_external_side_effects"}


class ApprovalReceiptError(ValueError):
    pass


@dataclass(frozen=True)
class ApprovalReceiptSubject:
    subject_type: str
    subject_id: str
    payload: dict[str, Any]
    subject_sha256: str | None = None


class ApprovalReceiptStore:
    """Append-only, hash-chained approval decision receipts in the AAA database."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_schema()

    def record(
        self,
        *,
        subject: ApprovalReceiptSubject,
        scope: str,
        decision: str,
        proposer_id: str,
        approver_id: str,
        risk_level: str = "unknown",
        request_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        with self._connection(write=True) as conn:
            return self._record_in_connection(
                conn,
                subject=subject,
                scope=scope,
                decision=decision,
                proposer_id=proposer_id,
                approver_id=approver_id,
                risk_level=risk_level,
                request_id=request_id,
                idempotency_key=idempotency_key,
            )

    def record_promotion_decision(
        self,
        *,
        package_id: str,
        expected_package_sha256: str,
        decision: str,
        approver_id: str,
        risk_level: str = "release_promotion",
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Verify package and full chain, then append under one write lock."""

        from ..persistence.promotion_package_store import (
            PromotionPackageStoreError,
            load_verified_promotion_package_record,
        )

        with self._connection(write=True) as conn:
            try:
                package = load_verified_promotion_package_record(conn, package_id)
            except PromotionPackageStoreError as exc:
                raise ApprovalReceiptError("promotion package integrity verification failed") from exc
            expected_digest = _sha256_digest(
                expected_package_sha256,
                "expected_package_sha256",
            )
            if package["package_sha256"] != expected_digest:
                raise ApprovalReceiptError("expected promotion package hash does not match")
            if self._chain_failures(conn):
                raise ApprovalReceiptError("approval receipt history is tampered")
            document = package.get("document")
            identities = document.get("identities") if isinstance(document, Mapping) else None
            run_id = identities.get("run_id") if isinstance(identities, Mapping) else None
            if type(run_id) is not str or not run_id:
                raise ApprovalReceiptError("promotion package run binding is invalid")
            self._record_in_connection(
                conn,
                subject=ApprovalReceiptSubject(
                    subject_type="promotion_package",
                    subject_id=package_id,
                    payload={},
                    subject_sha256=package["package_sha256"],
                ),
                scope="release_promotion",
                decision=decision,
                proposer_id=f"autopilot-run:{run_id}",
                approver_id=approver_id,
                risk_level=risk_level,
                idempotency_key=idempotency_key,
            )
            chain = self._verify_chain_in_connection(conn)
            if chain["integrity_status"] != "verified":
                raise ApprovalReceiptError("approval receipt history is tampered")
            latest = self._latest_for_subject_in_connection(
                conn,
                scope="release_promotion",
                subject_type="promotion_package",
                subject_id=package_id,
                subject_sha256=package["package_sha256"],
            )
            if latest is None:
                raise ApprovalReceiptError("promotion decision is missing after append")
            return {
                "package": package,
                "approval": latest,
                "chain": chain,
            }

    def _record_in_connection(
        self,
        conn: sqlite3.Connection,
        *,
        subject: ApprovalReceiptSubject,
        scope: str,
        decision: str,
        proposer_id: str,
        approver_id: str,
        risk_level: str = "unknown",
        request_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        clean_scope = _identifier(scope, "scope")
        clean_decision = _decision(decision)
        proposer = _actor(proposer_id, "proposer_id")
        approver = _actor(approver_id, "approver_id")
        subject_type = _identifier(subject.subject_type, "subject_type")
        if (
            clean_scope in SENSITIVE_SCOPES
            and proposer == approver
            and (clean_decision == "approved" or subject_type == "promotion_package")
        ):
            raise ApprovalReceiptError("promotion, release, and external-side-effect approval require separate proposer and approver identities")
        subject_id_hash = _sha256_text(_bounded_text(subject.subject_id, 500))
        subject_sha256 = (
            _sha256_digest(subject.subject_sha256, "subject_sha256")
            if subject.subject_sha256
            else _sha256_json(_secret_free_subject(subject.payload))
        )
        idempotency_token = _bounded_text(idempotency_key or request_id or "", 500)
        dedupe_material = {
            "scope": clean_scope,
            "decision": clean_decision,
            "proposer_id": proposer,
            "approver_id": approver,
            "subject_type": subject_type,
            "subject_id_sha256": subject_id_hash,
            "subject_sha256": subject_sha256,
            "idempotency_key": idempotency_token,
        }
        if not idempotency_token:
            dedupe_material["append_nonce"] = uuid.uuid4().hex
        dedupe_key = _sha256_json(dedupe_material)
        if idempotency_token:
            existing = conn.execute(
                "SELECT * FROM approval_receipts WHERE dedupe_key = ?",
                (dedupe_key,),
            ).fetchone()
            if existing:
                status = self._verify_row(conn, existing)
                if status != "verified":
                    raise ApprovalReceiptError("approval receipt history is tampered")
                return self._public(existing, integrity_status=status)
            candidates = conn.execute(
                """SELECT * FROM approval_receipts
                   WHERE scope = ? AND subject_type = ?
                     AND subject_id_sha256 = ? AND subject_sha256 = ?
                     AND decision = ? AND proposer_id = ? AND approver_id = ?""",
                (
                    clean_scope,
                    subject_type,
                    subject_id_hash,
                    subject_sha256,
                    clean_decision,
                    proposer,
                    approver,
                ),
            ).fetchall()
            if any(self._verify_row(conn, candidate) != "verified" for candidate in candidates):
                raise ApprovalReceiptError("approval receipt history is tampered")

        previous = conn.execute(
            "SELECT receipt_id, receipt_hash FROM approval_receipts ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = int(conn.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM approval_receipts").fetchone()[0])
        created_at = time.time()
        receipt_id = f"approval-{uuid.uuid4().hex}"
        payload = {
            "schema_version": APPROVAL_RECEIPT_SCHEMA,
            "receipt_id": receipt_id,
            "sequence": sequence,
            "dedupe_key": dedupe_key,
            "request_id_sha256": _sha256_text(_bounded_text(request_id or "", 500)) if request_id else None,
            "subject_type": subject_type,
            "subject_id_sha256": subject_id_hash,
            "subject_sha256": subject_sha256,
            "scope": clean_scope,
            "decision": clean_decision,
            "proposer_id": proposer,
            "approver_id": approver,
            "risk_level": _bounded_text(risk_level, 40) or "unknown",
            "previous_receipt_id": previous["receipt_id"] if previous else None,
            "previous_hash": previous["receipt_hash"] if previous else "0" * 64,
            "created_at": created_at,
            "privacy": {
                "subject_payload_stored": False,
                "credentials_included": False,
                "absolute_paths_included": False,
                "raw_transcripts_included": False,
            },
        }
        receipt_hash = _sha256_json(payload)
        conn.execute(
            """INSERT INTO approval_receipts
               (receipt_id, sequence, dedupe_key, subject_type, subject_id_sha256,
                subject_sha256, scope, decision, proposer_id, approver_id, risk_level,
                previous_receipt_id, previous_hash, receipt_hash, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                receipt_id, sequence, dedupe_key, subject_type, subject_id_hash,
                subject_sha256, clean_scope, clean_decision, proposer, approver,
                payload["risk_level"], payload["previous_receipt_id"], payload["previous_hash"],
                receipt_hash, _canonical(payload), created_at,
            ),
        )
        conn.execute(
            "UPDATE approval_receipt_chain_state SET receipt_count = ?, chain_tip = ? WHERE id = 1",
            (sequence, receipt_hash),
        )
        row = conn.execute("SELECT * FROM approval_receipts WHERE receipt_id = ?", (receipt_id,)).fetchone()
        return self._public(row, integrity_status="verified")

    def get(self, receipt_id: str) -> dict[str, Any]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM approval_receipts WHERE receipt_id = ?", (receipt_id,)).fetchone()
            if not row:
                raise KeyError(receipt_id)
            return self._public(row, integrity_status=self._verify_row(conn, row))

    def latest_for_subject(
        self,
        *,
        scope: str,
        subject_type: str,
        subject_id: str,
        subject_sha256: str,
    ) -> dict[str, Any] | None:
        with self._connection() as conn:
            return self._latest_for_subject_in_connection(
                conn,
                scope=scope,
                subject_type=subject_type,
                subject_id=subject_id,
                subject_sha256=subject_sha256,
            )

    def _latest_for_subject_in_connection(
        self,
        conn: sqlite3.Connection,
        *,
        scope: str,
        subject_type: str,
        subject_id: str,
        subject_sha256: str,
    ) -> dict[str, Any] | None:
        clean_scope = _identifier(scope, "scope")
        clean_subject_type = _identifier(subject_type, "subject_type")
        subject_id_hash = _sha256_text(_bounded_text(subject_id, 500))
        clean_subject_sha256 = _sha256_digest(subject_sha256, "subject_sha256")
        row = conn.execute(
            """SELECT * FROM approval_receipts
               WHERE scope = ? AND subject_type = ?
                 AND subject_id_sha256 = ? AND subject_sha256 = ?
               ORDER BY sequence DESC LIMIT 1""",
            (clean_scope, clean_subject_type, subject_id_hash, clean_subject_sha256),
        ).fetchone()
        if row is None:
            return None
        return self._public(row, integrity_status=self._verify_row(conn, row))

    def list(self, *, limit: int = 100, offset: int = 0, scope: str | None = None) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 500))
        safe_offset = max(0, int(offset))
        where = "WHERE scope = ?" if scope else ""
        params: list[Any] = [scope] if scope else []
        with self._connection() as conn:
            total = int(conn.execute(f"SELECT COUNT(*) FROM approval_receipts {where}", params).fetchone()[0])
            rows = conn.execute(
                f"SELECT * FROM approval_receipts {where} ORDER BY sequence DESC LIMIT ? OFFSET ?",
                [*params, safe_limit, safe_offset],
            ).fetchall()
            receipts = [self._public(row, integrity_status=self._verify_row(conn, row)) for row in rows]
            chain_failures = self._chain_failures(conn)
        page_status = "verified" if all(item["integrity_status"] == "verified" for item in receipts) else "tampered"
        chain_status = "verified" if not chain_failures else "tampered"
        return {
            "schema_version": APPROVAL_CHAIN_SCHEMA,
            "total": total,
            "limit": safe_limit,
            "offset": safe_offset,
            "receipts": receipts,
            "page_integrity_status": page_status,
            "chain_integrity_status": chain_status,
            "integrity_status": chain_status,
        }

    def verify_chain(self) -> dict[str, Any]:
        with self._connection() as conn:
            return self._verify_chain_in_connection(conn)

    def _verify_chain_in_connection(self, conn: sqlite3.Connection) -> dict[str, Any]:
        rows = conn.execute("SELECT * FROM approval_receipts ORDER BY sequence ASC").fetchall()
        failures = self._chain_failures(conn, rows=rows)
        anchor = conn.execute(
            "SELECT receipt_count, chain_tip FROM approval_receipt_chain_state WHERE id = 1"
        ).fetchone()
        observed_tip = rows[-1]["receipt_hash"] if rows else "0" * 64
        return {
            "schema_version": APPROVAL_CHAIN_SCHEMA,
            "receipt_count": len(rows),
            "integrity_status": "verified" if not failures else "tampered",
            "failures": failures,
            "chain_tip": anchor["chain_tip"] if anchor else observed_tip,
            "observed_chain_tip": observed_tip,
            "receipt_anchors": [_receipt_anchor(row) for row in rows],
        }

    def _verify_row(self, conn: sqlite3.Connection, row: sqlite3.Row) -> str:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            return "tampered"
        if _sha256_json(payload) != row["receipt_hash"]:
            return "tampered"
        if "dedupe_key" in payload and payload.get("dedupe_key") != row["dedupe_key"]:
            return "tampered"
        payload_columns = {
            "receipt_id": "receipt_id",
            "sequence": "sequence",
            "subject_type": "subject_type",
            "subject_id_sha256": "subject_id_sha256",
            "subject_sha256": "subject_sha256",
            "scope": "scope",
            "decision": "decision",
            "proposer_id": "proposer_id",
            "approver_id": "approver_id",
            "risk_level": "risk_level",
            "previous_receipt_id": "previous_receipt_id",
            "previous_hash": "previous_hash",
            "created_at": "created_at",
        }
        if any(payload.get(payload_key) != row[column] for payload_key, column in payload_columns.items()):
            return "tampered"
        previous_id = row["previous_receipt_id"]
        if previous_id:
            previous = conn.execute(
                "SELECT receipt_hash, sequence FROM approval_receipts WHERE receipt_id = ?",
                (previous_id,),
            ).fetchone()
            if (
                not previous
                or previous["receipt_hash"] != row["previous_hash"]
                or int(previous["sequence"]) != int(row["sequence"]) - 1
            ):
                return "tampered"
        elif row["previous_hash"] != "0" * 64 or int(row["sequence"]) != 1:
            return "tampered"
        return "verified"

    def _chain_failures(
        self,
        conn: sqlite3.Connection,
        *,
        rows: list[sqlite3.Row] | None = None,
    ) -> list[dict[str, str]]:
        chain_rows = rows
        if chain_rows is None:
            chain_rows = conn.execute("SELECT * FROM approval_receipts ORDER BY sequence ASC").fetchall()
        failures = []
        for row in chain_rows:
            status = self._verify_row(conn, row)
            if status != "verified":
                failures.append({"receipt_id": row["receipt_id"], "status": status})
        anchor = conn.execute(
            "SELECT receipt_count, chain_tip FROM approval_receipt_chain_state WHERE id = 1"
        ).fetchone()
        observed_tip = chain_rows[-1]["receipt_hash"] if chain_rows else "0" * 64
        if (
            not anchor
            or int(anchor["receipt_count"]) != len(chain_rows)
            or anchor["chain_tip"] != observed_tip
        ):
            failures.append({"receipt_id": "chain-anchor", "status": "truncated_or_replaced"})
        return failures

    def _public(self, row: sqlite3.Row, *, integrity_status: str) -> dict[str, Any]:
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        public_columns = {
            "receipt_id": row["receipt_id"],
            "sequence": row["sequence"],
            "subject_type": row["subject_type"],
            "subject_id_sha256": row["subject_id_sha256"],
            "subject_sha256": row["subject_sha256"],
            "scope": row["scope"],
            "decision": row["decision"],
            "proposer_id": row["proposer_id"],
            "approver_id": row["approver_id"],
            "risk_level": row["risk_level"],
            "previous_receipt_id": row["previous_receipt_id"],
            "previous_hash": row["previous_hash"],
            "created_at": row["created_at"],
        }
        return {
            **public_columns,
            **payload,
            "receipt_hash": row["receipt_hash"],
            "integrity_status": integrity_status,
        }

    @contextmanager
    def _connection(self, *, write: bool = False):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            if write:
                conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connection(write=True) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS approval_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    sequence INTEGER NOT NULL UNIQUE,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    subject_type TEXT NOT NULL,
                    subject_id_sha256 TEXT NOT NULL,
                    subject_sha256 TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    proposer_id TEXT NOT NULL,
                    approver_id TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    previous_receipt_id TEXT,
                    previous_hash TEXT NOT NULL,
                    receipt_hash TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )"""
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_approval_receipts_scope ON approval_receipts(scope, sequence DESC)")
            conn.execute(
                """CREATE INDEX IF NOT EXISTS idx_approval_receipts_subject_lookup
                   ON approval_receipts(
                       scope, subject_type, subject_id_sha256, subject_sha256, sequence DESC
                   )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS approval_receipt_chain_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    receipt_count INTEGER NOT NULL,
                    chain_tip TEXT NOT NULL
                )"""
            )
            current = conn.execute(
                "SELECT COUNT(*) AS receipt_count FROM approval_receipts"
            ).fetchone()
            if int(current["receipt_count"]) == 0:
                conn.execute(
                    """INSERT OR IGNORE INTO approval_receipt_chain_state
                       (id, receipt_count, chain_tip) VALUES (1, 0, ?)""",
                    ("0" * 64,),
                )


def evaluate_promotion_authorization(
    package_record: Mapping[str, Any],
    decision: Mapping[str, Any] | None,
    chain: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate authorization without mutating the sealed package or receipt chain."""

    package = package_record if isinstance(package_record, Mapping) else {}
    receipt = decision if isinstance(decision, Mapping) else {}
    chain_state = chain if isinstance(chain, Mapping) else {}
    package_id = package.get("package_id") if type(package.get("package_id")) is str else None
    package_digest = (
        package.get("package_sha256")
        if type(package.get("package_sha256")) is str
        else None
    )
    decision_present = bool(receipt)
    subject_binding_matches = bool(
        package_id
        and package_digest
        and receipt.get("scope") == "release_promotion"
        and receipt.get("subject_type") == "promotion_package"
        and receipt.get("subject_id_sha256") == _sha256_text(package_id)
        and receipt.get("subject_sha256") == package_digest
    )
    anchors = chain_state.get("receipt_anchors")
    chain_complete = _chain_projection_verified(chain_state)
    receipt_anchor = _matching_receipt_anchor(anchors, receipt)
    matching_subject_anchors = [
        anchor
        for anchor in anchors
        if isinstance(anchor, Mapping)
        and anchor.get("scope") == receipt.get("scope")
        and anchor.get("subject_type") == receipt.get("subject_type")
        and anchor.get("subject_id_sha256") == receipt.get("subject_id_sha256")
        and anchor.get("subject_sha256") == receipt.get("subject_sha256")
    ] if isinstance(anchors, list) else []
    latest_subject_anchor = (
        max(matching_subject_anchors, key=lambda anchor: anchor["sequence"])
        if matching_subject_anchors
        else None
    )
    checks = {
        "package_integrity_verified": _promotion_package_record_verified(package),
        "decision_present": decision_present,
        "decision_integrity_verified": _public_receipt_verified(receipt),
        "decision_approved": receipt.get("decision") == "approved",
        "subject_binding_matches": subject_binding_matches,
        "decision_bound_to_chain": bool(chain_complete and receipt_anchor),
        "latest_subject_decision": bool(
            receipt_anchor
            and latest_subject_anchor
            and receipt_anchor.get("receipt_id") == latest_subject_anchor.get("receipt_id")
            and receipt_anchor.get("receipt_hash") == latest_subject_anchor.get("receipt_hash")
        ),
        "separate_actors": bool(
            decision_present
            and receipt.get("proposer_id")
            and receipt.get("approver_id")
            and receipt.get("proposer_id") != receipt.get("approver_id")
        ),
        "chain_integrity_verified": chain_complete,
    }
    authorized = all(checks.values())
    return {
        "schema_version": "across-promotion-authorization/1.0",
        "package_id": package_id,
        "package_sha256": package_digest,
        "decision_receipt_id": receipt.get("receipt_id") if decision_present else None,
        "status": "authorized" if authorized else "not_authorized",
        "authorized": authorized,
        "checks": checks,
    }


def _promotion_package_record_verified(package: Mapping[str, Any]) -> bool:
    document = package.get("document")
    digest = package.get("package_sha256")
    package_id = package.get("package_id")
    if (
        package.get("integrity_status") != "verified"
        or not isinstance(document, Mapping)
        or type(digest) is not str
        or type(package_id) is not str
    ):
        return False
    try:
        return package_sha256(document) == digest and package_id == f"promotion-{digest}"
    except ValueError:
        return False


def _public_receipt_verified(receipt: Mapping[str, Any]) -> bool:
    if receipt.get("integrity_status") != "verified":
        return False
    payload = {
        key: value
        for key, value in receipt.items()
        if key not in {"receipt_hash", "integrity_status"}
    }
    return _sha256_json(payload) == receipt.get("receipt_hash")


def _receipt_anchor(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "receipt_id": row["receipt_id"],
        "sequence": row["sequence"],
        "receipt_hash": row["receipt_hash"],
        "scope": row["scope"],
        "subject_type": row["subject_type"],
        "subject_id_sha256": row["subject_id_sha256"],
        "subject_sha256": row["subject_sha256"],
    }


def _chain_projection_verified(chain: Mapping[str, Any]) -> bool:
    anchors = chain.get("receipt_anchors")
    receipt_count = chain.get("receipt_count")
    if (
        chain.get("integrity_status") != "verified"
        or chain.get("failures") != []
        or type(receipt_count) is not int
        or not isinstance(anchors, list)
        or receipt_count != len(anchors)
    ):
        return False
    for sequence, anchor in enumerate(anchors, start=1):
        if (
            not isinstance(anchor, Mapping)
            or anchor.get("sequence") != sequence
            or type(anchor.get("receipt_id")) is not str
            or type(anchor.get("receipt_hash")) is not str
            or type(anchor.get("scope")) is not str
            or type(anchor.get("subject_type")) is not str
            or type(anchor.get("subject_id_sha256")) is not str
            or type(anchor.get("subject_sha256")) is not str
        ):
            return False
    observed_tip = anchors[-1]["receipt_hash"] if anchors else "0" * 64
    return (
        chain.get("observed_chain_tip") == observed_tip
        and chain.get("chain_tip") == observed_tip
    )


def _matching_receipt_anchor(
    anchors: Any,
    receipt: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    if not isinstance(anchors, list):
        return None
    for anchor in anchors:
        if (
            isinstance(anchor, Mapping)
            and anchor.get("receipt_id") == receipt.get("receipt_id")
            and anchor.get("sequence") == receipt.get("sequence")
            and anchor.get("receipt_hash") == receipt.get("receipt_hash")
        ):
            return anchor
    return None


def _secret_free_subject(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key in sorted(value):
            clean_key = str(key)
            lowered = clean_key.lower()
            if any(token in lowered for token in ("secret", "token", "password", "credential", "api_key", "transcript", "messages")):
                result[clean_key] = "[REDACTED]"
            else:
                result[clean_key] = _secret_free_subject(value[key])
        return result
    if isinstance(value, (list, tuple)):
        return [_secret_free_subject(item) for item in value]
    if isinstance(value, str):
        if value.startswith("/") or re.match(r"^[A-Za-z]:\\", value):
            return {"local_path_sha256": _sha256_text(value)}
        if re.search(r"\b(sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{16,})\b", value):
            return "[REDACTED]"
        return value[:2000]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:2000]


def _identifier(value: str, name: str) -> str:
    clean = _bounded_text(value, 120).lower()
    if not clean or not re.fullmatch(r"[a-z0-9][a-z0-9_.:-]*", clean):
        raise ApprovalReceiptError(f"{name} must be a stable identifier")
    return clean


def _actor(value: str, name: str) -> str:
    clean = _bounded_text(value, 200)
    contains_path = bool(re.search(
        r"(?:^|\s)(?:/(?:Users|home|tmp|var|private|Volumes|opt|etc|usr|Applications)(?:/|$)|[A-Za-z]:\\)",
        clean,
    ))
    contains_secret = bool(re.search(
        r"\b(sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{16,})\b",
        clean,
    ))
    if not clean or "\x00" in clean or contains_path or contains_secret:
        raise ApprovalReceiptError(f"{name} is required")
    return clean


def _decision(value: str) -> str:
    clean = _bounded_text(value, 40).lower()
    aliases = {"approve": "approved", "always_allow": "approved", "reject": "rejected"}
    clean = aliases.get(clean, clean)
    if clean not in {"approved", "rejected"}:
        raise ApprovalReceiptError("decision must be approved or rejected")
    return clean


def _sha256_digest(value: str, name: str) -> str:
    clean = _bounded_text(value, 64).lower()
    if not re.fullmatch(r"[a-f0-9]{64}", clean):
        raise ApprovalReceiptError(f"{name} must be a lowercase SHA-256 digest")
    return clean


def _bounded_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
