#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTEXT_ROOT="${ACROSS_CONTEXT_SOURCE:-$ROOT_DIR/../across-context}"
AUTOPILOT_ROOT="${ACROSS_AUTOPILOT_SOURCE:-$ROOT_DIR/../across-autopilot}"
PYTHON_BIN="${ACROSS_AAA_TEST_PYTHON:-$ROOT_DIR/backend/.venv/bin/python}"

for path in "$CONTEXT_ROOT" "$AUTOPILOT_ROOT"; do
  if [[ ! -f "$path/package.json" ]]; then
    echo "Missing local plugin source: $path" >&2
    exit 2
  fi
done
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing AAA backend test Python: $PYTHON_BIN" >&2
  exit 2
fi

PROFILE_HOME="$(mktemp -d /tmp/across-fresh-plugin-profile.XXXXXX)"
cleanup() {
  rm -rf "$PROFILE_HOME"
}
trap cleanup EXIT

env -i \
  HOME="$PROFILE_HOME" \
  PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
  PYTHONPATH="$ROOT_DIR/backend/src" \
  ACROSS_HOME="$PROFILE_HOME/.across" \
  ACROSS_AGENTS_PRODUCT_MODE=1 \
  ACROSS_AGENTS_DEVELOPER_MODE=1 \
  ACROSS_AGENTS_CONTEXT_INSTALL_SOURCE="$CONTEXT_ROOT" \
  ACROSS_AGENTS_AUTOPILOT_INSTALL_SOURCE="$AUTOPILOT_ROOT" \
  AAA_PROJECT_ROOT="$ROOT_DIR" \
  "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from across_agents_assistant.plugin_runtime import (
    discover_across_plugins,
    run_autopilot_plugin_lifecycle_action,
    run_context_plugin_lifecycle_action,
)


env = dict(os.environ)
across_home = Path(env["ACROSS_HOME"])
context = run_context_plugin_lifecycle_action("install", env=env)
autopilot = run_autopilot_plugin_lifecycle_action("install", env=env)
for plugin in (context, autopilot):
    assert plugin["installed"] is True, plugin
    assert plugin["available"] is True, plugin
    assert plugin["integrity_ok"] is True, plugin

visible = {
    item["plugin_id"]: item
    for item in discover_across_plugins(
        plugin_ids=["across-context", "across-autopilot"],
        probe=True,
        env=env,
    )
}
assert set(visible) == {"across-context", "across-autopilot"}, visible
assert all(item["installed"] and item["available"] for item in visible.values()), visible

command = across_home / "bin" / "across-autopilot"
assert command.is_file(), command
run_env = {
    "HOME": env["HOME"],
    "PATH": f'{across_home / "bin"}:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
    "ACROSS_HOME": str(across_home),
    "ACROSS_AGENTS_PRODUCT_MODE": "1",
}
completed = subprocess.run(
    [
        str(command),
        "beginner-pattern",
        "run",
        "--pattern",
        "first-verified-task",
        "--goal",
        "Identify the safest next step for this project",
        "--json",
    ],
    cwd=env["AAA_PROJECT_ROOT"],
    env=run_env,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    timeout=180,
    check=False,
)
assert completed.returncode == 0, completed.stderr
payload = json.loads(completed.stdout)
assert payload["schema_version"] == "across-no-key-demo-result/1.0", payload
assert payload["status"] == "completed", payload
assert payload["verdict"] in {"verified", "needs_attention"}, payload
assert payload["policy"] == {
    "provider_key_used": False,
    "network_used": False,
    "model_calls": 0,
    "external_side_effects_performed": False,
}, payload
assert len(payload["evidence_sha256"]) == 64, payload
assert len(payload["goal_sha256"]) == 64, payload
assert payload["next_action_id"] == "inspect_evidence", payload
print(json.dumps({
    "schema_version": "across-fresh-profile-plugin-no-key-e2e/1.0",
    "status": "passed",
    "installed_plugins": sorted(visible),
    "pattern_id": payload["pattern_id"],
    "verdict": payload["verdict"],
    "policy": payload["policy"],
}, sort_keys=True))
PY
