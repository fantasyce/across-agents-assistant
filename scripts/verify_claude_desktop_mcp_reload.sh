#!/bin/bash

set -euo pipefail

CONFIG_FILE=${CLAUDE_CONFIG_FILE:-"$HOME/Library/Application Support/Claude/claude_desktop_config.json"}
APP_CONTROL=${CLAUDE_APP_CONTROL:-}
INSTALL_COMMANDS_FILE=${ACROSS_INSTALL_COMMANDS_FILE:-}
EXPECTED_DIGESTS_FILE=${EXPECTED_TOOL_DIGESTS_FILE:-}
EVIDENCE_FILE=${EVIDENCE_PATH:-}
PYTHON_BIN=${PYTHON_BIN:-python3}
ORIGINAL_EXISTED=0
COMPLETED=0
BACKUP_FILE=""

fail_public() {
    echo "Claude Desktop MCP reload verification failed." >&2
    exit 1
}

is_absolute_file_target() {
    case "$1" in
        /*) return 0 ;;
        *) return 1 ;;
    esac
}

for target in "$CONFIG_FILE" "$INSTALL_COMMANDS_FILE" "$EXPECTED_DIGESTS_FILE" "$EVIDENCE_FILE"; do
    [[ -n "$target" ]] || fail_public
    is_absolute_file_target "$target" || fail_public
done
[[ -d "$(dirname "$CONFIG_FILE")" && ! -L "$CONFIG_FILE" ]] || fail_public
[[ -f "$INSTALL_COMMANDS_FILE" && ! -L "$INSTALL_COMMANDS_FILE" ]] || fail_public
[[ -f "$EXPECTED_DIGESTS_FILE" && ! -L "$EXPECTED_DIGESTS_FILE" ]] || fail_public
[[ -d "$(dirname "$EVIDENCE_FILE")" && ! -L "$EVIDENCE_FILE" ]] || fail_public
if [[ -n "$APP_CONTROL" ]]; then
    is_absolute_file_target "$APP_CONTROL" || fail_public
    [[ -f "$APP_CONTROL" && -x "$APP_CONTROL" && ! -L "$APP_CONTROL" ]] || fail_public
fi
if [[ -e "$CONFIG_FILE" && ! -f "$CONFIG_FILE" ]]; then
    fail_public
fi

control_action() {
    local action="$1"
    if [[ -n "$APP_CONTROL" ]]; then
        "$APP_CONTROL" "$action" >/dev/null 2>&1
        return
    fi
    case "$action" in
        stop)
            /usr/bin/osascript -e 'tell application "Claude" to quit' >/dev/null 2>&1 || true
            ;;
        wait-stopped)
            for _ in $(seq 1 300); do
                /usr/bin/pgrep -x Claude >/dev/null 2>&1 || return 0
                sleep 0.1
            done
            return 1
            ;;
        start)
            /usr/bin/open -a Claude >/dev/null 2>&1
            ;;
        wait-started)
            for _ in $(seq 1 300); do
                /usr/bin/pgrep -x Claude >/dev/null 2>&1 && return 0
                sleep 0.1
            done
            return 1
            ;;
        *) return 1 ;;
    esac
}

BACKUP_FILE=$(mktemp "${CONFIG_FILE}.across-backup.XXXXXX")
if [[ -f "$CONFIG_FILE" ]]; then
    ORIGINAL_EXISTED=1
    /bin/cp -p "$CONFIG_FILE" "$BACKUP_FILE"
else
    /bin/rm -f "$BACKUP_FILE"
fi
export CLAUDE_CONFIG_FILE="$CONFIG_FILE"
export CLAUDE_APP_CONTROL="$APP_CONTROL"
export ACROSS_INSTALL_COMMANDS_FILE="$INSTALL_COMMANDS_FILE"
export EXPECTED_TOOL_DIGESTS_FILE="$EXPECTED_DIGESTS_FILE"
export EVIDENCE_PATH="$EVIDENCE_FILE"
export BACKUP_FILE

restore_original() {
    if [[ "$ORIGINAL_EXISTED" == "1" ]]; then
        RESTORE_SOURCE="$BACKUP_FILE" RESTORE_TARGET="$CONFIG_FILE" "$PYTHON_BIN" - <<'PY'
import os
from pathlib import Path
import tempfile

source = Path(os.environ["RESTORE_SOURCE"])
target = Path(os.environ["RESTORE_TARGET"])
data = source.read_bytes()
fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.restore-", dir=target.parent)
try:
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary_name, source.stat().st_mode & 0o777)
    os.replace(temporary_name, target)
finally:
    try:
        os.unlink(temporary_name)
    except FileNotFoundError:
        pass
PY
    else
        /bin/rm -f "$CONFIG_FILE"
    fi
}

on_exit() {
    local status=$?
    trap - EXIT INT TERM
    if [[ "$status" != "0" && "$COMPLETED" != "1" ]]; then
        restore_original >/dev/null 2>&1 || true
        control_action stop || true
        control_action wait-stopped || true
        control_action start || true
        control_action wait-started || true
    fi
    [[ -z "$BACKUP_FILE" ]] || /bin/rm -f "$BACKUP_FILE"
    exit "$status"
}

trap 'exit 130' INT
trap 'exit 143' TERM
trap on_exit EXIT

"$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any


SERVER_IDS = ("across-context", "across-orchestrator", "across-autopilot")
SERVER_ID_SET = set(SERVER_IDS)
HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")
PRIVATE_TEXT = re.compile(
    r"(/Users/|/private/|sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)


class ReloadFailure(RuntimeError):
    pass


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ReloadFailure from exc
    if type(value) is not dict:
        raise ReloadFailure
    return value


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    serialized = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def run_control(action: str) -> None:
    controller = os.environ.get("CLAUDE_APP_CONTROL", "")
    if not controller:
        if action == "stop":
            subprocess.run(["/usr/bin/osascript", "-e", 'tell application "Claude" to quit'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            return
        if action == "start":
            command = ["/usr/bin/open", "-a", "Claude"]
        elif action == "wait-stopped":
            command = ["/bin/bash", "-c", "for i in $(seq 1 300); do /usr/bin/pgrep -x Claude >/dev/null || exit 0; sleep 0.1; done; exit 1"]
        elif action == "wait-started":
            command = ["/bin/bash", "-c", "for i in $(seq 1 300); do /usr/bin/pgrep -x Claude >/dev/null && exit 0; sleep 0.1; done; exit 1"]
        else:
            raise ReloadFailure
    else:
        command = [controller, action]
    try:
        completed = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=35, check=False)
    except Exception as exc:
        raise ReloadFailure from exc
    if completed.returncode != 0:
        raise ReloadFailure


def restart_claude() -> None:
    for action in ("stop", "wait-stopped", "start", "wait-started"):
        run_control(action)


def validate_install_commands(value: object) -> dict[str, list[str]]:
    if type(value) is not dict or set(value) != SERVER_ID_SET:
        raise ReloadFailure
    commands: dict[str, list[str]] = {}
    for plugin_id in SERVER_IDS:
        command = value.get(plugin_id)
        if type(command) is not list or not command or len(command) > 32:
            raise ReloadFailure
        if any(type(item) is not str or not item or "\x00" in item or len(item) > 4096 for item in command):
            raise ReloadFailure
        if sum(item.count("{config_file}") for item in command) != 1:
            raise ReloadFailure
        commands[plugin_id] = list(command)
    return commands


def validate_expected(value: object) -> dict[str, dict[str, object]]:
    if type(value) is not dict or set(value) != SERVER_ID_SET:
        raise ReloadFailure
    expected: dict[str, dict[str, object]] = {}
    for plugin_id in SERVER_IDS:
        item = value.get(plugin_id)
        if type(item) is not dict or set(item) != {"tool_count", "tool_set_digest"}:
            raise ReloadFailure
        count = item.get("tool_count")
        digest = item.get("tool_set_digest")
        if type(count) is not int or count < 0 or count > 256 or type(digest) is not str or not HEX_DIGEST.fullmatch(digest):
            raise ReloadFailure
        expected[plugin_id] = {"tool_count": count, "tool_set_digest": digest}
    return expected


def config_servers(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("mcpServers")
    if value is None:
        return {}
    if type(value) is not dict:
        raise ReloadFailure
    return dict(value)


def run_installer(command: list[str], config_file: Path) -> None:
    argv = [item.replace("{config_file}", str(config_file)) for item in command]
    try:
        completed = subprocess.run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=False)
    except Exception as exc:
        raise ReloadFailure from exc
    if completed.returncode != 0:
        raise ReloadFailure


def probe_tools(entry: object) -> list[dict[str, object]]:
    if type(entry) is not dict:
        raise ReloadFailure
    command = entry.get("command")
    args = entry.get("args", [])
    if type(command) is not str or not command or type(args) is not list or any(type(item) is not str for item in args):
        raise ReloadFailure
    requests = "\n".join(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "Across reload verifier"}}}),
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        ]
    ) + "\n"
    try:
        completed = subprocess.run([command, *args], input=requests, text=True, capture_output=True, timeout=15, check=False)
    except Exception as exc:
        raise ReloadFailure from exc
    if completed.returncode != 0:
        raise ReloadFailure
    try:
        responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
        tools = next(item["result"]["tools"] for item in responses if item.get("id") == 2)
    except Exception as exc:
        raise ReloadFailure from exc
    if type(tools) is not list or any(type(item) is not dict for item in tools):
        raise ReloadFailure
    return tools


def tool_digest(tools: list[dict[str, object]]) -> str:
    canonical = json.dumps(tools, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def main() -> None:
    config_file = Path(os.environ["CLAUDE_CONFIG_FILE"])
    evidence_file = Path(os.environ["EVIDENCE_PATH"])
    commands = validate_install_commands(load_object(Path(os.environ["ACROSS_INSTALL_COMMANDS_FILE"])))
    expected = validate_expected(load_object(Path(os.environ["EXPECTED_TOOL_DIGESTS_FILE"])))
    original_config_present = config_file.exists()
    original = load_object(config_file) if original_config_present else {}
    original_servers = config_servers(original)
    unrelated = {key: value for key, value in original_servers.items() if key not in SERVER_ID_SET}
    original_non_registry = {key: value for key, value in original.items() if key != "mcpServers"}
    before_present = sorted(SERVER_ID_SET.intersection(original_servers))

    removed_config = dict(original)
    removed_config["mcpServers"] = dict(unrelated)
    atomic_json(config_file, removed_config)
    restart_claude()
    removed_servers = config_servers(load_object(config_file))
    if SERVER_ID_SET.intersection(removed_servers) or {key: removed_servers[key] for key in unrelated} != unrelated:
        raise ReloadFailure

    for plugin_id in SERVER_IDS:
        run_installer(commands[plugin_id], config_file)
    installed_config = load_object(config_file)
    installed_servers = config_servers(installed_config)
    if set(installed_servers) != set(unrelated).union(SERVER_ID_SET):
        raise ReloadFailure
    if {key: installed_servers.get(key) for key in unrelated} != unrelated:
        raise ReloadFailure
    if {key: value for key, value in installed_config.items() if key != "mcpServers"} != original_non_registry:
        raise ReloadFailure
    restart_claude()

    server_evidence: dict[str, dict[str, object]] = {}
    for plugin_id in SERVER_IDS:
        tools = probe_tools(installed_servers[plugin_id])
        observed = {"tool_count": len(tools), "tool_set_digest": tool_digest(tools)}
        if observed != expected[plugin_id]:
            raise ReloadFailure
        server_evidence[plugin_id] = observed

    backup_source = Path(os.environ.get("BACKUP_FILE", ""))
    backup_digest = hashlib.sha256(backup_source.read_bytes()).hexdigest() if backup_source.is_file() else hashlib.sha256(b"").hexdigest()
    evidence = {
        "schema_version": "across-claude-desktop-mcp-reload/1.0",
        "status": "passed",
        "servers": list(SERVER_IDS),
        "backup": {"original_present": original_config_present, "content_digest": backup_digest},
        "before": {"across_entry_count": len(before_present)},
        "removed": {"all_absent": True, "restart_completed": True},
        "reinstalled": {
            "all_expected_digests": True,
            "restart_completed": True,
            "servers": server_evidence,
        },
    }
    serialized = json.dumps(evidence, sort_keys=True, ensure_ascii=False)
    if PRIVATE_TEXT.search(serialized):
        raise ReloadFailure
    atomic_json(evidence_file, evidence)


try:
    main()
except Exception:
    print("Claude Desktop MCP reload verification failed.", file=sys.stderr)
    raise SystemExit(1)
PY

COMPLETED=1
/bin/rm -f "$BACKUP_FILE"
BACKUP_FILE=""
trap - EXIT INT TERM
