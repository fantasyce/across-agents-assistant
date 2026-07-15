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

from across_agents_assistant.managed_plugin_payloads import (
    ManagedPluginPayloadError,
    ensure_node_runtime,
    extract_plugin_source,
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


def test_managed_payload_installs_verified_node_runtime_and_extracts_package(tmp_path):
    payload_root = tmp_path / "payloads"
    archive, descriptor = _write_node_archive(
        payload_root,
        plugin_id="across-context",
        package_name="@across/context",
        version="0.9.0",
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
        version="0.9.0",
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
    archive = payload_root / "packages" / "across-context-0.9.0.tar.gz"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz") as handle:
        member = tarfile.TarInfo("../escaped.txt")
        content = b"unsafe"
        member.size = len(content)
        handle.addfile(member, io.BytesIO(content))
    descriptor = {
        "version": "0.9.0",
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
        ("across-context", "@across/context", "0.9.0", run_context_plugin_lifecycle_action),
        ("across-autopilot", "@across/autopilot", "0.3.0", run_autopilot_plugin_lifecycle_action),
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


def test_one_click_orchestrator_install_uses_native_payload_and_preserves_data(monkeypatch, tmp_path):
    payload_root = tmp_path / "payloads"
    native = _write_executable(
        payload_root / "runtimes" / "orchestrator-0.8.0" / "across-orchestrator",
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  plugin-manifest) printf '{\"id\":\"across-orchestrator\",\"displayName\":\"Across Orchestrator\",\"kind\":\"task-runtime\",\"version\":\"0.8.0\"}\\n' ;;\n"
        "  plugin-status) printf '{\"status\":\"installed\",\"installed\":true,\"available\":true}\\n' ;;\n"
        "  serve) [ \"$2\" = \"--help\" ] && printf '%s\\n' '  --allow-client-project-roots' ;;\n"
        "  *) printf '{}\\n' ;;\n"
        "esac\n",
    )
    _write_payload_manifest(
        payload_root,
        {
            "across-orchestrator": {
                "version": "0.8.0",
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
    assert status["source"] == "bundle://across-orchestrator/0.8.0"
    assert api_status["install"]["strategy"] == "bundled-native"
    assert api_status["install"]["requires_external_tools"] is False
    assert api_status["manifest"]["lifecycle"]["install"]["strategy"] == "bundled-native"
    assert not (installer.venv_dir / "pyvenv.cfg").exists()
    assert subprocess.run(
        [str(across_home / "bin" / "across-orchestrator"), "plugin-status", "--json"],
        env={**env, "PATH": "/usr/bin:/bin"},
        check=False,
    ).returncode == 0

    removed = installer.uninstall()

    assert removed["removed"] is True
    assert preserved.is_file()


def test_managed_orchestrator_runtime_rejects_missing_client_project_root_contract(tmp_path):
    native = _write_executable(
        tmp_path / "across-orchestrator",
        "#!/bin/sh\n[ \"$1\" = \"serve\" ] && [ \"$2\" = \"--help\" ] && printf '%s\\n' 'usage: serve'\n",
    )

    with pytest.raises(ManagedPluginPayloadError, match="client project roots"):
        validate_orchestrator_runtime_compatibility(native)
