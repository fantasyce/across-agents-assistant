from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
import sys
import threading
import time
from typing import Any, Iterator

_PROGRESS_ENV_KEYS = (
    "ACROSS_AAA_HOST_CLI_PROGRESS_LOG_FILE",
    "ACROSS_AAA_HOST_CLI_PROGRESS_RUN_ID",
    "ACROSS_AAA_HOST_CLI_PROGRESS_CANDIDATE_ID",
    "ACROSS_AAA_HOST_CLI_PROGRESS_PHASE",
)


def host_cli_log(log_file: str, event: str, **fields: Any) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": event,
        **fields,
    }
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    print(line, file=sys.stderr, flush=True)
    try:
        from .paths import log_dir

        path = log_dir() / log_file
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


@contextmanager
def host_cli_progress_scope(
    log_file: str,
    *,
    run_id: Any = None,
    candidate_id: Any = None,
    phase: str = "",
) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in _PROGRESS_ENV_KEYS}
    os.environ["ACROSS_AAA_HOST_CLI_PROGRESS_LOG_FILE"] = log_file
    os.environ["ACROSS_AAA_HOST_CLI_PROGRESS_RUN_ID"] = "" if run_id is None else str(run_id)
    os.environ["ACROSS_AAA_HOST_CLI_PROGRESS_CANDIDATE_ID"] = "" if candidate_id is None else str(candidate_id)
    os.environ["ACROSS_AAA_HOST_CLI_PROGRESS_PHASE"] = str(phase or "")
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def host_cli_activity(event: str, **fields: Any) -> None:
    log_file = os.environ.get("ACROSS_AAA_HOST_CLI_PROGRESS_LOG_FILE")
    if not log_file:
        return
    run_id = os.environ.get("ACROSS_AAA_HOST_CLI_PROGRESS_RUN_ID") or None
    candidate_id = os.environ.get("ACROSS_AAA_HOST_CLI_PROGRESS_CANDIDATE_ID") or None
    phase = os.environ.get("ACROSS_AAA_HOST_CLI_PROGRESS_PHASE") or None
    host_cli_log(log_file, event, run_id=run_id, candidate_id=candidate_id, phase=phase, **fields)


def heartbeat_interval_seconds() -> float:
    raw = str(os.environ.get("ACROSS_AAA_HOST_CLI_HEARTBEAT_SECONDS") or "").strip()
    if not raw:
        return 30.0
    try:
        value = float(raw)
    except ValueError:
        return 30.0
    return max(0.01, min(value, 300.0))


@contextmanager
def host_cli_heartbeat(
    log_file: str,
    event: str,
    *,
    run_id: Any = None,
    candidate_id: Any = None,
    interval_seconds: float | None = None,
    phase: str = "",
) -> Iterator[None]:
    stop = threading.Event()
    started = time.monotonic()
    interval = heartbeat_interval_seconds() if interval_seconds is None else max(0.01, float(interval_seconds))
    beat_count = 0

    def emit_beat() -> None:
        nonlocal beat_count
        beat_count += 1
        host_cli_log(
            log_file,
            event,
            run_id=run_id,
            candidate_id=candidate_id,
            phase=phase or None,
            heartbeat_kind="watchdog",
            heartbeat=beat_count,
            elapsed_sec=round(time.monotonic() - started, 3),
        )

    def emit() -> None:
        while not stop.wait(interval):
            emit_beat()

    thread = threading.Thread(target=emit, name=f"{event}-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=1.0)
        if beat_count == 0 and (time.monotonic() - started) >= interval:
            emit_beat()
