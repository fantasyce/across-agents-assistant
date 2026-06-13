import json
import os
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

import across_agents_assistant.api_server as api_server
from across_agents_assistant.api_server import app
from across_agents_assistant.plugin_runtime import (
    discover_across_plugins,
    forget_context_memory,
    inspect_across_plugin,
    list_context_memories,
    remember_context_memory,
    run_context_plugin_lifecycle_action,
    update_context_memory_status,
)


def _write_plugin_manifest(across_home: Path, plugin_id: str, kind: str) -> Path:
    plugin_dir = across_home / "plugins" / plugin_id
    plugin_dir.mkdir(parents=True)
    manifest = {
        "schemaVersion": "1.0",
        "pluginApiVersion": "2026-06-10",
        "id": plugin_id,
        "displayName": "Across Context" if plugin_id == "across-context" else "Across Orchestrator",
        "kind": kind,
        "version": "1.2.3",
        "compatibility": {"requiredHostVersion": ">=0.6.0"},
        "lifecycle": {"actions": ["probe", "install", "repair", "uninstall"]},
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


def _write_fake_context_memory_command(across_home: Path) -> Path:
    bin_dir = across_home / "bin"
    bin_dir.mkdir(parents=True)
    path = bin_dir / "across-context"
    path.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  list) printf '[{\"id\":\"mem_cli_1\",\"scope\":\"global\",\"type\":\"note\",\"text\":\"CLI memory\",\"status\":\"pending\"}]\\n' ;;\n"
        "  remember) printf '{\"memory\":{\"id\":\"mem_cli_2\",\"scope\":\"global\",\"type\":\"note\",\"text\":\"Host apps use plugin CLI.\",\"status\":\"pending\"}}\\n' ;;\n"
        "  update-status) printf '{\"updated\":[{\"id\":\"mem_cli_2\",\"scope\":\"global\",\"type\":\"note\",\"text\":\"Host apps use plugin CLI.\",\"status\":\"active\"}],\"missing\":[]}\\n' ;;\n"
        "  forget) printf '{\"forgotten\":1}\\n' ;;\n"
        "  *) printf '{}\\n' ;;\n"
        "esac\n",
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
    assert context["version"] == "1.2.3"
    assert context["compatibility"]["requiredHostVersion"] == ">=0.6.0"
    assert context["lifecycle"]["actions"] == ["probe", "install", "repair", "upgrade", "uninstall"]
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


def test_inspect_across_plugin_reports_actual_wheel_install_source_from_direct_url(tmp_path):
    across_home = tmp_path / "across"
    _write_plugin_manifest(across_home, "across-orchestrator", "task-runtime")
    plugin_dir = across_home / "plugins" / "across-orchestrator"
    package_path = plugin_dir / "packages" / "across_orchestrator-0.6.1-py3-none-any.whl"
    dist_info = plugin_dir / "venv" / "lib" / "python3.11" / "site-packages" / "across_orchestrator-0.6.1.dist-info"
    package_path.parent.mkdir(parents=True)
    dist_info.mkdir(parents=True)
    package_path.write_text("wheel", encoding="utf-8")
    (dist_info / "direct_url.json").write_text(
        json.dumps({"url": package_path.as_uri(), "archive_info": {"hash": "sha256=abc"}}),
        encoding="utf-8",
    )
    env = {"ACROSS_HOME": str(across_home), "PATH": ""}

    orchestrator = inspect_across_plugin("across-orchestrator", env=env, probe=False)

    assert orchestrator["install"]["source"] == package_path.as_uri()
    assert "github.com/fantasyce/across-orchestrator" not in orchestrator["install"]["source"]


def test_inspect_across_plugin_rejects_wrapper_referencing_documents(tmp_path):
    across_home = tmp_path / "across"
    bin_dir = across_home / "bin"
    bin_dir.mkdir(parents=True)
    marker_path = tmp_path / "wrapper-ran"
    command_path = bin_dir / "across-context"
    command_path.write_text(
        "#!/bin/sh\n"
        f"touch {marker_path}\n"
        "exec /usr/bin/env node 'file:///Users/example/Documents/projects/across-context/src/cli.js' \"$@\"\n",
        encoding="utf-8",
    )
    command_path.chmod(0o755)
    env = {"ACROSS_HOME": str(across_home), "PATH": ""}

    context = inspect_across_plugin("across-context", env=env, probe=True)

    assert context["status"] == "needs_repair"
    assert context["available"] is False
    assert context["integrity_ok"] is False
    assert context["integrity_issues"]
    assert not marker_path.exists()


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


def test_context_plugin_lifecycle_probe_and_uninstall(tmp_path):
    across_home = tmp_path / "across"
    _write_plugin_manifest(across_home, "across-context", "memory-provider")
    command_path = _write_fake_command(across_home, "across-context")
    env = {"ACROSS_HOME": str(across_home), "PATH": ""}

    probed = run_context_plugin_lifecycle_action("probe", env=env)
    assert probed["available"] is True
    assert probed["command"] == str(command_path)

    uninstalled = run_context_plugin_lifecycle_action("uninstall", env=env)
    assert uninstalled["removed"] is True
    assert not command_path.exists()
    assert not (across_home / "plugins" / "across-context").exists()
    assert uninstalled["preserved_data"] == str(across_home / "data" / "across-context")


def test_context_plugin_upgrade_reinstalls_existing_runtime(tmp_path):
    across_home = tmp_path / "across"
    _write_fake_command(across_home, "across-context")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_npm = fake_bin / "npm"
    fake_npm.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_npm.chmod(0o755)
    env = {"ACROSS_HOME": str(across_home), "PATH": str(fake_bin)}
    calls: list[list[str]] = []
    runner_envs: list[dict[str, str]] = []

    def runner(args, **kwargs):
        calls.append([str(item) for item in args])
        runner_envs.append(dict(kwargs.get("env") or {}))
        if args[0] == str(fake_npm):
            prefix = Path(args[args.index("--prefix") + 1])
            command = prefix / "node_modules" / ".bin" / "across-context"
            command.parent.mkdir(parents=True)
            command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            command.chmod(0o755)
        elif Path(args[0]).name == "across-context" and args[1:3] == ["install", "host-plugin"]:
            wrapper = across_home / "bin" / "across-context"
            wrapper.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  plugin-manifest) printf '{\"id\":\"across-context\",\"displayName\":\"Across Context\",\"kind\":\"memory-provider\",\"version\":\"9.9.9\"}\\n' ;;\n"
                "  plugin-status) printf '{\"status\":\"installed\",\"installed\":true,\"available\":true}\\n' ;;\n"
                "  *) printf '{}\\n' ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            wrapper.chmod(0o755)
        return subprocess.CompletedProcess(args, 0, "", "")

    upgraded = run_context_plugin_lifecycle_action("upgrade", env=env, runner=runner)

    assert upgraded["version"] == "9.9.9"
    assert any(call[0] == str(fake_npm) and "install" in call for call in calls)
    assert all(
        item.get("NPM_CONFIG_CACHE") == str(across_home / "cache" / "across-agents-assistant" / "npm")
        for item in runner_envs
    )


def test_context_memory_client_uses_plugin_cli(tmp_path):
    across_home = tmp_path / "across"
    _write_fake_context_memory_command(across_home)
    env = {"ACROSS_HOME": str(across_home), "PATH": ""}

    memories = list_context_memories(status="pending", env=env)
    assert memories[0]["id"] == "mem_cli_1"

    created = remember_context_memory(text="Host apps use plugin CLI.", env=env)
    assert created["id"] == "mem_cli_2"

    updated = update_context_memory_status("mem_cli_2", "active", env=env)
    assert updated["status"] == "active"

    forgotten = forget_context_memory("mem_cli_2", env=env)
    assert forgotten == {"forgotten": True, "id": "mem_cli_2"}


def test_context_memory_pending_review_includes_all_projects(tmp_path):
    across_home = tmp_path / "across"
    bin_dir = across_home / "bin"
    bin_dir.mkdir(parents=True)
    log_path = tmp_path / "argv.txt"
    command_path = bin_dir / "across-context"
    command_path.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" > {log_path}\n"
        "printf '[{\"id\":\"mem_project_1\",\"scope\":\"project\",\"type\":\"session\",\"text\":\"Project memory\",\"status\":\"pending\"}]\\n'\n",
        encoding="utf-8",
    )
    command_path.chmod(0o755)
    env = {"ACROSS_HOME": str(across_home), "PATH": ""}

    memories = list_context_memories(status="pending", env=env)

    assert memories[0]["id"] == "mem_project_1"
    assert "--all-projects" in log_path.read_text(encoding="utf-8")


def test_plugins_action_api_rejects_unsupported_action(monkeypatch, tmp_path):
    monkeypatch.setenv("ACROSS_HOME", str(tmp_path / "across"))
    response = TestClient(app).post("/api/plugins/across-context/actions", json={"action": "explode"})

    assert response.status_code == 400


def test_memory_governance_api_creates_and_updates_pending_memory(monkeypatch, tmp_path):
    monkeypatch.setattr(
        api_server,
        "remember_context_memory",
        lambda **_: {
            "id": "mem_api_1",
            "scope": "global",
            "type": "note",
            "text": "AAA plugin lifecycle E2E should review pending memory.",
            "status": "pending",
        },
    )
    monkeypatch.setattr(
        api_server,
        "list_context_memories",
        lambda **_: [{
            "id": "mem_api_1",
            "scope": "global",
            "type": "note",
            "text": "AAA plugin lifecycle E2E should review pending memory.",
            "status": "pending",
        }],
    )
    monkeypatch.setattr(
        api_server,
        "update_context_memory_status",
        lambda memory_id, status: {
            "id": memory_id,
            "scope": "global",
            "type": "note",
            "text": "AAA plugin lifecycle E2E should review pending memory.",
            "status": status,
        },
    )
    monkeypatch.setattr(
        api_server,
        "forget_context_memory",
        lambda memory_id: {"forgotten": True, "id": memory_id},
    )
    client = TestClient(app)

    created = client.post(
        "/api/memory/remember",
        json={
            "text": "AAA plugin lifecycle E2E should review pending memory.",
            "scope": "global",
            "type": "note",
            "status": "pending",
        },
    )
    assert created.status_code == 200
    memory_id = created.json()["memory"]["id"]

    pending = client.get("/api/memory/memories", params={"status": "pending"})
    assert pending.status_code == 200
    assert [item["id"] for item in pending.json()["memories"]] == [memory_id]

    approved = client.post(f"/api/memory/memories/{memory_id}/status", json={"status": "active"})
    assert approved.status_code == 200
    assert approved.json()["memory"]["status"] == "active"

    forgotten = client.post(f"/api/memory/memories/{memory_id}/forget")
    assert forgotten.status_code == 200
    assert forgotten.json()["forgotten"] is True
