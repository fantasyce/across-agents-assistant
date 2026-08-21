from __future__ import annotations

from pathlib import Path
import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile

import pytest
from fastapi.testclient import TestClient

import across_agents_assistant.api_server as api_server

from across_agents_assistant.managed_plugin_payloads import (
    ManagedPluginPayloadError,
    ensure_node_runtime,
    extract_plugin_source,
    plugin_payload,
    validate_orchestrator_runtime_compatibility,
)
from across_agents_assistant.orchestrator_plugin import OrchestratorPluginInstaller
from across_agents_assistant.plugin_runtime import (
    inspect_across_plugin,
    run_autopilot_plugin_lifecycle_action,
    run_context_plugin_lifecycle_action,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_executable(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)
    return path


def _write_node_archive(
    payload_root: Path,
    *,
    plugin_id: str,
    package_name: str,
    version: str,
) -> tuple[Path, dict]:
    source_root = payload_root.parent / f"source-{plugin_id}" / f"{plugin_id}-{version}"
    cli = source_root / "src" / "cli.js"
    cli.parent.mkdir(parents=True, exist_ok=True)
    cli.write_text("// managed plugin fixture\n", encoding="utf-8")
    (source_root / "package.json").write_text(
        json.dumps({"name": package_name, "version": version, "type": "module"}),
        encoding="utf-8",
    )
    archive = payload_root / "packages" / f"{plugin_id}-{version}.tar.gz"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(source_root, arcname=source_root.name)
    return archive, {
        "version": version,
        "commit": "a" * 40,
        "runtime": "node",
        "archive": str(archive.relative_to(payload_root)),
        "sha256": _sha256(archive),
        "metadata": "package.json",
        "package_name": package_name,
        "entrypoint": "src/cli.js",
    }


def _write_payload_manifest(payload_root: Path, plugins: dict) -> Path:
    fake_node = _write_executable(
        payload_root / "runtimes" / "node-22.17.1" / "bin" / "node",
        "#!/bin/sh\n"
        "case \"$2\" in\n"
        "  plugin-manifest) printf '{\"id\":\"%s\",\"displayName\":\"Managed Fixture\",\"kind\":\"memory-provider\",\"version\":\"1.0.0\"}\\n' \"$(basename \"$(dirname \"$(dirname \"$1\")\")\")\" ;;\n"
        "  plugin-status) printf '{\"status\":\"installed\",\"installed\":true,\"available\":true}\\n' ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n",
    )
    payload = {
        "schema_version": "across-managed-plugin-payloads/1.0",
        "platform": "macos",
        "architecture": "fixture",
        "runtimes": {
            "node": {
                "version": "22.17.1",
                "path": "runtimes/node-22.17.1",
                "executable": "bin/node",
                "sha256": _sha256(fake_node),
            }
        },
        "plugins": plugins,
    }
    path = payload_root / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _managed_env(tmp_path: Path, payload_root: Path) -> dict[str, str]:
    return {
        "HOME": str(tmp_path / "home"),
        "ACROSS_HOME": str(tmp_path / "home" / ".across"),
        "ACROSS_AGENTS_DEVELOPER_MODE": "1",
        "ACROSS_AGENTS_PLUGIN_PAYLOAD_ROOT": str(payload_root),
        "PATH": "/usr/bin:/bin",
    }


def test_promotion_descriptors_cover_exactly_three_plugins_without_checkout_paths(tmp_path):
    payload_root = tmp_path / "payloads"
    plugins = {
        "across-context": {
            "version": "0.11.0",
            "commit": "a" * 40,
            "runtime": "node",
            "archive": "packages/across-context-0.11.0.tar.gz",
            "sha256": "1" * 64,
        },
        "across-orchestrator": {
            "version": "0.10.7",
            "commit": "b" * 40,
            "runtime": "native",
            "executable": "runtimes/orchestrator-0.10.7/across-orchestrator",
            "sha256": "2" * 64,
            "source_sha256": "3" * 64,
        },
        "across-autopilot": {
            "version": "0.5.3",
            "commit": "c" * 40,
            "runtime": "node",
            "archive": "packages/across-autopilot-0.5.3.tar.gz",
            "sha256": "4" * 64,
        },
    }
    manifest_path = _write_payload_manifest(payload_root, plugins)
    env = _managed_env(tmp_path, payload_root)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_ids = {
        "across-context",
        "across-orchestrator",
        "across-autopilot",
    }
    assert set(manifest["plugins"]) == expected_ids

    descriptors = {
        plugin_id: plugin_payload(plugin_id, env)
        for plugin_id in expected_ids
    }
    assert all(descriptor is not None for descriptor in descriptors.values())
    assert {plugin_id for plugin_id, descriptor in descriptors.items() if descriptor} == expected_ids
    for descriptor in descriptors.values():
        public_descriptor = {key: value for key, value in descriptor.items() if key != "payload_root"}
        serialized = json.dumps(public_descriptor, sort_keys=True)
        assert "source_root" not in public_descriptor
        assert "checkout" not in serialized.lower()
        assert "/Users/" not in serialized
        assert "../" not in serialized


def test_managed_payload_installs_verified_node_runtime_and_extracts_package(tmp_path):
    payload_root = tmp_path / "payloads"
    archive, descriptor = _write_node_archive(
        payload_root,
        plugin_id="across-context",
        package_name="@across/context",
        version="0.11.0",
    )
    _write_payload_manifest(payload_root, {"across-context": descriptor})
    env = _managed_env(tmp_path, payload_root)
    across_home = Path(env["ACROSS_HOME"])

    node = ensure_node_runtime(across_home, env)
    source = extract_plugin_source("across-context", across_home / "cache" / "installer", env)

    assert node == across_home / "runtimes" / "node-22.17.1" / "bin" / "node"
    assert os.access(node, os.X_OK)
    assert (source / "package.json").is_file()
    assert _sha256(archive) == descriptor["sha256"]


def test_managed_payload_rejects_checksum_mismatch(tmp_path):
    payload_root = tmp_path / "payloads"
    _archive, descriptor = _write_node_archive(
        payload_root,
        plugin_id="across-context",
        package_name="@across/context",
        version="0.11.0",
    )
    descriptor["sha256"] = "0" * 64
    _write_payload_manifest(payload_root, {"across-context": descriptor})

    with pytest.raises(ManagedPluginPayloadError, match="checksum"):
        extract_plugin_source(
            "across-context",
            tmp_path / "destination",
            _managed_env(tmp_path, payload_root),
        )


def test_managed_payload_rejects_archive_path_traversal(tmp_path):
    payload_root = tmp_path / "payloads"
    archive = payload_root / "packages" / "across-context-0.11.0.tar.gz"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz") as handle:
        member = tarfile.TarInfo("../escaped.txt")
        content = b"unsafe"
        member.size = len(content)
        handle.addfile(member, io.BytesIO(content))
    descriptor = {
        "version": "0.11.0",
        "commit": "a" * 40,
        "runtime": "node",
        "archive": str(archive.relative_to(payload_root)),
        "sha256": _sha256(archive),
        "metadata": "package.json",
        "package_name": "@across/context",
        "entrypoint": "src/cli.js",
    }
    _write_payload_manifest(payload_root, {"across-context": descriptor})

    with pytest.raises(ManagedPluginPayloadError, match="unsafe path"):
        extract_plugin_source(
            "across-context",
            tmp_path / "destination",
            _managed_env(tmp_path, payload_root),
        )

    assert not (tmp_path / "escaped.txt").exists()


@pytest.mark.parametrize(
    ("plugin_id", "package_name", "version", "install"),
    [
        ("across-context", "@across/context", "0.11.0", run_context_plugin_lifecycle_action),
        ("across-autopilot", "@across/autopilot", "0.5.2", run_autopilot_plugin_lifecycle_action),
    ],
)
def test_one_click_node_install_does_not_require_npm_or_git(
    tmp_path,
    plugin_id,
    package_name,
    version,
    install,
):
    payload_root = tmp_path / "payloads"
    _archive, descriptor = _write_node_archive(
        payload_root,
        plugin_id=plugin_id,
        package_name=package_name,
        version=version,
    )
    _write_payload_manifest(payload_root, {plugin_id: descriptor})
    env = _managed_env(tmp_path, payload_root)
    across_home = Path(env["ACROSS_HOME"])
    calls: list[list[str]] = []
    legacy_wrapper = _write_executable(
        across_home / "bin" / plugin_id,
        "#!/bin/sh\nexec /usr/bin/env node /tmp/legacy.js \"$@\"\n",
    )
    assert "/usr/bin/env node" in legacy_wrapper.read_text(encoding="utf-8")

    def runner(args, **_kwargs):
        calls.append([str(item) for item in args])
        source_root = Path(args[1]).parent.parent
        install_dir = across_home / "plugins" / plugin_id
        shutil.copytree(source_root, install_dir, dirs_exist_ok=True)
        (install_dir / "manifest.json").write_text(
            json.dumps({
                "id": plugin_id,
                "displayName": "Managed Fixture",
                "kind": "memory-provider" if plugin_id == "across-context" else "autonomous-workflow",
                "version": version,
            }),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args, 0, "", "")

    status = install("install", env=env, runner=runner)
    wrapper = across_home / "bin" / plugin_id
    wrapper_text = wrapper.read_text(encoding="utf-8")

    assert status["installed"] is True
    assert status["available"] is True
    assert status["integrity_ok"] is True
    assert status["install"]["strategy"] == "bundled-node"
    assert status["install"]["requires_external_tools"] is False
    assert status["manifest"]["lifecycle"]["install"]["strategy"] == "bundled-node"
    assert calls and calls[0][0].endswith("runtimes/node-22.17.1/bin/node")
    assert all("npm" not in call and "git" not in call for call in calls)
    assert "../runtimes/node-22.17.1/bin/node" in wrapper_text
    assert "/usr/bin/env node" not in wrapper_text
    provenance_path = across_home / "plugins" / plugin_id / ".across-managed-plugin.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert provenance == {
        "schema_version": "across-managed-plugin-install/1.0",
        "plugin_id": plugin_id,
        "version": version,
        "commit": descriptor["commit"],
        "sha256": descriptor["sha256"],
    }

    provenance["sha256"] = "0" * 64
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
    drifted = inspect_across_plugin(plugin_id, probe=True, env=env)

    assert drifted["status"] == "needs_repair"
    assert drifted["integrity_ok"] is False
    assert drifted["available"] is False
    assert any("differs from the bundled version" in issue for issue in drifted["integrity_issues"])


@pytest.mark.parametrize(
    ("plugin_id", "package_name", "version_a", "version_b", "lifecycle"),
    [
        (
            "across-context",
            "@across/context",
            "0.11.0",
            "0.11.1",
            run_context_plugin_lifecycle_action,
        ),
        (
            "across-autopilot",
            "@across/autopilot",
            "0.5.2",
            "0.5.3",
            run_autopilot_plugin_lifecycle_action,
        ),
    ],
)
def test_managed_node_lifecycle_repairs_upgrades_and_uninstalls_without_deleting_data(
    tmp_path,
    plugin_id,
    package_name,
    version_a,
    version_b,
    lifecycle,
):
    payload_a = tmp_path / "payload-a"
    _archive_a, descriptor_a = _write_node_archive(
        payload_a,
        plugin_id=plugin_id,
        package_name=package_name,
        version=version_a,
    )
    _write_payload_manifest(payload_a, {plugin_id: descriptor_a})
    env_a = _managed_env(tmp_path, payload_a)
    across_home = Path(env_a["ACROSS_HOME"])
    data_file = across_home / "data" / plugin_id / "keep.json"
    data_file.parent.mkdir(parents=True, exist_ok=True)
    data_file.write_text("preserved\n", encoding="utf-8")

    def runner(args, **_kwargs):
        source_root = Path(args[1]).parent.parent
        install_dir = across_home / "plugins" / plugin_id
        shutil.rmtree(install_dir, ignore_errors=True)
        shutil.copytree(source_root, install_dir)
        package = json.loads((source_root / "package.json").read_text(encoding="utf-8"))
        (install_dir / "manifest.json").write_text(
            json.dumps({
                "id": plugin_id,
                "displayName": "Managed Fixture",
                "kind": "memory-provider" if plugin_id == "across-context" else "autonomous-workflow",
                "version": package["version"],
            }),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args, 0, "", "")

    installed = lifecycle("install", env=env_a, runner=runner)
    marker_path = across_home / "plugins" / plugin_id / ".across-managed-plugin.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert installed["integrity_ok"] is True
    assert marker["version"] == version_a

    marker["sha256"] = "0" * 64
    marker_path.write_text(json.dumps(marker), encoding="utf-8")
    repaired = lifecycle("repair", env=env_a, runner=runner)
    repaired_marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert repaired["integrity_ok"] is True
    assert repaired_marker["sha256"] == descriptor_a["sha256"]

    payload_b = tmp_path / "payload-b"
    _archive_b, descriptor_b = _write_node_archive(
        payload_b,
        plugin_id=plugin_id,
        package_name=package_name,
        version=version_b,
    )
    descriptor_b["commit"] = "b" * 40
    _write_payload_manifest(payload_b, {plugin_id: descriptor_b})
    env_b = _managed_env(tmp_path, payload_b)
    upgraded = lifecycle("upgrade", env=env_b, runner=runner)
    upgraded_marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert upgraded["integrity_ok"] is True
    assert upgraded_marker["version"] == version_b
    assert upgraded_marker["commit"] == "b" * 40
    assert upgraded_marker["sha256"] == descriptor_b["sha256"]

    removed = lifecycle("uninstall", env=env_b, runner=runner)
    assert removed["removed"] is True
    assert not (across_home / "plugins" / plugin_id).exists()
    assert not (across_home / "bin" / plugin_id).exists()
    assert data_file.read_text(encoding="utf-8") == "preserved\n"


def test_autopilot_real_payload_lifecycle_runs_through_api_transaction(monkeypatch, tmp_path):
    plugin_id = "across-autopilot"
    payload_a = tmp_path / "payload-a"
    _archive_a, descriptor_a = _write_node_archive(
        payload_a,
        plugin_id=plugin_id,
        package_name="@across/autopilot",
        version="0.5.2",
    )
    _write_payload_manifest(payload_a, {plugin_id: descriptor_a})
    env_a = _managed_env(tmp_path, payload_a)
    for key, value in env_a.items():
        monkeypatch.setenv(key, value)
    across_home = Path(env_a["ACROSS_HOME"])
    data_file = across_home / "data" / plugin_id / "keep.json"
    data_file.parent.mkdir(parents=True, exist_ok=True)
    data_file.write_text("preserved\n", encoding="utf-8")

    def runner(args, **_kwargs):
        source_root = Path(args[1]).parent.parent
        install_dir = across_home / "plugins" / plugin_id
        shutil.rmtree(install_dir, ignore_errors=True)
        shutil.copytree(source_root, install_dir)
        package = json.loads((source_root / "package.json").read_text(encoding="utf-8"))
        (install_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "id": plugin_id,
                    "displayName": "Managed Fixture",
                    "kind": "autonomous-workflow",
                    "version": package["version"],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args, 0, "", "")

    class StoppedScheduler:
        def status(self):
            return {"running": False}

    monkeypatch.setattr(api_server, "get_autopilot_trigger_scheduler", lambda: StoppedScheduler())
    monkeypatch.setattr(
        api_server,
        "run_autopilot_plugin_lifecycle_action",
        lambda action: run_autopilot_plugin_lifecycle_action(
            action,
            env=os.environ,
            runner=runner,
        ),
    )
    client = TestClient(api_server.app)

    installed = client.post(
        "/api/plugins/across-autopilot/actions",
        json={"action": "install"},
    )
    assert installed.status_code == 200
    marker_path = across_home / "plugins" / plugin_id / ".across-managed-plugin.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    assert marker["version"] == "0.5.2"

    marker["sha256"] = "0" * 64
    marker_path.write_text(json.dumps(marker), encoding="utf-8")
    repaired = client.post(
        "/api/plugins/across-autopilot/actions",
        json={"action": "repair"},
    )
    assert repaired.status_code == 200
    assert json.loads(marker_path.read_text(encoding="utf-8"))["sha256"] == descriptor_a["sha256"]

    payload_b = tmp_path / "payload-b"
    _archive_b, descriptor_b = _write_node_archive(
        payload_b,
        plugin_id=plugin_id,
        package_name="@across/autopilot",
        version="0.5.3",
    )
    descriptor_b["commit"] = "b" * 40
    _write_payload_manifest(payload_b, {plugin_id: descriptor_b})
    monkeypatch.setenv("ACROSS_AGENTS_PLUGIN_PAYLOAD_ROOT", str(payload_b))
    upgraded = client.post(
        "/api/plugins/across-autopilot/actions",
        json={"action": "upgrade"},
    )
    assert upgraded.status_code == 200
    assert json.loads(marker_path.read_text(encoding="utf-8"))["version"] == "0.5.3"

    removed = client.post(
        "/api/plugins/across-autopilot/actions",
        json={"action": "uninstall"},
    )
    assert removed.status_code == 200
    assert not (across_home / "plugins" / plugin_id).exists()
    assert not (across_home / "bin" / plugin_id).exists()
    assert data_file.read_text(encoding="utf-8") == "preserved\n"


def test_one_click_orchestrator_install_uses_native_payload_and_preserves_data(monkeypatch, tmp_path):
    payload_root = tmp_path / "payloads"
    native = _write_executable(
        payload_root / "runtimes" / "orchestrator-0.10.5" / "across-orchestrator",
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  plugin-manifest) printf '{\"id\":\"across-orchestrator\",\"displayName\":\"Across Orchestrator\",\"kind\":\"task-runtime\",\"version\":\"0.10.5\"}\\n' ;;\n"
        "  plugin-status) printf '{\"status\":\"installed\",\"installed\":true,\"available\":true}\\n' ;;\n"
        "  serve) [ \"$2\" = \"--help\" ] && printf '%s\\n' '  --allow-client-project-roots' ;;\n"
        "  *) printf '{}\\n' ;;\n"
        "esac\n",
    )
    _write_payload_manifest(
        payload_root,
        {
            "across-orchestrator": {
                "version": "0.10.5",
                "commit": "b" * 40,
                "runtime": "native",
                "executable": str(native.relative_to(payload_root)),
                "sha256": _sha256(native),
            }
        },
    )
    env = _managed_env(tmp_path, payload_root)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    across_home = Path(env["ACROSS_HOME"])
    preserved = across_home / "data" / "across-orchestrator" / "keep.json"
    preserved.parent.mkdir(parents=True, exist_ok=True)
    preserved.write_text("{}", encoding="utf-8")

    installer = OrchestratorPluginInstaller(plugin_home=across_home / "plugins")
    status = installer.install()
    api_status = inspect_across_plugin(
        "across-orchestrator",
        env=env,
        probe=True,
    )

    assert status["installed"] is True
    assert status["integrity_ok"] is True
    assert status["runtime"] == "bundled_native"
    assert status["python"] is None
    assert status["source"] == "bundle://across-orchestrator/0.10.5"
    assert api_status["install"]["strategy"] == "bundled-native"
    assert api_status["install"]["requires_external_tools"] is False
    assert api_status["manifest"]["lifecycle"]["install"]["strategy"] == "bundled-native"
    assert not (installer.venv_dir / "pyvenv.cfg").exists()
    assert subprocess.run(
        [str(across_home / "bin" / "across-orchestrator"), "plugin-status", "--json"],
        env={**env, "PATH": "/usr/bin:/bin"},
        check=False,
    ).returncode == 0

    installer.command_path.write_text("corrupted\n", encoding="utf-8")
    installer.command_path.chmod(0o755)
    assert installer.status()["integrity_ok"] is False
    repaired = installer.install()
    assert repaired["integrity_ok"] is True
    assert repaired["source"] == "bundle://across-orchestrator/0.10.5"

    upgraded_native = _write_executable(
        payload_root / "runtimes" / "orchestrator-0.10.6" / "across-orchestrator",
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  plugin-manifest) printf '{\"id\":\"across-orchestrator\",\"displayName\":\"Across Orchestrator\",\"kind\":\"task-runtime\",\"version\":\"0.10.6\"}\\n' ;;\n"
        "  plugin-status) printf '{\"status\":\"installed\",\"installed\":true,\"available\":true}\\n' ;;\n"
        "  serve) [ \"$2\" = \"--help\" ] && printf '%s\\n' '  --allow-client-project-roots' ;;\n"
        "  *) printf '{}\\n' ;;\n"
        "esac\n",
    )
    _write_payload_manifest(
        payload_root,
        {
            "across-orchestrator": {
                "version": "0.10.6",
                "commit": "c" * 40,
                "runtime": "native",
                "executable": str(upgraded_native.relative_to(payload_root)),
                "sha256": _sha256(upgraded_native),
            }
        },
    )
    upgraded_installer = OrchestratorPluginInstaller(plugin_home=across_home / "plugins")
    upgraded = upgraded_installer.install()
    assert upgraded["integrity_ok"] is True
    assert upgraded["source"] == "bundle://across-orchestrator/0.10.6"
    assert json.loads(upgraded_installer.state_path.read_text(encoding="utf-8"))["sha256"] == _sha256(upgraded_native)

    removed = upgraded_installer.uninstall()

    assert removed["removed"] is True
    assert preserved.is_file()


def test_managed_orchestrator_runtime_rejects_missing_client_project_root_contract(tmp_path):
    native = _write_executable(
        tmp_path / "across-orchestrator",
        "#!/bin/sh\n[ \"$1\" = \"serve\" ] && [ \"$2\" = \"--help\" ] && printf '%s\\n' 'usage: serve'\n",
    )

    with pytest.raises(ManagedPluginPayloadError, match="client project roots"):
        validate_orchestrator_runtime_compatibility(native)


def test_managed_orchestrator_runtime_allows_frozen_binary_cold_start():
    observed = {}

    def runner(args, **kwargs):
        observed["args"] = args
        observed["timeout"] = kwargs["timeout"]
        return subprocess.CompletedProcess(
            args,
            0,
            stdout="usage: serve --allow-client-project-roots",
            stderr="",
        )

    validate_orchestrator_runtime_compatibility(
        Path("/private/tmp/across-orchestrator"),
        runner=runner,
    )

    assert observed["args"][-2:] == ["serve", "--help"]
    assert observed["timeout"] == 60
