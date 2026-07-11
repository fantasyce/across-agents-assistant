#!/usr/bin/env python3
"""Deterministic Codex-compatible process used only by the isolated vNext E2E.

The real-agent E2E remains the default. This fixture exists so the product
contract can be regression-tested even when an external subscription-backed
agent returns successfully without changing its assigned worktree.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


ENGINE = '''"""Deterministic incident correlation."""

from __future__ import annotations

from datetime import datetime


SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2, "critical": 3}
REQUIRED_FIELDS = ("event_id", "incident_id", "service", "severity", "timestamp", "message")


def _validated(event):
    if not isinstance(event, dict):
        raise ValueError("event must be an object")
    item = {}
    for field in REQUIRED_FIELDS:
        value = event.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")
        item[field] = value.strip()
    if item["severity"] not in SEVERITY_RANK:
        raise ValueError("severity must be one of: critical, error, warning, info")
    try:
        datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("timestamp must be ISO-8601") from exc
    return item


def correlate_events(events):
    unique = {}
    for raw in events:
        event = _validated(raw)
        prior = unique.get(event["event_id"])
        if prior is not None and prior != event:
            raise ValueError(f"event_id conflict: {event['event_id']}")
        unique.setdefault(event["event_id"], event)

    grouped = {}
    for event in unique.values():
        grouped.setdefault(event["incident_id"], []).append(event)

    incidents = []
    for incident_id, incident_events in grouped.items():
        ordered = sorted(incident_events, key=lambda item: (item["timestamp"], item["event_id"]))
        severity = max(ordered, key=lambda item: SEVERITY_RANK[item["severity"]])["severity"]
        summary = "; ".join(item["message"] for item in ordered)
        incidents.append({
            "incident_id": incident_id,
            "severity": severity,
            "event_count": len(ordered),
            "services": sorted({item["service"] for item in ordered}),
            "first_seen": ordered[0]["timestamp"],
            "last_seen": ordered[-1]["timestamp"],
            "summary": summary[:500],
        })
    return sorted(
        incidents,
        key=lambda item: (-SEVERITY_RANK[item["severity"]], item["first_seen"], item["incident_id"]),
    )
'''


CLI = '''"""Command-line incident report generator."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from .engine import correlate_events


def _read_jsonl(path):
    events = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"line {line_number}: malformed JSON") from exc
    return events


def _write_atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    incidents = correlate_events(_read_jsonl(Path(args.input)))
    _write_atomic(Path(args.output), {
        "schema_version": "incident-correlation-report/1.0",
        "incident_count": len(incidents),
        "incidents": incidents,
    })


if __name__ == "__main__":
    main()
'''


ENGINE_TESTS = '''import unittest

from incident_correlation import correlate_events


class CorrelationTests(unittest.TestCase):
    def test_groups_deduplicates_orders_and_summarizes(self):
        events = [
            {"event_id": "evt-3", "incident_id": "inc-b", "service": "billing", "severity": "warning", "timestamp": "2026-07-10T02:01:00Z", "message": "queue lag"},
            {"event_id": "evt-1", "incident_id": "inc-a", "service": "api", "severity": "critical", "timestamp": "2026-07-10T02:00:00Z", "message": "requests failing"},
            {"event_id": "evt-1", "incident_id": "inc-a", "service": "api", "severity": "critical", "timestamp": "2026-07-10T02:00:00Z", "message": "requests failing"},
            {"event_id": "evt-2", "incident_id": "inc-a", "service": "worker", "severity": "error", "timestamp": "2026-07-10T02:00:30Z", "message": "retry exhausted"},
        ]
        result = correlate_events(events)
        self.assertEqual([item["incident_id"] for item in result], ["inc-a", "inc-b"])
        self.assertEqual(result[0]["severity"], "critical")
        self.assertEqual(result[0]["event_count"], 2)
        self.assertEqual(result[0]["services"], ["api", "worker"])

    def test_rejects_invalid_records_with_stable_error(self):
        with self.assertRaisesRegex(ValueError, "incident_id"):
            correlate_events([{"event_id": "evt-invalid"}])

    def test_rejects_conflicting_duplicate(self):
        base = {"event_id": "evt-1", "incident_id": "inc-a", "service": "api", "severity": "error", "timestamp": "2026-07-10T02:00:00Z", "message": "failed"}
        with self.assertRaisesRegex(ValueError, "event_id conflict"):
            correlate_events([base, {**base, "message": "different"}])

    def test_rejects_unknown_severity(self):
        event = {"event_id": "evt-1", "incident_id": "inc-a", "service": "api", "severity": "fatal", "timestamp": "2026-07-10T02:00:00Z", "message": "failed"}
        with self.assertRaisesRegex(ValueError, "severity"):
            correlate_events([event])


if __name__ == "__main__":
    unittest.main()
'''


CLI_TESTS = '''import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTests(unittest.TestCase):
    def test_cli_writes_deterministic_json_report(self):
        events = [
            {"event_id": "evt-2", "incident_id": "inc-7", "service": "worker", "severity": "error", "timestamp": "2026-07-10T02:02:00Z", "message": "retry exhausted"},
            {"event_id": "evt-1", "incident_id": "inc-7", "service": "api", "severity": "critical", "timestamp": "2026-07-10T02:00:00Z", "message": "requests failing"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "events.jsonl"
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            source.write_text("".join(json.dumps(item) + "\\n" for item in events), encoding="utf-8")
            for output in (first, second):
                completed = subprocess.run([sys.executable, "-m", "incident_correlation.cli", "--input", str(source), "--output", str(output)], capture_output=True, text=True)
                self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            report = json.loads(first.read_text(encoding="utf-8"))
            self.assertEqual(report["schema_version"], "incident-correlation-report/1.0")

    def test_cli_reports_malformed_jsonl_line(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "events.jsonl"
            output = Path(directory) / "report.json"
            source.write_text("{}\\nnot-json\\n", encoding="utf-8")
            completed = subprocess.run([sys.executable, "-m", "incident_correlation.cli", "--input", str(source), "--output", str(output)], capture_output=True, text=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("line 2", completed.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
'''


def main() -> int:
    if os.environ.get("ACROSS_VNEXT_E2E_FIXTURE_AGENT") != "1":
        print("vNext fixture agent is disabled", file=sys.stderr)
        return 2
    if "--version" in sys.argv:
        print("codex-cli vNext-e2e-fixture")
        return 0

    root = Path.cwd()
    required = root / ".across" / "repo-push-gate.json"
    if not required.is_file():
        print("fixture must run inside the isolated vNext repository", file=sys.stderr)
        return 2

    (root / "incident_correlation" / "engine.py").write_text(ENGINE, encoding="utf-8")
    (root / "incident_correlation" / "cli.py").write_text(CLI, encoding="utf-8")
    (root / "tests" / "test_engine.py").write_text(ENGINE_TESTS, encoding="utf-8")
    (root / "tests" / "test_cli.py").write_text(CLI_TESTS, encoding="utf-8")
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + "\n## Operator workflow\n\nRun `python -m incident_correlation.cli --input events.jsonl --output report.json`. "
        + "The output is deterministic and replaced atomically.\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "type": "item.completed",
        "item": {"type": "agent_message", "text": "Implemented and validated the incident correlation workflow."},
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
