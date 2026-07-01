from __future__ import annotations

import hashlib
import hmac
import json
import calendar
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .paths import data_file


TRIGGER_REGISTRY_SCHEMA_VERSION = "across-aaa-autopilot-trigger-registry/1.0"


@dataclass(frozen=True)
class WebhookVerification:
    passed: bool
    reason: str
    delivery_id: str | None = None


class AutopilotTriggerRegistry:
    """AAA-hosted trigger registry for cron, webhook, and daemon wakeups."""

    def __init__(self, path: Path | None = None):
        self.path = path or data_file("autopilot-trigger-registry.json")

    def register(
        self,
        *,
        spec: str,
        trigger_type: str,
        payload: Mapping[str, Any] | None = None,
        schedule: Mapping[str, Any] | None = None,
        webhook: Mapping[str, Any] | None = None,
        daemon: Mapping[str, Any] | None = None,
        enabled: bool = True,
        actor: str = "user",
        source: str = "aaa",
        trigger_id: str | None = None,
    ) -> dict[str, Any]:
        state = self._load()
        now = _now()
        record = {
            "schema_version": "across-aaa-autopilot-trigger-config/1.0",
            "trigger_id": trigger_id or _trigger_id(spec, trigger_type, now),
            "spec": _required_text(spec, "spec"),
            "type": _required_text(trigger_type, "trigger_type"),
            "enabled": bool(enabled),
            "paused": False,
            "payload": dict(payload or {}),
            "schedule": dict(schedule or {}),
            "webhook": _redact_webhook(dict(webhook or {})),
            "daemon": dict(daemon or {}),
            "actor": actor or "user",
            "source": source or "aaa",
            "created_at": now,
            "updated_at": now,
            "last_enqueued_at": None,
            "last_trigger_id": None,
            "last_status": None,
            "last_daemon_signature": None,
            "seen_deliveries": [],
            "enqueue_count": 0,
        }
        secret = (webhook or {}).get("secret") if isinstance(webhook, Mapping) else None
        if secret:
            record["webhook_secret_sha256"] = _sha256(str(secret))
        state["triggers"] = [record, *[item for item in state["triggers"] if item.get("trigger_id") != record["trigger_id"]]]
        self._save(state)
        return record

    def ensure(
        self,
        *,
        spec: str,
        trigger_type: str,
        payload: Mapping[str, Any] | None = None,
        schedule: Mapping[str, Any] | None = None,
        webhook: Mapping[str, Any] | None = None,
        daemon: Mapping[str, Any] | None = None,
        enabled: bool = True,
        actor: str = "user",
        source: str = "aaa",
        trigger_id: str,
    ) -> dict[str, Any]:
        """Create or update a trigger config while preserving run history."""

        state = self._load()
        now = _now()
        try:
            record = self._find(state, trigger_id)
        except KeyError:
            return self.register(
                spec=spec,
                trigger_type=trigger_type,
                payload=payload,
                schedule=schedule,
                webhook=webhook,
                daemon=daemon,
                enabled=enabled,
                actor=actor,
                source=source,
                trigger_id=trigger_id,
            )
        record.update(
            {
                "spec": _required_text(spec, "spec"),
                "type": _required_text(trigger_type, "trigger_type"),
                "enabled": bool(enabled),
                "payload": dict(payload or {}),
                "schedule": dict(schedule or {}),
                "webhook": _redact_webhook(dict(webhook or {})),
                "daemon": dict(daemon or {}),
                "actor": actor or record.get("actor") or "user",
                "source": source or record.get("source") or "aaa",
                "updated_at": now,
            }
        )
        secret = (webhook or {}).get("secret") if isinstance(webhook, Mapping) else None
        if secret:
            record["webhook_secret_sha256"] = _sha256(str(secret))
        self._save(state)
        return record

    def list(self) -> dict[str, Any]:
        return self._load()

    def list_synced(self, queue: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Return trigger configs after syncing known queue terminal status.

        The registry stores a schedule/config view, while Autopilot's trigger
        queue is the source of truth for dispatch completion. Sync only the
        queue item already referenced by ``last_trigger_id`` so a read cannot
        mutate scheduling or claim new work.
        """

        state = self._load()
        changed = self._sync_queue_status(state, queue or {})
        if changed:
            self._save(state)
            return self._load()
        return state

    def set_paused(self, trigger_id: str, paused: bool) -> dict[str, Any]:
        state = self._load()
        record = self._find(state, trigger_id)
        record["paused"] = bool(paused)
        record["updated_at"] = _now()
        self._save(state)
        return record

    def delete(self, trigger_id: str) -> dict[str, Any]:
        state = self._load()
        before = len(state["triggers"])
        state["triggers"] = [item for item in state["triggers"] if item.get("trigger_id") != trigger_id]
        self._save(state)
        return {
            "schema_version": "across-aaa-autopilot-trigger-delete/1.0",
            "trigger_id": trigger_id,
            "deleted": len(state["triggers"]) < before,
        }

    def tick(self, client: Any, *, now: float | None = None) -> dict[str, Any]:
        state = self._load()
        current = float(now if now is not None else time.time())
        enqueued: list[dict[str, Any]] = []
        inspected: list[dict[str, Any]] = []
        for record in state["triggers"]:
            decision = self._due_decision(record, current)
            inspected.append(decision)
            if decision["status"] != "due":
                continue
            result = client.enqueue_trigger(
                record["spec"],
                trigger_type=record["type"],
                payload={**dict(record.get("payload") or {}), **dict(decision.get("payload") or {})},
                idempotency_key=decision["idempotency_key"],
                not_before=decision.get("not_before"),
                source=record.get("source") or "aaa-trigger-registry",
                actor=record.get("actor") or "scheduler",
            )
            record["last_enqueued_at"] = _iso(current)
            record["last_trigger_id"] = result.get("trigger_id")
            record["last_status"] = result.get("status")
            record["enqueue_count"] = int(record.get("enqueue_count") or 0) + (0 if result.get("duplicate") else 1)
            record["updated_at"] = _now()
            if decision.get("daemon_signature"):
                record["last_daemon_signature"] = decision["daemon_signature"]
            enqueued.append(result)
        self._save(state)
        return {
            "schema_version": "across-aaa-autopilot-trigger-tick/1.0",
            "status": "enqueued" if enqueued else "idle",
            "inspected": inspected,
            "enqueued": enqueued,
        }

    def accept_webhook(
        self,
        client: Any,
        *,
        trigger_id: str,
        raw_body: bytes,
        headers: Mapping[str, str],
        payload: Mapping[str, Any] | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        state = self._load()
        record = self._find(state, trigger_id)
        verification = self.verify_webhook(record, raw_body=raw_body, headers=headers, now=now)
        if not verification.passed:
            return {
                "schema_version": "across-aaa-autopilot-webhook-receipt/1.0",
                "status": "rejected",
                "trigger_id": trigger_id,
                "reason": verification.reason,
            }
        delivery_id = verification.delivery_id or _sha256(raw_body.decode("utf-8", errors="replace"))
        result = client.enqueue_trigger(
            record["spec"],
            trigger_type="webhook",
            payload={**dict(record.get("payload") or {}), **dict(payload or {})},
            idempotency_key=f"{trigger_id}:{delivery_id}",
            source=record.get("source") or "aaa-webhook",
            actor=record.get("actor") or "webhook",
        )
        record["seen_deliveries"] = [delivery_id, *[item for item in record.get("seen_deliveries", []) if item != delivery_id]][:200]
        record["last_enqueued_at"] = _now()
        record["last_trigger_id"] = result.get("trigger_id")
        record["last_status"] = result.get("status")
        record["enqueue_count"] = int(record.get("enqueue_count") or 0) + (0 if result.get("duplicate") else 1)
        record["updated_at"] = _now()
        self._save(state)
        return {
            "schema_version": "across-aaa-autopilot-webhook-receipt/1.0",
            "status": "accepted",
            "trigger_id": trigger_id,
            "delivery_id": delivery_id,
            "queued": result,
        }

    def verify_webhook(
        self,
        record: Mapping[str, Any],
        *,
        raw_body: bytes,
        headers: Mapping[str, str],
        now: float | None = None,
    ) -> WebhookVerification:
        if record.get("enabled") is False or record.get("paused") is True:
            return WebhookVerification(False, "trigger is disabled or paused")
        delivery_id = _header(headers, "x-across-delivery") or _header(headers, "x-github-delivery")
        if delivery_id and delivery_id in set(record.get("seen_deliveries") or []):
            return WebhookVerification(False, "duplicate delivery", delivery_id)
        secret_hash = record.get("webhook_secret_sha256")
        if not secret_hash:
            return WebhookVerification(True, "unsigned webhook accepted because no secret is configured", delivery_id)
        secret = _header(headers, "x-across-webhook-secret")
        if _sha256(secret or "") != secret_hash:
            return WebhookVerification(False, "webhook secret mismatch", delivery_id)
        timestamp = _header(headers, "x-across-timestamp")
        if timestamp:
            try:
                skew = abs(float(now if now is not None else time.time()) - float(timestamp))
            except ValueError:
                return WebhookVerification(False, "invalid webhook timestamp", delivery_id)
            tolerance = float((record.get("webhook") or {}).get("timestamp_tolerance_seconds") or 300)
            if skew > tolerance:
                return WebhookVerification(False, "webhook timestamp outside tolerance", delivery_id)
        signature = _header(headers, "x-across-signature")
        if signature:
            expected = "sha256=" + hmac.new(str(secret).encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return WebhookVerification(False, "webhook signature mismatch", delivery_id)
        return WebhookVerification(True, "webhook verified", delivery_id)

    def _due_decision(self, record: Mapping[str, Any], now: float) -> dict[str, Any]:
        trigger_id = record.get("trigger_id")
        if record.get("enabled") is False or record.get("paused") is True:
            return {"trigger_id": trigger_id, "type": record.get("type"), "status": "paused"}
        if record.get("type") == "cron":
            interval = max(0, int((record.get("schedule") or {}).get("interval_seconds") or 0))
            last = _parse_iso(record.get("last_enqueued_at"))
            if last is not None and (interval == 0 or now - last < interval):
                return {"trigger_id": trigger_id, "type": "cron", "status": "not_due", "next_due_at": _iso(last + max(interval, 1))}
            bucket = int(now // max(interval, 1))
            return {
                "trigger_id": trigger_id,
                "type": "cron",
                "status": "due",
                "idempotency_key": f"{trigger_id}:cron:{bucket}",
                "not_before": _iso(now),
            }
        if record.get("type") == "daemon":
            daemon = record.get("daemon") or {}
            watch_path = str(daemon.get("watch_path") or "").strip()
            signature = _path_signature(watch_path) if watch_path else None
            if not signature:
                return {"trigger_id": trigger_id, "type": "daemon", "status": "not_due", "reason": "watch path missing"}
            if signature == record.get("last_daemon_signature"):
                return {"trigger_id": trigger_id, "type": "daemon", "status": "not_due", "daemon_signature": signature}
            if record.get("last_daemon_signature") is None and not daemon.get("fire_on_start"):
                return {"trigger_id": trigger_id, "type": "daemon", "status": "initialized", "daemon_signature": signature}
            return {
                "trigger_id": trigger_id,
                "type": "daemon",
                "status": "due",
                "idempotency_key": f"{trigger_id}:daemon:{signature}",
                "not_before": _iso(now),
                "payload": {"watch_path": watch_path, "daemon_signature": signature},
                "daemon_signature": signature,
            }
        return {"trigger_id": trigger_id, "type": record.get("type"), "status": "not_scheduled"}

    def _find(self, state: dict[str, Any], trigger_id: str) -> dict[str, Any]:
        for record in state["triggers"]:
            if record.get("trigger_id") == trigger_id:
                return record
        raise KeyError(f"Unknown Autopilot trigger config: {trigger_id}")

    def _sync_queue_status(self, state: dict[str, Any], queue: Mapping[str, Any]) -> bool:
        items_by_id = {
            str(item.get("trigger_id")): item
            for item in queue.get("items", []) or []
            if isinstance(item, Mapping) and item.get("trigger_id")
        }
        changed = False
        for record in state["triggers"]:
            record_changed = False
            queue_id = str(record.get("last_trigger_id") or "")
            if not queue_id:
                continue
            item = items_by_id.get(queue_id)
            if not item:
                continue
            status = item.get("status")
            if status and record.get("last_status") != status:
                record["last_status"] = status
                record_changed = True
            completed_at = item.get("completed_at")
            if completed_at and record.get("last_completed_at") != completed_at:
                record["last_completed_at"] = completed_at
                record_changed = True
            failure = item.get("failure")
            if isinstance(failure, Mapping):
                public_failure = {
                    key: failure.get(key)
                    for key in ("adapter_id", "code", "failed_state", "message", "retryable")
                    if failure.get(key) is not None
                }
                if record.get("last_failure") != public_failure:
                    record["last_failure"] = public_failure
                    record_changed = True
            elif record.get("last_failure") is not None and status == "completed":
                record.pop("last_failure", None)
                record_changed = True
            if record_changed:
                record["updated_at"] = _now()
                changed = True
        return changed

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        triggers = payload.get("triggers") if isinstance(payload, Mapping) else []
        return {
            "schema_version": TRIGGER_REGISTRY_SCHEMA_VERSION,
            "updated_at": _now(),
            "triggers": [dict(item) for item in triggers or [] if isinstance(item, Mapping)],
        }

    def _save(self, payload: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        normalized = {
            "schema_version": TRIGGER_REGISTRY_SCHEMA_VERSION,
            "updated_at": _now(),
            "triggers": [dict(item) for item in payload.get("triggers", [])],
        }
        tmp = self.path.with_name(f"{self.path.name}.tmp-{int(time.time() * 1000)}")
        tmp.write_text(json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)


class AutopilotTriggerScheduler:
    """Small local scheduler loop for AAA-hosted Autopilot trigger configs."""

    def __init__(self, registry: AutopilotTriggerRegistry, client_factory: Any, *, default_interval_seconds: float = 60.0):
        self.registry = registry
        self.client_factory = client_factory
        self.default_interval_seconds = max(5.0, float(default_interval_seconds))
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._interval_seconds = self.default_interval_seconds
        self._started_at: str | None = None
        self._last_tick_at: str | None = None
        self._last_tick_status: str | None = None
        self._last_error: str | None = None
        self._tick_count = 0

    def status(self) -> dict[str, Any]:
        with self._lock:
            running = self._thread is not None and self._thread.is_alive()
            return {
                "schema_version": "across-aaa-autopilot-trigger-scheduler/1.0",
                "running": running,
                "interval_seconds": self._interval_seconds,
                "started_at": self._started_at,
                "last_tick_at": self._last_tick_at,
                "last_tick_status": self._last_tick_status,
                "last_error": self._last_error,
                "tick_count": self._tick_count,
            }

    def start(self, *, interval_seconds: float | None = None) -> dict[str, Any]:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self.status()
            self._interval_seconds = max(5.0, float(interval_seconds or self.default_interval_seconds))
            self._stop_event.clear()
            self._started_at = _now()
            self._last_error = None
            self._thread = threading.Thread(target=self._run, name="across-autopilot-trigger-scheduler", daemon=True)
            self._thread.start()
        return self.status()

    def stop(self) -> dict[str, Any]:
        thread: threading.Thread | None
        with self._lock:
            thread = self._thread
            self._stop_event.set()
        if thread is not None:
            thread.join(timeout=2.0)
        with self._lock:
            if self._thread is thread:
                self._thread = None
        return self.status()

    def tick_once(self) -> dict[str, Any]:
        return self._tick()

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval_seconds):
            self._tick()

    def _tick(self) -> dict[str, Any]:
        try:
            result = self.registry.tick(self.client_factory())
            with self._lock:
                self._tick_count += 1
                self._last_tick_at = _now()
                self._last_tick_status = str(result.get("status") or "unknown")
                self._last_error = None
            return result
        except Exception as exc:  # pragma: no cover - defensive runtime telemetry
            with self._lock:
                self._tick_count += 1
                self._last_tick_at = _now()
                self._last_tick_status = "failed"
                self._last_error = str(exc)[:500]
            return {
                "schema_version": "across-aaa-autopilot-trigger-tick/1.0",
                "status": "failed",
                "error": str(exc)[:500],
            }


def build_trigger_registry_summary(registry: Mapping[str, Any]) -> dict[str, Any]:
    triggers = [item for item in registry.get("triggers", []) if isinstance(item, Mapping)]
    by_type: dict[str, int] = {}
    for item in triggers:
        by_type[str(item.get("type") or "unknown")] = by_type.get(str(item.get("type") or "unknown"), 0) + 1
    return {
        "schema_version": "across-aaa-autopilot-trigger-registry-summary/1.0",
        "total": len(triggers),
        "enabled": sum(1 for item in triggers if item.get("enabled") is not False and item.get("paused") is not True),
        "paused": sum(1 for item in triggers if item.get("paused") is True),
        "by_type": by_type,
        "enqueue_count": sum(int(item.get("enqueue_count") or 0) for item in triggers),
    }


def _trigger_id(spec: str, trigger_type: str, now: str) -> str:
    return "atc-" + _sha256(f"{spec}:{trigger_type}:{now}")[:16]


def _required_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text


def _redact_webhook(value: dict[str, Any]) -> dict[str, Any]:
    value.pop("secret", None)
    return value


def _path_signature(path: str) -> str | None:
    target = Path(path).expanduser()
    try:
        stat = target.stat()
    except OSError:
        return None
    return _sha256(f"{target.resolve()}:{stat.st_mtime_ns}:{stat.st_size}")


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if str(key).lower() == lowered:
            return str(value)
    return None


def _sha256(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return _iso(time.time())


def _iso(timestamp: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))


def _parse_iso(value: Any) -> float | None:
    if not value:
        return None
    try:
        return float(calendar.timegm(time.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ")))
    except Exception:
        return None
