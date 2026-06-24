import json
import os
import subprocess
import sys
from pathlib import Path

from across_agents_assistant.external_agent_plugin_gateway import probe_agent_plugin_runtime_status


PROJECTS_ROOT = Path(__file__).resolve().parents[4]


def test_agent_plugin_runtime_cross_process_e2e(tmp_path):
    manifest = tmp_path / "demo-agent-plugin.json"
    manifest.write_text(json.dumps(_manifest()), encoding="utf-8")
    across_home = tmp_path / "across-home"
    env = os.environ.copy()
    env["ACROSS_HOME"] = str(across_home)
    env["ACROSS_ORCHESTRATOR_HOME"] = str(across_home / "data" / "across-orchestrator")
    env["PYTHONPATH"] = str(PROJECTS_ROOT / "across-orchestrator" / "src")

    context_cli = ["node", str(PROJECTS_ROOT / "across-context" / "src" / "cli.js")]
    registered = subprocess.run(
        [
            sys.executable,
            "-m",
            "across_orchestrator.cli",
            "external-agents",
            "register",
            "--manifest",
            str(manifest),
            "--json",
        ],
        cwd=PROJECTS_ROOT / "across-orchestrator",
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert registered.returncode == 0, registered.stderr

    commands = {
        "orchestrator": [
            sys.executable,
            "-m",
            "across_orchestrator.cli",
            "external-agents",
            "list",
            "--json",
        ],
        "autopilot": [
            "node",
            str(PROJECTS_ROOT / "across-autopilot" / "src" / "cli.js"),
            "ecosystem-roadmap",
            "--agent-plugin-manifest",
            str(manifest),
            "--json",
        ],
        "context": [
            *context_cli,
            "context-packs",
            "--all-projects",
            "--agent-plugin",
            "demo.echo-agent",
            "--json",
        ],
    }

    status = probe_agent_plugin_runtime_status(commands=commands, env=env, timeout_seconds=10)

    assert status["schema_version"] == "across-aaa-agent-plugin-runtime/1.0"
    assert status["status"] == "passed"
    assert status["summary"]["downstream_ready_count"] == 3
    assert status["summary"]["external_agent_count"] == 1
    assert status["summary"]["ready_agent_plugin_count"] == 1
    assert status["summary"]["context_pack_count"] >= 1
    assert status["sections"]["orchestrator_external_agents"]["items"][0]["id"] == "demo.echo-agent"
    assert status["sections"]["autopilot_agent_plugin_runtime"]["items"][0]["context_pack_id"] == "demo.echo"
    assert status["sections"]["context_agent_packs"]["items"][0]["agent_plugin_id"] == "demo.echo-agent"
    assert status["sections"]["context_agent_packs"]["items"][0]["virtual"] is True


def _manifest():
    return {
        "schema_version": "across-agent-plugin/1.0",
        "plugin_id": "demo.echo-agent",
        "display_name": "Demo Echo Agent",
        "version": "1.0.0",
        "agent": {"id": "demo.echo", "name": "Demo Echo", "vendor": "local"},
        "protocols": ["stdio"],
        "capabilities": [{"id": "message.echo", "kind": "tool", "risk": "low"}],
        "entrypoints": {
            "run": {"command": [sys.executable, "-m", "json.tool"], "transport": "stdio"},
        },
        "trust": {
            "mutation_boundary": "read_only",
            "requires_human_approval": False,
            "secrets_included": False,
        },
        "context": {"pack_id": "demo.echo"},
        "health": {"status": "passed", "message": "static test health"},
    }
