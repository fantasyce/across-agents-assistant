from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Mapping

from ..promotion_package import package_sha256


PROMOTION_PACKAGE_SCHEMA = "across-promotion-package/1.0"


class PromotionPackageStoreError(ValueError):
    pass


class PromotionPackageStore:
    """Append-only persistence for canonical, content-addressed promotion packages."""

    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def put(self, document: Mapping[str, Any]) -> dict[str, Any]:
        payload_json = _canonical(document)
        normalized = json.loads(payload_json)
        semantics = _semantics(normalized)
        digest = package_sha256(normalized)
        package_id = f"promotion-{digest}"
        created_at = time.time()
        candidate = {
            "package_id": package_id,
            "package_sha256": digest,
            **semantics,
            "payload_json": payload_json,
            "created_at": created_at,
        }
        with self._connection(write=True) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO promotion_packages
                   (package_id, package_sha256, run_id, spec_id, candidate_id,
                    task_ids_json, plugin_ids_json, payload_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                tuple(candidate[column] for column in _STORED_COLUMNS),
            )
            row = conn.execute(
                "SELECT * FROM promotion_packages WHERE package_id = ?",
                (package_id,),
            ).fetchone()
            if row is None or any(row[column] != candidate[column] for column in _CONTENT_COLUMNS):
                raise PromotionPackageStoreError("existing promotion package differs from canonical bytes")
            return self._public(row, integrity_status=self._verify_row(row))

    def get(self, package_id: str) -> dict[str, Any]:
        with self._connection() as conn:
            return load_verified_promotion_package_record(
                conn,
                package_id,
                allow_tampered=True,
            )

    def _verify_row(self, row: sqlite3.Row) -> str:
        return _verify_promotion_package_row(row)

    @staticmethod
    def _public(row: sqlite3.Row, *, integrity_status: str) -> dict[str, Any]:
        return _public_promotion_package_row(row, integrity_status=integrity_status)

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
                """CREATE TABLE IF NOT EXISTS promotion_packages (
                    package_id TEXT PRIMARY KEY,
                    package_sha256 TEXT NOT NULL UNIQUE,
                    run_id TEXT NOT NULL,
                    spec_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    task_ids_json TEXT NOT NULL,
                    plugin_ids_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )"""
            )


_STORED_COLUMNS = (
    "package_id",
    "package_sha256",
    "run_id",
    "spec_id",
    "candidate_id",
    "task_ids_json",
    "plugin_ids_json",
    "payload_json",
    "created_at",
)
_CONTENT_COLUMNS = _STORED_COLUMNS[:-1]


def load_verified_promotion_package_record(
    conn: sqlite3.Connection,
    package_id: str,
    *,
    allow_tampered: bool = False,
) -> dict[str, Any]:
    """Load and verify a package using the caller's active SQLite transaction."""

    row = conn.execute(
        "SELECT * FROM promotion_packages WHERE package_id = ?",
        (str(package_id),),
    ).fetchone()
    if row is None:
        raise KeyError(package_id)
    integrity_status = _verify_promotion_package_row(row)
    if integrity_status != "verified" and not allow_tampered:
        raise PromotionPackageStoreError("promotion package integrity verification failed")
    return _public_promotion_package_row(row, integrity_status=integrity_status)


def _verify_promotion_package_row(row: sqlite3.Row) -> str:
    try:
        document = json.loads(row["payload_json"])
        semantics = _semantics(document)
        digest = package_sha256(document)
        verified = (
            row["payload_json"] == _canonical(document)
            and row["package_id"] == f"promotion-{digest}"
            and row["package_sha256"] == digest
            and all(row[column] == value for column, value in semantics.items())
        )
    except (PromotionPackageStoreError, TypeError, ValueError, json.JSONDecodeError):
        verified = False
    return "verified" if verified else "tampered"


def _public_promotion_package_row(
    row: sqlite3.Row,
    *,
    integrity_status: str,
) -> dict[str, Any]:
    try:
        document = json.loads(row["payload_json"])
    except (TypeError, json.JSONDecodeError):
        document = None
    return {
        "package_id": row["package_id"],
        "package_sha256": row["package_sha256"],
        "document": document,
        "created_at": row["created_at"],
        "integrity_status": integrity_status,
    }


def _semantics(document: Any) -> dict[str, str]:
    if not isinstance(document, dict) or document.get("schema_version") != PROMOTION_PACKAGE_SCHEMA:
        raise PromotionPackageStoreError("promotion package document has an unsupported schema")
    if document.get("status") != "ready_for_human_approval":
        raise PromotionPackageStoreError("promotion package document is not ready for approval")
    identities = document.get("identities")
    if not isinstance(identities, dict):
        raise PromotionPackageStoreError("promotion package identities are required")
    run_id = _identifier(identities.get("run_id"), "run_id")
    spec_id = _identifier(identities.get("spec_id"), "spec_id")
    candidate_id = _identifier(identities.get("candidate_id"), "candidate_id")
    task_ids = identities.get("task_ids")
    plugins = identities.get("plugins")
    if not isinstance(task_ids, list) or not task_ids:
        raise PromotionPackageStoreError("promotion package task identities are required")
    clean_task_ids = sorted({_identifier(item, "task_id") for item in task_ids})
    if len(clean_task_ids) != len(task_ids):
        raise PromotionPackageStoreError("promotion package task identities must be unique")
    if not isinstance(plugins, list) or not plugins:
        raise PromotionPackageStoreError("promotion package plugin identities are required")
    plugin_ids = []
    for item in plugins:
        if not isinstance(item, dict):
            raise PromotionPackageStoreError("promotion package plugin identities are invalid")
        plugin_ids.append(_identifier(item.get("plugin_id"), "plugin_id"))
    clean_plugin_ids = sorted(set(plugin_ids))
    if len(clean_plugin_ids) != len(plugin_ids):
        raise PromotionPackageStoreError("promotion package plugin identities must be unique")
    return {
        "run_id": run_id,
        "spec_id": spec_id,
        "candidate_id": candidate_id,
        "task_ids_json": _canonical(clean_task_ids),
        "plugin_ids_json": _canonical(clean_plugin_ids),
    }


def _identifier(value: Any, name: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise PromotionPackageStoreError(f"promotion package {name} is invalid")
    return value


def _canonical(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        raise PromotionPackageStoreError("promotion package document is invalid") from exc
