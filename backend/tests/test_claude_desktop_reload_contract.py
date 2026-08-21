from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_claude_desktop_mcp_reload.sh"
SERVER_IDS = ("across-context", "across-orchestrator", "across-autopilot")


def _tool_digest(tools: list[dict[str, object]]) -> str:
    canonical = json.dumps(tools, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(canonical).hexdigest()


def _write_executable(path: Path, source: str) -> Path:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)
    return path


def _fixture(
    tmp_path: Path,
    *,
    failing_installer: bool = False,
    inject_unrelated_server: bool = False,
) -> dict[str, object]:
    config = tmp_path / "claude_desktop_config.json"
    evidence = tmp_path / "evidence.json"
    controller_log = tmp_path / "controller.log"
    server = _write_executable(
        tmp_path / "fake_mcp_server.py",
        """#!/usr/bin/env python3
import json
import sys
plugin_id, generation = sys.argv[1:3]
for line in sys.stdin:
    request = json.loads(line)
    if 'id' not in request:
        continue
    if request.get('method') == 'initialize':
        result = {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}}, 'serverInfo': {'name': plugin_id, 'version': generation}}
    elif request.get('method') == 'tools/list':
        result = {'tools': [{'name': f'{plugin_id}-generation-{generation}', 'description': 'fixture', 'inputSchema': {'type': 'object', 'properties': {}}}]}
    else:
        result = {}
    print(json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result}), flush=True)
""",
    )
    controller = _write_executable(
        tmp_path / "fake_controller.py",
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys
action = sys.argv[1]
config = Path(os.environ['CLAUDE_CONFIG_FILE'])
payload = json.loads(config.read_text()) if config.exists() else {}
present = sorted(set((payload.get('mcpServers') or {})) & {'across-context', 'across-orchestrator', 'across-autopilot'})
with Path(os.environ['CONTROLLER_LOG']).open('a') as handle:
    handle.write(f"{action}:{','.join(present)}\\n")
""",
    )
    installer = _write_executable(
        tmp_path / "fake_installer.py",
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys
plugin_id, config_path = sys.argv[1:3]
if os.environ.get('FAIL_INSTALLER') == plugin_id:
    raise SystemExit(9)
path = Path(config_path)
payload = json.loads(path.read_text()) if path.exists() else {}
servers = dict(payload.get('mcpServers') or {})
servers[plugin_id] = {'command': sys.executable, 'args': [os.environ['FAKE_MCP_SERVER'], plugin_id, '2']}
if os.environ.get('INJECT_UNRELATED_SERVER') and plugin_id == 'across-orchestrator':
    servers['unexpected-server'] = {'command': '/usr/bin/true', 'args': []}
payload['mcpServers'] = servers
temporary = path.with_name(path.name + '.fixture-tmp')
temporary.write_text(json.dumps(payload, sort_keys=True))
os.replace(temporary, path)
""",
    )
    original = {
        "theme": "dark",
        "mcpServers": {
            "unrelated-server": {"command": "/usr/bin/true", "args": []},
            **{
                plugin_id: {
                    "command": sys.executable,
                    "args": [str(server), plugin_id, "1"],
                }
                for plugin_id in SERVER_IDS
            },
        },
    }
    original_bytes = json.dumps(original, indent=2, sort_keys=True).encode()
    config.write_bytes(original_bytes)
    install_commands = tmp_path / "install_commands.json"
    install_commands.write_text(
        json.dumps(
            {
                plugin_id: [sys.executable, str(installer), plugin_id, "{config_file}"]
                for plugin_id in SERVER_IDS
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    expected = tmp_path / "expected_digests.json"
    expected.write_text(
        json.dumps(
            {
                plugin_id: {
                    "tool_count": 1,
                    "tool_set_digest": _tool_digest(
                        [{"name": f"{plugin_id}-generation-2", "description": "fixture", "inputSchema": {"type": "object", "properties": {}}}]
                    ),
                }
                for plugin_id in SERVER_IDS
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "CLAUDE_CONFIG_FILE": str(config),
        "CLAUDE_APP_CONTROL": str(controller),
        "ACROSS_INSTALL_COMMANDS_FILE": str(install_commands),
        "EXPECTED_TOOL_DIGESTS_FILE": str(expected),
        "EVIDENCE_PATH": str(evidence),
        "CONTROLLER_LOG": str(controller_log),
        "FAKE_MCP_SERVER": str(server),
        "FAIL_INSTALLER": "across-orchestrator" if failing_installer else "",
        "INJECT_UNRELATED_SERVER": "1" if inject_unrelated_server else "",
    }
    return {
        "config": config,
        "evidence": evidence,
        "controller_log": controller_log,
        "original_bytes": original_bytes,
        "env": env,
    }


def test_reload_script_declares_atomic_backup_restore_and_sanitized_contract() -> None:
    assert SCRIPT.is_file(), "Claude Desktop reload verifier must exist"
    source = SCRIPT.read_text(encoding="utf-8")
    for marker in (
        "CLAUDE_CONFIG_FILE",
        "CLAUDE_APP_CONTROL",
        "ACROSS_INSTALL_COMMANDS_FILE",
        "EXPECTED_TOOL_DIGESTS_FILE",
        "EVIDENCE_PATH",
        "trap",
        "os.replace",
        "across-context",
        "across-orchestrator",
        "across-autopilot",
        "wait-stopped",
        "wait-started",
    ):
        assert marker in source


def test_reload_script_removes_restarts_reinstalls_and_probes_exact_generation(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    completed = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=fixture["env"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    config = json.loads(fixture["config"].read_text(encoding="utf-8"))
    assert config["theme"] == "dark"
    assert config["mcpServers"]["unrelated-server"] == {"command": "/usr/bin/true", "args": []}
    for plugin_id in SERVER_IDS:
        assert config["mcpServers"][plugin_id]["args"][-1] == "2"

    actions = fixture["controller_log"].read_text(encoding="utf-8").splitlines()
    assert actions == [
        "stop:",
        "wait-stopped:",
        "start:",
        "wait-started:",
        "stop:across-autopilot,across-context,across-orchestrator",
        "wait-stopped:across-autopilot,across-context,across-orchestrator",
        "start:across-autopilot,across-context,across-orchestrator",
        "wait-started:across-autopilot,across-context,across-orchestrator",
    ]
    evidence_bytes = fixture["evidence"].read_bytes()
    evidence = json.loads(evidence_bytes)
    assert evidence["status"] == "passed"
    assert evidence["removed"]["all_absent"] is True
    assert evidence["reinstalled"]["all_expected_digests"] is True
    assert set(evidence["reinstalled"]["servers"]) == set(SERVER_IDS)
    assert b"generation-1" not in evidence_bytes
    assert str(tmp_path).encode() not in evidence_bytes
    assert b"sk-" not in evidence_bytes


def test_reload_script_restores_original_bytes_and_restarts_on_failure(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, failing_installer=True)
    completed = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=fixture["env"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode != 0
    assert fixture["config"].read_bytes() == fixture["original_bytes"]
    assert not fixture["evidence"].exists()
    actions = fixture["controller_log"].read_text(encoding="utf-8").splitlines()
    assert actions[-4:] == [
        "stop:across-autopilot,across-context,across-orchestrator",
        "wait-stopped:across-autopilot,across-context,across-orchestrator",
        "start:across-autopilot,across-context,across-orchestrator",
        "wait-started:across-autopilot,across-context,across-orchestrator",
    ]
    assert str(tmp_path) not in completed.stderr
    assert "private" not in completed.stderr.lower()


def test_reload_script_rejects_symlink_config_without_touching_target(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    real_config = fixture["config"]
    real_bytes = real_config.read_bytes()
    linked_config = tmp_path / "linked-claude-config.json"
    linked_config.symlink_to(real_config)
    env = {**fixture["env"], "CLAUDE_CONFIG_FILE": str(linked_config)}

    completed = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode != 0
    assert real_config.read_bytes() == real_bytes
    assert not fixture["controller_log"].exists()
    assert str(tmp_path) not in completed.stderr


def test_reload_script_restores_when_installer_modifies_non_across_registry(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path, inject_unrelated_server=True)
    completed = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=fixture["env"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode != 0
    assert fixture["config"].read_bytes() == fixture["original_bytes"]
    assert not fixture["evidence"].exists()
