import json
import os
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

import across_agents_assistant.api_server as api_server
import across_agents_assistant.plugin_runtime as plugin_runtime
from across_agents_assistant.api_server import app
from across_agents_assistant.plugin_runtime import (
    discover_across_plugins,
    forget_context_memory,
    get_agent_loop_memory_metrics,
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
        "  loop-memory-metrics) printf '{\"schema_version\":\"agent-loop-memory-metrics/1.0\",\"candidate_schema\":\"agent-loop-memory-candidate/1.0\",\"totals\":{\"candidate_count\":1,\"pending_count\":1},\"metrics\":[{\"id\":\"agent_loop_memory.candidate_count\",\"value\":1}]}\\n' ;;\n"
        "  remember) printf '{\"memory\":{\"id\":\"mem_cli_2\",\"scope\":\"global\",\"type\":\"note\",\"text\":\"Host apps use plugin CLI.\",\"status\":\"pending\"}}\\n' ;;\n"
        "  approve) printf '{\"memory\":{\"id\":\"mem_cli_2\",\"scope\":\"global\",\"type\":\"note\",\"text\":\"Host apps use plugin CLI.\",\"status\":\"active\"}}\\n' ;;\n"
        "  update-status) printf '{\"updated\":[{\"id\":\"mem_cli_2\",\"scope\":\"global\",\"type\":\"note\",\"text\":\"Host apps use plugin CLI.\",\"status\":\"active\"}],\"missing\":[]}\\n' ;;\n"
        "  forget) printf '{\"forgotten\":1}\\n' ;;\n"
        "  *) printf '{}\\n' ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _write_capability_manifest(across_home: Path, plugin_id: str, **overrides) -> Path:
    plugin_dir = across_home / "plugins" / plugin_id
    command = plugin_dir / "bin" / plugin_id
    command.parent.mkdir(parents=True)
    command.write_text("#!/bin/sh\nprintf '{}\\n'\n", encoding="utf-8")
    command.chmod(0o755)
    manifest = {
        "schema_version": "across-capability-manifest/1.0",
        "id": plugin_id,
        "display_name": "Example Capability",
        "version": "1.0.0",
        "kind": "quality-provider",
        "capabilities": [{"id": "repository_review"}],
        "entrypoints": {"cli": {"command": plugin_id, "args": ["review"]}},
        "permissions": {"filesystem": "read"},
        "trust": {"level": "verified"},
        "health": {"status": "ready"},
        "contributed_workflows": ["repo-quality"],
        "optional_ui": None,
    }
    manifest.update(overrides)
    path = plugin_dir / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_discover_across_plugins_reads_manifests_without_probe(tmp_path):
    across_home = tmp_path / "across"
    manifest_path = _write_plugin_manifest(across_home, "across-context", "memory-provider")
    env = {"ACROSS_HOME": str(across_home), "PATH": ""}

    plugins = discover_across_plugins(env=env, probe=False)
    context = next(item for item in plugins if item["plugin_id"] == "across-context")
    orchestrator = next(item for item in plugins if item["plugin_id"] == "across-orchestrator")
    autopilot = next(item for item in plugins if item["plugin_id"] == "across-autopilot")

    assert context["installed"] is True
    assert context["manifest_path"] == str(manifest_path)
    assert context["manifest"]["pluginApiVersion"] == "2026-06-10"
    assert context["version"] == "1.2.3"
    assert context["compatibility"]["requiredHostVersion"] == ">=0.6.0"
    assert context["lifecycle"]["actions"] == ["probe", "install", "repair", "upgrade", "uninstall"]
    assert context["command_exists"] is False
    assert orchestrator["installed"] is False
    assert orchestrator["paths"]["data"] == str(across_home / "data" / "across-orchestrator")
    assert autopilot["installed"] is False
    assert autopilot["kind"] == "autonomous-workflow"
    assert autopilot["paths"]["data"] == str(across_home / "data" / "across-autopilot")
    assert context["manifest"]["schema_version"] == "across-capability-manifest/1.0"
    assert set(("id", "display_name", "version", "kind", "capabilities", "entrypoints", "permissions", "trust", "health", "contributed_workflows", "optional_ui")) <= set(context["manifest"])


def test_discover_across_plugins_finds_unknown_valid_capability_manifest(monkeypatch, tmp_path):
    across_home = tmp_path / "across"
    manifest_path = _write_capability_manifest(across_home, "example-review")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))

    plugins = discover_across_plugins(env={"ACROSS_HOME": str(across_home), "PATH": ""})
    plugin = next(item for item in plugins if item["plugin_id"] == "example-review")

    assert plugin["manifest_path"] == str(manifest_path)
    assert plugin["available"] is True
    assert plugin["install"]["installable"] is False
    assert plugin["capabilities"] == [{"id": "repository_review"}]
    assert plugin["trust"] == {"level": "verified"}
    assert plugin["capability_manifest"] == plugin["manifest"]

    response = TestClient(app).get("/api/plugins")
    assert response.status_code == 200
    api_plugin = next(item for item in response.json()["plugins"] if item["plugin_id"] == "example-review")
    assert api_plugin["capability_manifest"]["schema_version"] == "across-capability-manifest/1.0"
    assert api_plugin["capability_manifest"] == api_plugin["manifest"]


def test_discovery_rejects_invalid_manifest_paths_and_commands(monkeypatch, tmp_path):
    across_home = tmp_path / "across"
    _write_capability_manifest(across_home, "unsafe-path", optional_ui={"path": "../../private.html"})
    _write_capability_manifest(
        across_home,
        "unsafe-command",
        entrypoints={"cli": {"command": "sh -c", "args": ["echo unsafe"]}},
    )
    _write_capability_manifest(
        across_home,
        "unsafe-basename",
        entrypoints={"cli": {"command": "..", "args": []}},
    )
    env = {"ACROSS_HOME": str(across_home), "PATH": ""}
    monkeypatch.setenv("ACROSS_HOME", str(across_home))

    ids = {item["plugin_id"] for item in discover_across_plugins(env=env)}

    assert "unsafe-path" not in ids
    assert "unsafe-command" not in ids
    for plugin_id in ("unsafe-path", "unsafe-command", "unsafe-basename"):
        response = TestClient(app).get(f"/api/plugins/{plugin_id}")
        assert response.status_code == 404
        assert response.json() == {"detail": "Unknown Across plugin"}


def test_managed_manifest_accepts_command_from_shared_across_bin(tmp_path):
    across_home = tmp_path / ".across"
    command = across_home / "bin" / "across-context"
    command.parent.mkdir(parents=True)
    command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    command.chmod(0o755)
    plugin_dir = across_home / "plugins" / "across-context"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "manifest.json").write_text(json.dumps({
        "schemaVersion": "1.0",
        "id": "across-context",
        "displayName": "Across Context",
        "kind": "memory-provider",
        "entrypoints": {"cli": {"command": "~/.across/bin/across-context"}},
        "capabilities": {"memory": True},
        "permissions": {},
    }), encoding="utf-8")

    status = inspect_across_plugin(
        "across-context",
        env={"ACROSS_HOME": str(across_home), "HOME": str(tmp_path), "PATH": ""},
    )

    assert status["integrity_ok"] is True
    assert status["capabilities"]["memory"] is True


def test_invalid_first_party_manifest_keeps_managed_plugin_in_repair_state(tmp_path):
    across_home = tmp_path / "across"
    _write_plugin_manifest(across_home, "across-context", "memory-provider")
    manifest_path = across_home / "plugins" / "across-context" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["entrypoints"] = {"cli": {"command": "sh -c"}}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    plugins = discover_across_plugins(env={"ACROSS_HOME": str(across_home), "PATH": ""})
    context = next(item for item in plugins if item["plugin_id"] == "across-context")

    assert context["status"] == "needs_repair"
    assert context["integrity_ok"] is False
    assert context["manifest"]["schema_version"] == "across-capability-manifest/1.0"


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


def test_inspect_across_plugin_rejects_stale_bundled_native_runtime(monkeypatch, tmp_path):
    across_home = tmp_path / "across"
    _write_plugin_manifest(across_home, "across-orchestrator", "task-runtime")
    plugin_dir = across_home / "plugins" / "across-orchestrator"
    executable = plugin_dir / "venv" / "bin" / "across-orchestrator"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"installed runtime")
    executable.chmod(0o755)
    command = _write_fake_command(across_home, "across-orchestrator")
    (plugin_dir / "install-state.json").write_text(
        json.dumps({"runtime": "bundled_native", "sha256": "0" * 64}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        plugin_runtime,
        "plugin_payload",
        lambda plugin_id, env: {
            "runtime": "native",
            "version": "0.9.0",
            "commit": "abc123",
            "sha256": "1" * 64,
        },
    )

    orchestrator = inspect_across_plugin(
        "across-orchestrator",
        env={"ACROSS_HOME": str(across_home), "PATH": ""},
        probe=True,
    )

    assert orchestrator["command"] == str(command)
    assert orchestrator["status"] == "needs_repair"
    assert orchestrator["available"] is False
    assert orchestrator["integrity_ok"] is False
    assert any("differs from the bundled version" in issue for issue in orchestrator["integrity_issues"])


def test_inspect_across_plugin_accepts_matching_bundled_native_runtime(monkeypatch, tmp_path):
    across_home = tmp_path / "across"
    _write_plugin_manifest(across_home, "across-orchestrator", "task-runtime")
    plugin_dir = across_home / "plugins" / "across-orchestrator"
    executable = plugin_dir / "venv" / "bin" / "across-orchestrator"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"installed runtime")
    executable.chmod(0o755)
    _write_fake_command(across_home, "across-orchestrator")
    expected_sha256 = plugin_runtime._sha256_file(executable)
    (plugin_dir / "install-state.json").write_text(
        json.dumps({"runtime": "bundled_native", "sha256": expected_sha256}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        plugin_runtime,
        "plugin_payload",
        lambda plugin_id, env: {
            "runtime": "native",
            "version": "0.9.0",
            "commit": "abc123",
            "sha256": expected_sha256,
        },
    )

    orchestrator = inspect_across_plugin(
        "across-orchestrator",
        env={"ACROSS_HOME": str(across_home), "PATH": ""},
        probe=True,
    )

    assert orchestrator["status"] == "installed"
    assert orchestrator["available"] is True
    assert orchestrator["integrity_ok"] is True


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


def test_inspect_across_plugin_rejects_stale_orchestrator_aaa_source_tree(tmp_path):
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-orchestrator"
    stale_source = plugin_dir / "source" / "src" / "across_agents_assistant" / "__init__.py"
    bin_dir = across_home / "bin"
    marker_path = tmp_path / "orchestrator-ran"
    _write_plugin_manifest(across_home, "across-orchestrator", "task-runtime")
    stale_source.parent.mkdir(parents=True)
    bin_dir.mkdir(parents=True)
    stale_source.write_text("# old AAA runtime namespace\n", encoding="utf-8")
    command_path = bin_dir / "across-orchestrator"
    command_path.write_text(
        "#!/bin/sh\n"
        f"touch {marker_path}\n"
        "printf '{\"status\":\"installed\",\"installed\":true,\"available\":true}\\n'\n",
        encoding="utf-8",
    )
    command_path.chmod(0o755)
    env = {"ACROSS_HOME": str(across_home), "PATH": ""}

    orchestrator = inspect_across_plugin("across-orchestrator", env=env, probe=True)

    assert orchestrator["status"] == "needs_repair"
    assert orchestrator["available"] is False
    assert orchestrator["integrity_ok"] is False
    assert any("stale Across Agents Assistant source" in issue for issue in orchestrator["integrity_issues"])
    assert not marker_path.exists()


def test_inspect_across_plugin_rejects_orchestrator_editable_direct_url(tmp_path):
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-orchestrator"
    dist_info = plugin_dir / "venv" / "lib" / "python3.11" / "site-packages" / "across_orchestrator-0.6.2.dist-info"
    bin_dir = across_home / "bin"
    marker_path = tmp_path / "orchestrator-ran"
    _write_plugin_manifest(across_home, "across-orchestrator", "task-runtime")
    dist_info.mkdir(parents=True)
    bin_dir.mkdir(parents=True)
    (dist_info / "direct_url.json").write_text(
        json.dumps({
            "url": "file:///Users/example/Documents/projects/across-orchestrator",
            "dir_info": {"editable": True},
        }),
        encoding="utf-8",
    )
    command_path = bin_dir / "across-orchestrator"
    command_path.write_text(
        "#!/bin/sh\n"
        f"touch {marker_path}\n"
        "printf '{\"status\":\"installed\",\"installed\":true,\"available\":true}\\n'\n",
        encoding="utf-8",
    )
    command_path.chmod(0o755)
    env = {"ACROSS_HOME": str(across_home), "PATH": ""}

    orchestrator = inspect_across_plugin("across-orchestrator", env=env, probe=True)

    assert orchestrator["status"] == "needs_repair"
    assert orchestrator["available"] is False
    assert orchestrator["integrity_ok"] is False
    assert any("editable install" in issue for issue in orchestrator["integrity_issues"])
    assert not marker_path.exists()


def test_plugins_api_returns_known_plugins(monkeypatch, tmp_path):
    across_home = tmp_path / "across"
    _write_plugin_manifest(across_home, "across-orchestrator", "task-runtime")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))

    response = TestClient(app).get("/api/plugins")

    assert response.status_code == 200
    plugins = response.json()["plugins"]
    assert {item["plugin_id"] for item in plugins} == {"across-context", "across-orchestrator", "across-autopilot"}
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

    metrics = get_agent_loop_memory_metrics(env=env)
    assert metrics["schema_version"] == "agent-loop-memory-metrics/1.0"
    assert metrics["totals"]["pending_count"] == 1


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


def test_context_agent_loop_memory_metrics_includes_all_projects(tmp_path):
    across_home = tmp_path / "across"
    bin_dir = across_home / "bin"
    bin_dir.mkdir(parents=True)
    log_path = tmp_path / "argv.txt"
    command_path = bin_dir / "across-context"
    command_path.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" > {log_path}\n"
        "printf '{\"schema_version\":\"agent-loop-memory-metrics/1.0\",\"totals\":{\"candidate_count\":2,\"pending_count\":1}}\\n'\n",
        encoding="utf-8",
    )
    command_path.chmod(0o755)
    env = {"ACROSS_HOME": str(across_home), "PATH": ""}

    metrics = get_agent_loop_memory_metrics(env=env)

    assert metrics["totals"]["candidate_count"] == 2
    argv = log_path.read_text(encoding="utf-8")
    assert "loop-memory-metrics" in argv
    assert "--all-projects" in argv


def test_plugins_action_api_rejects_unsupported_action(monkeypatch, tmp_path):
    monkeypatch.setenv("ACROSS_HOME", str(tmp_path / "across"))
    response = TestClient(app).post("/api/plugins/across-context/actions", json={"action": "explode"})

    assert response.status_code == 400


def test_plugins_action_api_runs_one_click_context_install(monkeypatch, tmp_path):
    calls: list[str] = []
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-context"
    wrapper = across_home / "bin" / "across-context"
    monkeypatch.setenv("ACROSS_HOME", str(across_home))

    def install(action: str):
        calls.append(action)
        plugin_dir.mkdir(parents=True)
        wrapper.parent.mkdir(parents=True)
        (plugin_dir / "runtime.txt").write_text("installed\n", encoding="utf-8")
        wrapper.write_text("wrapper\n", encoding="utf-8")
        return {
            "plugin_id": "across-context",
            "status": "installed",
            "installed": True,
            "available": True,
            "integrity_ok": True,
            "probe": True,
        }

    monkeypatch.setattr(api_server, "run_context_plugin_lifecycle_action", install)
    monkeypatch.setattr(
        api_server,
        "get_agent_loop_memory_metrics",
        lambda: {
            "schema_version": "agent-loop-memory-metrics/1.0",
            "totals": {"candidate_count": 0, "pending_count": 0},
        },
    )

    response = TestClient(app).post(
        "/api/plugins/across-context/actions",
        json={"action": "install"},
    )

    assert response.status_code == 200
    assert response.json()["available"] is True
    assert calls == ["install"]


def test_plugins_action_api_reconciles_worker_runtime_after_orchestrator_repair(monkeypatch, tmp_path):
    calls: list[str] = []
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-orchestrator"
    wrapper = across_home / "bin" / "across-orchestrator"
    monkeypatch.setenv("ACROSS_HOME", str(across_home))

    class FakeManager:
        def reset_runtime_connection(self):
            calls.append("manager-reset")

        def install_plugin(self):
            calls.append("install")
            plugin_dir.mkdir(parents=True)
            wrapper.parent.mkdir(parents=True)
            (plugin_dir / "runtime.txt").write_text("installed\n", encoding="utf-8")
            wrapper.write_text("wrapper\n", encoding="utf-8")
            return {"status": "installed", "installed": True, "integrity_ok": True}

        def implementation_status(self, probe: bool = True):
            assert probe is True
            calls.append("status")
            return {
                "implementation": "external",
                "available": True,
                "install": {"installed": True, "integrity_ok": True},
            }

    class FakeWorkerRuntime:
        def shutdown(self):
            calls.append("worker-shutdown")

        def reconcile(self):
            calls.append("worker-reconcile")
            return {"status": "running", "listener_pid": 42}

    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakeManager())
    monkeypatch.setattr(api_server, "get_worker_network_runtime", lambda: FakeWorkerRuntime())

    response = TestClient(app).post(
        "/api/plugins/across-orchestrator/actions",
        json={"action": "repair"},
    )

    assert response.status_code == 200
    assert response.json()["worker_runtime"]["listener_pid"] == 42
    assert calls == ["worker-shutdown", "manager-reset", "install", "status", "worker-reconcile"]


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
        "get_agent_loop_memory_metrics",
        lambda **_: {
            "schema_version": "agent-loop-memory-metrics/1.0",
            "candidate_schema": "agent-loop-memory-candidate/1.0",
            "totals": {"candidate_count": 1, "pending_count": 1},
            "metrics": [{"id": "agent_loop_memory.candidate_count", "value": 1}],
        },
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

    metrics = client.get("/api/memory/agent-loop-metrics")
    assert metrics.status_code == 200
    assert metrics.json()["totals"]["pending_count"] == 1

    approved = client.post(f"/api/memory/memories/{memory_id}/status", json={"status": "active"})
    assert approved.status_code == 200
    assert approved.json()["memory"]["status"] == "active"

    forgotten = client.post(f"/api/memory/memories/{memory_id}/forget")
    assert forgotten.status_code == 200
    assert forgotten.json()["forgotten"] is True
