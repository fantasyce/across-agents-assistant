import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from across_agents_assistant.api_server import app
from across_agents_assistant.plugin_runtime import discover_across_plugins, inspect_across_plugin


def _write_plugin_manifest(across_home: Path, plugin_id: str, kind: str) -> Path:
    plugin_dir = across_home / "plugins" / plugin_id
    plugin_dir.mkdir(parents=True)
    manifest = {
        "schemaVersion": "1.0",
        "pluginApiVersion": "2026-06-10",
        "id": plugin_id,
        "displayName": "Across Context" if plugin_id == "across-context" else "Across Orchestrator",
        "kind": kind,
        "entrypoints": {"mcp": {"command": plugin_id, "args": ["mcp"]}},
    }
    path = plugin_dir / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _write_fake_command(across_home: Path, name: str) -> Path:
    bin_dir = across_home / "bin"
    bin_dir.mkdir(parents=True)
    path = bin_dir / name
    path.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  plugin-manifest) printf '{\"id\":\"%s\",\"displayName\":\"Fake %s\",\"kind\":\"memory-provider\"}\\n' ;;\n"
        "  plugin-status) printf '{\"status\":\"installed\",\"installed\":true,\"available\":true,\"command\":\"%s\"}\\n' ;;\n"
        "  *) printf '{}\\n' ;;\n"
        "esac\n" % (name, name, path),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def test_discover_across_plugins_reads_manifests_without_probe(tmp_path):
    across_home = tmp_path / "across"
    manifest_path = _write_plugin_manifest(across_home, "across-context", "memory-provider")
    env = {"ACROSS_HOME": str(across_home), "PATH": ""}

    plugins = discover_across_plugins(env=env, probe=False)
    context = next(item for item in plugins if item["plugin_id"] == "across-context")
    orchestrator = next(item for item in plugins if item["plugin_id"] == "across-orchestrator")

    assert context["installed"] is True
    assert context["manifest_path"] == str(manifest_path)
    assert context["manifest"]["pluginApiVersion"] == "2026-06-10"
    assert context["command_exists"] is False
    assert orchestrator["installed"] is False
    assert orchestrator["paths"]["data"] == str(across_home / "data" / "across-orchestrator")


def test_inspect_across_plugin_probe_uses_command_status(tmp_path):
    across_home = tmp_path / "across"
    command_path = _write_fake_command(across_home, "across-context")
    env = {"ACROSS_HOME": str(across_home), "PATH": ""}

    context = inspect_across_plugin("across-context", env=env, probe=True)

    assert context["probe"] is True
    assert context["available"] is True
    assert context["command"] == str(command_path)
    assert context["display_name"] == "Fake across-context"


def test_plugins_api_returns_known_plugins(monkeypatch, tmp_path):
    across_home = tmp_path / "across"
    _write_plugin_manifest(across_home, "across-orchestrator", "task-runtime")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))

    response = TestClient(app).get("/api/plugins")

    assert response.status_code == 200
    plugins = response.json()["plugins"]
    assert {item["plugin_id"] for item in plugins} == {"across-context", "across-orchestrator"}
    orchestrator = next(item for item in plugins if item["plugin_id"] == "across-orchestrator")
    assert orchestrator["installed"] is True
    assert orchestrator["kind"] == "task-runtime"


def test_plugin_api_rejects_unknown_plugin():
    response = TestClient(app).get("/api/plugins/not-real")

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown Across plugin"
