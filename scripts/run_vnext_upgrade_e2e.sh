#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AUTOPILOT_ROOT="${ACROSS_AUTOPILOT_SOURCE:-"$ROOT_DIR/../across-autopilot"}"
CONTEXT_ROOT="${ACROSS_CONTEXT_SOURCE:-"$ROOT_DIR/../across-context"}"
ORCHESTRATOR_ROOT="${ACROSS_ORCHESTRATOR_SOURCE:-"$ROOT_DIR/../across-orchestrator"}"
UV_BIN="${UV_BIN:-$(command -v uv || true)}"
TIMEOUT_SECONDS="${VNEXT_E2E_TIMEOUT_SECONDS:-1800}"
AGENT_MODE="${VNEXT_E2E_AGENT_MODE:-real}"

if [[ "$AGENT_MODE" != "real" && "$AGENT_MODE" != "fixture" ]]; then
  echo "VNEXT_E2E_AGENT_MODE must be real or fixture." >&2
  exit 1
fi

if [[ -z "$UV_BIN" ]]; then
  echo "uv is required for the vNext E2E." >&2
  exit 1
fi

for dir in "$AUTOPILOT_ROOT" "$CONTEXT_ROOT" "$ORCHESTRATOR_ROOT"; do
  [[ -d "$dir" ]] || { echo "Missing Across checkout: $dir" >&2; exit 1; }
done

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/across-vnext-e2e.XXXXXX")"
ACROSS_HOME="$TMP_ROOT/across"
ACROSS_AGENTS_HOME="$TMP_ROOT/aaa"
FIXTURE_REPO="$TMP_ROOT/incident-correlation-service"
SUMMARY_PATH="$TMP_ROOT/vnext-e2e-summary.json"
SERVER_PID=""

cleanup() {
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
  if [[ "${KEEP_VNEXT_E2E_HOME:-0}" == "1" ]]; then
    echo "Preserved vNext E2E home: $TMP_ROOT"
  else
    rm -rf "$TMP_ROOT"
  fi
}
trap cleanup EXIT

mkdir -p "$ACROSS_HOME"

E2E_PATH="$PATH"
FIXTURE_AGENT_ENABLED=0
if [[ "$AGENT_MODE" == "fixture" ]]; then
  mkdir -p "$TMP_ROOT/fixture-bin"
  ln -s "$ROOT_DIR/scripts/vnext_fixture_codex.py" "$TMP_ROOT/fixture-bin/codex"
  ACROSS_AGENTS_HOME="$ACROSS_AGENTS_HOME" FIXTURE_CODEX="$TMP_ROOT/fixture-bin/codex" python3 - <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ["ACROSS_AGENTS_HOME"])
fixture_codex = os.environ["FIXTURE_CODEX"]
root.mkdir(parents=True, exist_ok=True)
(root / "local_agents.json").write_text(
    json.dumps(
        {
            "agents": {
                "codex": {
                    "executable_path": fixture_codex,
                    "model": "auto",
                }
            }
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY
  E2E_PATH="$TMP_ROOT/fixture-bin:$PATH"
  FIXTURE_AGENT_ENABLED=1
fi

echo "== Creating realistic repository fixture =="
python3 - "$FIXTURE_REPO" <<'PY'
import json
import os
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
(root / ".across").mkdir(parents=True)
(root / ".github").mkdir(parents=True)
(root / "incident_correlation").mkdir(parents=True)
(root / "tests").mkdir(parents=True)

files = {
    ".gitignore": "__pycache__/\n*.py[cod]\n",
    "README.md": """# Incident Correlation Service

This repository turns JSONL operational events into deterministic incident summaries.
The vNext task must implement the package, CLI, tests, and operator documentation.
""",
    "incident_correlation/__init__.py": """\"\"\"Incident correlation package.\"\"\"\n\nfrom .engine import correlate_events\n\n__all__ = [\"correlate_events\"]\n""",
    "incident_correlation/engine.py": """\"\"\"Correlation engine placeholder for the supervised workspace task.\"\"\"\n\ndef correlate_events(events):\n    raise NotImplementedError(\"Implement deterministic incident correlation\")\n""",
    "incident_correlation/cli.py": """\"\"\"JSONL incident report CLI placeholder.\"\"\"\n\ndef main():\n    raise SystemExit(2)\n\nif __name__ == \"__main__\":\n    main()\n""",
    "tests/test_engine.py": """import unittest\n\nfrom incident_correlation import correlate_events\n\n\nclass CorrelationTests(unittest.TestCase):\n    def test_groups_deduplicates_orders_and_summarizes(self):\n        events = [\n            {\"event_id\": \"evt-3\", \"incident_id\": \"inc-b\", \"service\": \"billing\", \"severity\": \"warning\", \"timestamp\": \"2026-07-10T02:01:00Z\", \"message\": \"queue lag\"},\n            {\"event_id\": \"evt-1\", \"incident_id\": \"inc-a\", \"service\": \"api\", \"severity\": \"critical\", \"timestamp\": \"2026-07-10T02:00:00Z\", \"message\": \"requests failing\"},\n            {\"event_id\": \"evt-1\", \"incident_id\": \"inc-a\", \"service\": \"api\", \"severity\": \"critical\", \"timestamp\": \"2026-07-10T02:00:00Z\", \"message\": \"duplicate\"},\n            {\"event_id\": \"evt-2\", \"incident_id\": \"inc-a\", \"service\": \"worker\", \"severity\": \"error\", \"timestamp\": \"2026-07-10T02:00:30Z\", \"message\": \"retry exhausted\"},\n        ]\n        result = correlate_events(events)\n        self.assertEqual([item[\"incident_id\"] for item in result], [\"inc-a\", \"inc-b\"])\n        self.assertEqual(result[0][\"severity\"], \"critical\")\n        self.assertEqual(result[0][\"event_count\"], 2)\n        self.assertEqual(result[0][\"services\"], [\"api\", \"worker\"])\n        self.assertEqual(result[0][\"first_seen\"], \"2026-07-10T02:00:00Z\")\n        self.assertEqual(result[0][\"last_seen\"], \"2026-07-10T02:00:30Z\")\n\n    def test_rejects_invalid_records_with_stable_error(self):\n        with self.assertRaisesRegex(ValueError, \"incident_id\"):\n            correlate_events([{\"event_id\": \"evt-invalid\"}])\n\n\nif __name__ == \"__main__\":\n    unittest.main()\n""",
    "tests/test_cli.py": """import json\nimport subprocess\nimport sys\nimport tempfile\nimport unittest\nfrom pathlib import Path\n\n\nclass CliTests(unittest.TestCase):\n    def test_cli_writes_deterministic_json_report(self):\n        events = [\n            {\"event_id\": \"evt-2\", \"incident_id\": \"inc-7\", \"service\": \"worker\", \"severity\": \"error\", \"timestamp\": \"2026-07-10T02:02:00Z\", \"message\": \"retry exhausted\"},\n            {\"event_id\": \"evt-1\", \"incident_id\": \"inc-7\", \"service\": \"api\", \"severity\": \"critical\", \"timestamp\": \"2026-07-10T02:00:00Z\", \"message\": \"requests failing\"},\n        ]\n        with tempfile.TemporaryDirectory() as directory:\n            source = Path(directory) / \"events.jsonl\"\n            output = Path(directory) / \"report.json\"\n            source.write_text(\"\".join(json.dumps(item) + \"\\n\" for item in events), encoding=\"utf-8\")\n            completed = subprocess.run(\n                [sys.executable, \"-m\", \"incident_correlation.cli\", \"--input\", str(source), \"--output\", str(output)],\n                check=False, text=True, capture_output=True,\n            )\n            self.assertEqual(completed.returncode, 0, completed.stderr)\n            report = json.loads(output.read_text(encoding=\"utf-8\"))\n            self.assertEqual(report[\"schema_version\"], \"incident-correlation-report/1.0\")\n            self.assertEqual(report[\"incident_count\"], 1)\n            self.assertEqual(report[\"incidents\"][0][\"severity\"], \"critical\")\n\n\nif __name__ == \"__main__\":\n    unittest.main()\n""",
    ".github/CODEOWNERS": "* @across-reviewers\n",
}

gate_config = {
    "schema_version": "across-autopilot-gate-config/1.0",
    "id": "incident-correlation-trusted-baseline",
    "network_policy": "none",
    "checks": [
        {
            "id": "python-unit-tests",
            "category": "test",
            "argv": ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"],
            "required": True,
            "timeout_ms": 120000,
            "repair": {"strategy": "auto", "suggested_action": "Repair the implementation and tests."},
        },
        {
            "id": "python-compile",
            "category": "lint",
            "argv": ["python3", "-m", "compileall", "-q", "incident_correlation", "tests"],
            "required": True,
            "timeout_ms": 60000,
        },
    ],
    "tools": [],
    "budget": {
        "max_commands": 6,
        "max_total_timeout_ms": 300000,
        "max_diff_bytes": 1000000,
        "max_changed_files": 100,
        "max_findings": 100,
        "max_output_bytes": 64000,
        "max_repair_actions": 3,
        "max_repair_rounds": 2,
    },
    "ci": {"required": True, "expected_checks": ["lint", "test", "review"]},
    "policies": {
        "dirty_tree": "block",
        "base_must_be_ancestor": True,
        "codeowners": {"required": True, "require_changed_file_coverage": True},
        "generated_files": {"mode": "block_unpaired", "patterns": ["**/*.generated.*", "**/generated/**"]},
        "vulnerability": {"required_tool": False},
    },
}
files[".across/repo-push-gate.json"] = json.dumps(gate_config, indent=2, sort_keys=True) + "\n"

for relative, content in files.items():
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

subprocess.run(["git", "init", "-b", "main", str(root)], check=True, capture_output=True)
subprocess.run(["git", "-C", str(root), "config", "user.name", "Across E2E"], check=True)
subprocess.run(["git", "-C", str(root), "config", "user.email", "e2e@across.invalid"], check=True)
subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
subprocess.run(["git", "-C", str(root), "commit", "-m", "Create incident correlation baseline"], check=True, capture_output=True)
PY

python3 - "$TMP_ROOT/ci-status.json" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps({
    "checks": [
        {"id": "lint", "status": "passed", "url": "https://example.invalid/checks/lint"},
        {"id": "test", "status": "passed", "url": "https://example.invalid/checks/test"},
        {"id": "review", "status": "passed", "url": "https://example.invalid/checks/review"},
    ]
}, indent=2) + "\n", encoding="utf-8")
PY

echo "== Installing managed Context and Autopilot runtimes =="
node "$CONTEXT_ROOT/src/cli.js" install host-plugin --across-home "$ACROSS_HOME" --json > "$TMP_ROOT/context-install.json"
node "$AUTOPILOT_ROOT/src/cli.js" install host-plugin --across-home "$ACROSS_HOME" --json > "$TMP_ROOT/autopilot-install.json"

PORT="$(python3 - <<'PY'
import socket
s = socket.socket()
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
)"
BASE_URL="http://127.0.0.1:$PORT"
ORCHESTRATOR_COMMAND_JSON="$(python3 - "$UV_BIN" "$ORCHESTRATOR_ROOT" <<'PY'
import json, sys
print(json.dumps([sys.argv[1], "run", "--project", sys.argv[2], "--python", "3.12", "python", "-m", "across_orchestrator.cli"]))
PY
)"

echo "== Starting AAA backend =="
BACKEND_COMMAND=(
  "$UV_BIN" run
  --with-requirements "$ROOT_DIR/backend/requirements_no_pyobjc.txt"
  --python 3.11
  python
)
if [[ -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
  BACKEND_COMMAND=("$ROOT_DIR/backend/.venv/bin/python")
fi
env \
  "PATH=$E2E_PATH" \
  "PYTHONPATH=$ROOT_DIR/backend/src" \
  "ACROSS_HOME=$ACROSS_HOME" \
  "ACROSS_AGENTS_HOME=$ACROSS_AGENTS_HOME" \
  "ACROSS_VNEXT_E2E_FIXTURE_AGENT=$FIXTURE_AGENT_ENABLED" \
  "ACROSS_CONTEXT_COMMAND=$ACROSS_HOME/bin/across-context" \
  "ACROSS_ORCHESTRATOR_COMMAND=$ORCHESTRATOR_COMMAND_JSON" \
  "${BACKEND_COMMAND[@]}" -m uvicorn across_agents_assistant.api_server:app --host 127.0.0.1 --port "$PORT" \
  > "$TMP_ROOT/aaa-backend.log" 2>&1 &
SERVER_PID="$!"

if ! python3 - "$BASE_URL" <<'PY'
import sys, time, urllib.request
base = sys.argv[1]
deadline = time.time() + 60
last = None
while time.time() < deadline:
    try:
        with urllib.request.urlopen(base + "/api/health", timeout=2) as response:
            if response.status == 200:
                raise SystemExit(0)
    except Exception as exc:
        last = exc
        time.sleep(0.5)
raise SystemExit(f"AAA backend did not become ready: {last}")
PY
then
  echo "== AAA backend log ==" >&2
  tail -n 120 "$TMP_ROOT/aaa-backend.log" >&2 || true
  exit 1
fi

echo "== Running real parallel workspace, gate, promotion, and memory lifecycle =="
ACROSS_HOME="$ACROSS_HOME" \
VNEXT_E2E_AGENT_MODE="$AGENT_MODE" \
python3 - "$BASE_URL" "$FIXTURE_REPO" "$ACROSS_HOME" "$TMP_ROOT/ci-status.json" "$SUMMARY_PATH" "$TIMEOUT_SECONDS" <<'PY'
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

base, repo_raw, across_raw, ci_raw, summary_raw, timeout_raw = sys.argv[1:]
repo = Path(repo_raw)
across_home = Path(across_raw)
ci_path = Path(ci_raw)
summary_path = Path(summary_raw)
timeout_seconds = float(timeout_raw)


def request(method, path, payload=None, timeout=120):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body)
        except json.JSONDecodeError:
            detail = body
        return exc.code, detail


status, readiness = request(
    "GET",
    "/api/agent-workspaces/readiness?refresh=true&repo_root="
    + urllib.parse.quote(str(repo))
    + "&selected_agent_ids=codex",
)
assert status == 200, readiness
assert readiness["status"] == "ready", readiness
available = [item["agent_id"] for item in readiness["available_local_agents"]]
if os.environ.get("VNEXT_E2E_AGENT_MODE") == "fixture":
    selected = ["codex"] if "codex" in available else []
else:
    selected = [item for item in ("codex", "claude", "kimi") if item in available][:2]
assert selected, readiness

prompt = """Implement the production-quality incident correlation workflow described by the committed tests and README.

Requirements:
1. Validate every event and reject malformed records with stable, field-specific ValueError messages.
2. Deduplicate by event_id, group by incident_id, rank critical > error > warning > info, and return deterministic incident ordering.
3. Report event_count, sorted unique services, first_seen, last_seen, and a bounded summary per incident.
4. Implement `python -m incident_correlation.cli --input events.jsonl --output report.json` with schema incident-correlation-report/1.0, deterministic JSON, JSONL line-number errors, and atomic output replacement.
5. Add meaningful edge-case tests for duplicate conflicts, unknown severity, malformed JSONL, and deterministic output; update operator documentation.
6. Do not alter .across/repo-push-gate.json or weaken existing tests. Work only in this isolated worktree and leave changes for review.
"""
status, workspace = request(
    "POST",
    "/api/agent-workspaces",
    {
        "repo_root": str(repo),
        "prompt": prompt,
        "agent_ids": selected,
        "execution_strategy": "parallel_worktrees",
        "validation_commands": [
            ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"],
            ["python3", "-m", "compileall", "-q", "incident_correlation", "tests"],
            ["git", "diff", "--check"],
        ],
        "task_timeout_seconds": min(timeout_seconds, 1800),
        "test_timeout_seconds": 180,
        "idempotency_key": "vnext-incident-correlation-complex-e2e",
        "workflow": "repo-quality-copilot",
        "quality_gate_ci_path": str(ci_path),
        "quality_gate_ci_wait_seconds": 10,
        "quality_gate_draft_pr": True,
    },
    timeout=180,
)
assert status == 201, workspace
workspace_id = workspace["workspace_id"]


def await_stable(deadline_seconds):
    deadline = time.time() + deadline_seconds
    latest = None
    while time.time() < deadline:
        code, latest = request("GET", f"/api/agent-workspaces/{workspace_id}")
        assert code == 200, latest
        if latest["status"] not in {"creating", "running", "revising", "cancelling"}:
            return latest
        time.sleep(5)
    raise AssertionError({"message": "workspace timeout", "latest": latest})


workspace = await_stable(timeout_seconds)
ready_candidates = [
    item for item in workspace["candidates"]
    if item["status"] == "completed" and item["evidence"]["ready_for_review"] is True
]
if not ready_candidates:
    repairable = [item for item in workspace["candidates"] if item["status"] in {"failed", "completed"}]
    repairable.sort(
        key=lambda item: (
            len(item.get("comparison", {}).get("changed_files", [])),
            item.get("comparison", {}).get("quality_gate", {}).get("status") == "passed",
        ),
        reverse=True,
    )
    repair_target = repairable[0] if repairable else None
    assert repair_target is not None, workspace
    code, _ = request(
        "POST",
        f"/api/agent-workspaces/{workspace_id}/comment",
        {
            "candidate_id": repair_target["candidate_id"],
            "comment": "Repair every failing repository validation and managed quality-gate finding. Re-run the full unittest, compile, and diff checks. Keep the trusted gate configuration unchanged.",
        },
    )
    assert code == 200
    workspace = await_stable(timeout_seconds)
    ready_candidates = [
        item for item in workspace["candidates"]
        if item["status"] == "completed" and item["evidence"]["ready_for_review"] is True
    ]
assert ready_candidates, workspace
candidate = ready_candidates[0]
candidate_id = candidate["candidate_id"]
quality_gate = candidate["comparison"]["quality_gate"]
assert quality_gate["status"] == "passed", quality_gate
assert quality_gate["evidence_hash"], quality_gate
assert quality_gate["push_receipt"]["gate_verdict"] == "pass", quality_gate

candidate_root = across_home / "data" / "across-agents-assistant" / "agent-workspaces" / workspace_id / "worktrees" / candidate_id
candidate_head = subprocess.check_output(["git", "-C", str(candidate_root), "rev-parse", "HEAD"], text=True).strip()
base_sha = workspace["base_sha"]

patch = subprocess.check_output(
    ["git", "-C", str(candidate_root), "diff", "--unified=0", base_sha, candidate_head, "--"],
    text=True,
)
review_path = None
review_line = None
current_path = None
for patch_line in patch.splitlines():
    if patch_line.startswith("+++ b/"):
        current_path = patch_line[6:]
    elif current_path and patch_line.startswith("@@"):
        target = patch_line.split("+")[1].split(" ")[0]
        start = int(target.split(",")[0])
        if current_path == "README.md" or review_path is None:
            review_path, review_line = current_path, start
        if current_path == "README.md":
            break
assert review_path and review_line, patch
code, reviewed = request(
    "POST",
    f"/api/agent-workspaces/{workspace_id}/line-reviews",
    {
        "candidate_id": candidate_id,
        "anchor": candidate["comparison"]["review_anchor"],
        "comments": [{
            "path": review_path,
            "side": "RIGHT",
            "line": review_line,
            "body": "Clarify the operational contract at this line without weakening validation, determinism, or error handling. Re-run every required check.",
        }],
        "idempotency_key": "vnext-complex-e2e-line-review",
    },
    timeout=180,
)
assert code == 200 and reviewed["status"] == "revising", reviewed
workspace = await_stable(timeout_seconds)
candidate = next(item for item in workspace["candidates"] if item["candidate_id"] == candidate_id)
assert candidate["status"] == "completed" and candidate["evidence"]["ready_for_review"] is True, candidate
assert workspace["line_review_batches"][0]["comment_count"] == 1, workspace["line_review_batches"]
quality_gate = candidate["comparison"]["quality_gate"]
candidate_head = subprocess.check_output(["git", "-C", str(candidate_root), "rev-parse", "HEAD"], text=True).strip()
ci_completed = json.loads(ci_path.read_text(encoding="utf-8"))
ci_pending = json.loads(json.dumps(ci_completed))
ci_pending["checks"][1]["status"] = "queued"
ci_path.write_text(json.dumps(ci_pending, indent=2) + "\n", encoding="utf-8")


def publish_completed_ci():
    replacement = ci_path.with_suffix(".completed.json")
    replacement.write_text(json.dumps(ci_completed, indent=2) + "\n", encoding="utf-8")
    replacement.replace(ci_path)


threading.Timer(1.0, publish_completed_ci).start()
code, gate = request(
    "POST",
    "/api/quality-gates/run",
    {
        "repo_root": str(candidate_root),
        "base_ref": base_sha,
        "head_ref": "HEAD",
        "commit": candidate_head,
        "ci_path": str(ci_path),
        "ci_wait_seconds": 10,
        "draft_pr": True,
        "max_repairs": 2,
        "timeout_seconds": 600,
    },
    timeout=700,
)
assert code == 200, gate
assert gate["schema_version"] == "across-autopilot-gate-result/1.0", gate
assert gate["gate_verdict"] == "pass", gate
assert gate["dirty_tree"] is False, gate
assert gate["head_sha"] == candidate_head, gate
assert gate["draft_pr"]["requested"] is True, gate["draft_pr"]
assert gate["draft_pr"]["status"] == "planned", gate["draft_pr"]
assert gate["draft_pr"]["mutation_performed"] is False, gate["draft_pr"]
assert gate["push_receipt"]["evidence_hash"] == gate["evidence_hash"], gate
assert gate["ci"]["status"] == "passed", gate["ci"]
assert gate["ci"]["watcher"]["mode"] == "bounded_file_watch", gate["ci"]
assert gate["ci"]["watcher"]["status"] == "observed", gate["ci"]
assert gate["github_review"]["check_run"]["conclusion"] == "success", gate["github_review"]
assert gate["github_review"]["pr_comment"]["evidence_hash"] == gate["evidence_hash"], gate["github_review"]

code, selected_state = request(
    "POST", f"/api/agent-workspaces/{workspace_id}/select", {"candidate_id": candidate_id}
)
assert code == 200, selected_state
code, denied = request(
    "POST",
    f"/api/agent-workspaces/{workspace_id}/promote",
    {"candidate_id": candidate_id, "approved": False},
)
assert code == 403, denied
assert denied["detail"]["code"] == "human_approval_required", denied
code, promoted = request(
    "POST",
    f"/api/agent-workspaces/{workspace_id}/promote",
    {"candidate_id": candidate_id, "approved": True, "approved_by": "vnext-e2e-owner"},
    timeout=180,
)
assert code == 200, promoted
assert promoted["status"] == "promoted", promoted
subprocess.run(
    ["python3", "-m", "unittest", "discover", "-s", "tests", "-v"],
    cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
)

memory_payload = {
    key: gate["push_receipt"].get(key)
    for key in (
        "schema_version", "repository", "base_ref", "head_ref", "head_sha",
        "dirty_tree", "gate_verdict", "evidence_hash", "pr_ready_summary",
    )
}
memory_payload["memory_summary"] = "Approved incident correlation implementation passed trusted gate, CI watcher, unit tests, compile checks, CODEOWNERS coverage, and human promotion review."
memory_text = json.dumps(memory_payload, sort_keys=True)
code, remembered = request(
    "POST",
    "/api/memory/remember",
    {"text": memory_text, "projectRoot": str(repo), "scope": "project", "type": "note", "status": "pending", "tags": ["repo-quality", "incident-correlation"]},
)
assert code == 200, remembered
memory_id = remembered["memory"]["id"]
code, ordinary_before = request(
    "POST", "/api/memory/search", {"query": "incident correlation trusted gate", "projectRoot": str(repo), "mode": "hybrid"}
)
assert code == 200, ordinary_before
assert all(item.get("entry", {}).get("id") != memory_id for item in ordinary_before.get("results", [])), ordinary_before
code, pending = request(
    "POST", "/api/memory/search", {"query": "incident correlation trusted gate", "projectRoot": str(repo), "mode": "hybrid", "status": "pending"}
)
assert code == 200, pending
assert any(item.get("entry", {}).get("id") == memory_id for item in pending.get("results", [])), pending
code, approved = request(
    "POST", f"/api/memory/memories/{memory_id}/status", {"status": "active"}
)
assert code == 200 and approved["memory"]["status"] == "active", approved
code, ordinary_after = request(
    "POST", "/api/memory/search", {"query": "incident correlation trusted gate", "projectRoot": str(repo), "mode": "hybrid"}
)
assert code == 200, ordinary_after
assert any(item.get("entry", {}).get("id") == memory_id for item in ordinary_after.get("results", [])), ordinary_after
evidence_recall = json.loads(subprocess.check_output(
    [
        str(across_home / "bin" / "across-context"),
        "retrieve",
        "incident correlation",
        "--route",
        "evidence_graph",
        "--project",
        str(repo),
        "--json",
    ],
    text=True,
))
assert any(item.get("entry", {}).get("id") == memory_id for item in evidence_recall.get("results", [])), evidence_recall

distillation_sources = []
for suffix in ("heartbeat", "stream"):
    code, source = request(
        "POST",
        "/api/memory/remember",
        {
            "text": f"Recurring quality gate timeout requires live {suffix} evidence, bounded wall time, and resumable retry.",
            "projectRoot": str(repo),
            "scope": "project",
            "type": "session",
            "status": "pending",
            "tags": ["failure-pattern", "quality-gate-timeout"],
        },
    )
    assert code == 200, source
    distillation_sources.append(source["memory"]["id"])
code, improved = request(
    "POST",
    "/api/memory/improve",
    {"projectRoot": str(repo), "sourceIds": distillation_sources, "similarityThreshold": 0.3},
)
assert code == 200 and improved["approval_required"] is True, improved
assert improved["proposal_count"] == 1, improved
proposal_id = improved["proposals"][0]["memory"]["id"]
all_routes = ["keyword", "embedding", "evidence_graph", "project_profile", "loop_recall"]
code, merged_pending = request(
    "POST",
    "/api/memory/retrieve/merged",
    {
        "query": "quality gate timeout heartbeat retry",
        "projectRoot": str(repo),
        "routes": all_routes,
        "status": "pending",
        "reviewPending": True,
        "includeRouteResults": True,
        "limit": 10,
    },
)
assert code == 200, merged_pending
assert merged_pending["strategy"] == "weighted-reciprocal-rank-fusion", merged_pending
assert any(item.get("entry", {}).get("id") == proposal_id for item in merged_pending.get("results", [])), merged_pending
code, distilled_approved = request(
    "POST", f"/api/memory/memories/{proposal_id}/status", {"status": "active"}
)
assert code == 200 and distilled_approved["memory"]["status"] == "active", distilled_approved
code, merged_active = request(
    "POST",
    "/api/memory/retrieve/merged",
    {"query": "quality gate timeout heartbeat retry", "projectRoot": str(repo), "routes": all_routes, "limit": 10},
)
assert code == 200, merged_active
assert any(item.get("entry", {}).get("id") == proposal_id for item in merged_active.get("results", [])), merged_active
code, rolled_back = request("POST", f"/api/memory/distilled/{proposal_id}/rollback")
assert code == 200 and rolled_back["status"] == "archived", rolled_back
assert set(rolled_back["restored_source_ids"]) == set(distillation_sources), rolled_back

code, events = request("GET", f"/api/agent-workspaces/{workspace_id}/events")
assert code == 200, events
event_types = [item["type"] for item in events["events"]]
for required in ("workspace.created", "candidate.started", "candidate.evidence.updated", "candidate.selected", "promotion.approved", "promotion.completed"):
    assert required in event_types, event_types

summary = {
    "schema_version": "across-vnext-e2e/1.0",
    "status": "passed",
    "fixture": "incident-correlation-service",
    "workspace_id": workspace_id,
    "agents": selected,
    "agent_mode": os.environ.get("VNEXT_E2E_AGENT_MODE", "real"),
    "selected_candidate_id": candidate_id,
    "candidate_head_sha": candidate_head,
    "base_sha": base_sha,
    "changed_files": candidate["comparison"]["changed_files"],
    "validation_status": candidate["comparison"]["tests"]["status"],
    "gate_verdict": gate["gate_verdict"],
    "gate_evidence_hash": gate["evidence_hash"],
    "autopilot_gate_contract": {
        "schema_version": gate["schema_version"],
        "findings": gate["findings"],
        "push_receipt": {
            "schema_version": gate["push_receipt"]["schema_version"],
            "repository": {"name": gate["push_receipt"]["repository"]["name"]},
            "base_ref": gate["push_receipt"]["base_ref"],
            "head_ref": gate["push_receipt"]["head_ref"],
            "head_sha": gate["push_receipt"]["head_sha"],
            "dirty_tree": gate["push_receipt"]["dirty_tree"],
            "gate_verdict": gate["push_receipt"]["gate_verdict"],
            "evidence_hash": gate["push_receipt"]["evidence_hash"],
            "pr_ready_summary": gate["push_receipt"]["pr_ready_summary"],
        },
    },
    "draft_pr_status": gate["draft_pr"]["status"],
    "ci_status": gate["ci"]["status"],
    "github_review_conclusion": gate["github_review"]["check_run"]["conclusion"],
    "promotion_status": promoted["promotion"]["status"],
    "memory_id": memory_id,
    "memory_recalled_after_approval": True,
    "memory_evidence_graph_recalled": True,
    "line_review_applied": True,
    "distilled_memory_id": proposal_id,
    "merged_memory_routes": all_routes,
    "distilled_memory_rolled_back": True,
    "event_count": len(events["events"]),
}
summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

echo "== Verifying Orchestrator finding remediation lifecycle =="
PYTHONPATH="$ORCHESTRATOR_ROOT/src" \
ACROSS_ORCHESTRATOR_HOME="$TMP_ROOT/orchestrator" \
"$UV_BIN" run --project "$ORCHESTRATOR_ROOT" --python 3.12 \
python - "$SUMMARY_PATH" "$FIXTURE_REPO" <<'PY'
import json
import sys
from pathlib import Path

from across_orchestrator.agent_loop import AgentLoopAdapters, AgentLoopRuntime


class Dispatcher:
    requires_cancel_ack = False

    def dispatch(self, *, loop, action_type, context):
        return {
            "status": "completed",
            "action_type": action_type,
            "changed_files": ["incident_correlation/engine.py", "incident_correlation/cli.py", "tests/test_engine.py"],
        }


class FailingThenPassingGate:
    def __init__(self, source_findings):
        self.calls = 0
        self.source_findings = source_findings

    def evaluate(self, *, loop, context):
        self.calls += 1
        if self.calls == 1:
            return {
                "status": "failed",
                "passed": False,
                "findings": [*self.source_findings, {
                    "id": "deterministic-json-contract",
                    "state": "auto_fix_available",
                    "severity": "high",
                    "summary": "The first gate round requires deterministic JSON output repair.",
                    "evidence": [{"type": "test", "id": "test_cli_writes_deterministic_json_report"}],
                    "suggested_action": "Normalize report ordering and rerun the quality gate.",
                    "owner": "incident-correlation",
                    "repair_round": 0,
                    "source_gate": "cli-contract",
                }],
            }
        return {
            "status": "passed",
            "passed": True,
            "findings": [
                *[{**item, "state": "pass", "repair_round": 1} for item in self.source_findings],
                {
                "id": "deterministic-json-contract",
                "state": "pass",
                "severity": "info",
                "summary": "Deterministic JSON output contract passed after remediation.",
                "evidence": [{"type": "test", "id": "test_cli_writes_deterministic_json_report"}],
                "suggested_action": None,
                "owner": "incident-correlation",
                "repair_round": 1,
                "source_gate": "cli-contract",
                },
            ],
        }


summary_path = Path(sys.argv[1])
summary = json.loads(summary_path.read_text(encoding="utf-8"))
autopilot_findings = summary["autopilot_gate_contract"]["findings"]
assert autopilot_findings, summary["autopilot_gate_contract"]
runtime = AgentLoopRuntime(
    adapters=AgentLoopAdapters(
        dispatcher=Dispatcher(),
        quality_gate=FailingThenPassingGate(autopilot_findings),
    )
)
loop = runtime.start_loop(
    goal="Repair and verify deterministic incident correlation evidence",
    project_root=sys.argv[2],
    max_turns=8,
)
completed = runtime.run_loop(loop.loop_id)
assert completed.status == "completed", completed
actions = [step.action.type for step in completed.steps]
assert actions == ["memory_search", "task_dispatch", "quality_gate", "remediation_dispatch", "quality_gate", "memory_write_candidate", "final_output"], actions
assert completed.finding_state == "pass", completed.finding_state
contract_history = [item for item in completed.finding_history if item["id"] == "deterministic-json-contract"]
assert [(item["repair_round"], item["state"]) for item in contract_history] == [(0, "auto_fix_available"), (1, "pass")], contract_history
evidence = runtime.get_loop_evidence_summary(loop.loop_id)
assert evidence["finding_lifecycle"]["history_count"] >= 2 + len(autopilot_findings), evidence
assert evidence["finding_lifecycle"]["state"] == "pass", evidence
summary["orchestrator"] = {
    "loop_id": loop.loop_id,
    "status": completed.status,
    "actions": actions,
    "finding_state": completed.finding_state,
    "finding_history_count": len(completed.finding_history),
    "autopilot_finding_count": len(autopilot_findings),
}
summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

REPORT_DIR="$HOME/.across/data/across-agents-assistant/release-reports"
mkdir -p "$REPORT_DIR"
REPORT_PATH="$REPORT_DIR/vnext-e2e-$(date -u +%Y%m%dT%H%M%SZ).json"
cp "$SUMMARY_PATH" "$REPORT_PATH"

echo "vNext E2E passed: $REPORT_PATH"
python3 -m json.tool "$SUMMARY_PATH"
