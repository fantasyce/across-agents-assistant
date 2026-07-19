from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Mapping
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import uuid

from .runtime_boundary import is_developer_mode


PAYLOAD_SCHEMA = "across-managed-plugin-payloads/1.0"
_MAX_MANIFEST_BYTES = 1024 * 1024
_MAX_ARCHIVE_FILES = 20_000
_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
_ORCHESTRATOR_COMPATIBILITY_TIMEOUT_SECONDS = 60


class ManagedPluginPayloadError(RuntimeError):
    """Raised when an app-bundled plugin payload is missing or unsafe."""


def bundled_payload_root(env: Mapping[str, str] | None = None) -> Path | None:
    source = env if env is not None else os.environ
    candidates: list[Path] = []
    override = str(source.get("ACROSS_AGENTS_PLUGIN_PAYLOAD_ROOT") or "").strip()
    if override and is_developer_mode(source):
        candidates.append(Path(override).expanduser())

    executable = Path(str(getattr(sys, "executable", "") or ""))
    if executable:
        candidates.extend(
            (
                executable.parent / "plugin-payloads",
                executable.parent.parent / "plugin-payloads",
            )
        )

    frozen_root = str(getattr(sys, "_MEIPASS", "") or "").strip()
    if frozen_root:
        unpacked = Path(frozen_root)
        candidates.extend(
            (
                unpacked / "plugin-payloads",
                unpacked.parent / "plugin-payloads",
                unpacked.parent.parent / "plugin-payloads",
            )
        )

    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if candidate.is_symlink() or not candidate.is_dir():
            continue
        manifest_path = candidate / "manifest.json"
        if manifest_path.is_file() and not manifest_path.is_symlink():
            return candidate
    return None


def plugin_payload(plugin_id: str, env: Mapping[str, str] | None = None) -> dict[str, Any] | None:
    root = bundled_payload_root(env)
    if root is None:
        return None
    manifest = _load_manifest(root)
    plugins = manifest.get("plugins")
    if not isinstance(plugins, Mapping):
        raise ManagedPluginPayloadError("Bundled plugin payload manifest is invalid")
    payload = plugins.get(plugin_id)
    if not isinstance(payload, Mapping):
        return None
    normalized = dict(payload)
    normalized["payload_root"] = str(root)
    return normalized


def bundled_install_source(plugin_id: str, env: Mapping[str, str] | None = None) -> str | None:
    payload = plugin_payload(plugin_id, env)
    if payload is None:
        return None
    version = str(payload.get("version") or "").strip()
    if not version:
        raise ManagedPluginPayloadError("Bundled plugin payload version is missing")
    return f"bundle://{plugin_id}/{version}"


def ensure_node_runtime(across_home: Path, env: Mapping[str, str] | None = None) -> Path:
    root = bundled_payload_root(env)
    if root is None:
        raise ManagedPluginPayloadError("Bundled Node runtime is unavailable")
    manifest = _load_manifest(root)
    runtimes = manifest.get("runtimes")
    descriptor = runtimes.get("node") if isinstance(runtimes, Mapping) else None
    if not isinstance(descriptor, Mapping):
        raise ManagedPluginPayloadError("Bundled Node runtime descriptor is missing")

    version = _required_string(descriptor, "version")
    source_dir = _payload_path(root, _required_string(descriptor, "path"), directory=True)
    executable_relative = _required_string(descriptor, "executable")
    source_executable = _payload_path(source_dir, executable_relative, executable=True)
    expected_sha256 = _required_sha256(descriptor)
    _verify_sha256(source_executable, expected_sha256)
    _validate_payload_tree(source_dir)

    destination = Path(across_home).expanduser() / "runtimes" / f"node-{version}"
    executable = destination / executable_relative
    marker = destination / ".across-runtime.json"
    if _runtime_marker_matches(marker, version=version, sha256=expected_sha256) and _is_executable(executable):
        return executable

    _copy_tree_atomic(source_dir, destination)
    executable = destination / executable_relative
    executable.chmod(executable.stat().st_mode | 0o755)
    _verify_sha256(executable, expected_sha256)
    marker.write_text(
        json.dumps(
            {
                "schema_version": "across-managed-runtime/1.0",
                "runtime": "node",
                "version": version,
                "sha256": expected_sha256,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return executable


def extract_plugin_source(
    plugin_id: str,
    destination: Path,
    env: Mapping[str, str] | None = None,
) -> Path:
    payload = plugin_payload(plugin_id, env)
    if payload is None:
        raise ManagedPluginPayloadError(f"Bundled payload for {plugin_id} is unavailable")
    if str(payload.get("runtime") or "") != "node":
        raise ManagedPluginPayloadError(f"Bundled payload for {plugin_id} is not a Node plugin")

    root = Path(str(payload["payload_root"]))
    archive = _payload_path(root, _required_string(payload, "archive"), executable=False)
    _verify_sha256(archive, _required_sha256(payload))
    destination = Path(destination).expanduser()
    shutil.rmtree(destination, ignore_errors=True)
    destination.mkdir(parents=True, exist_ok=True)
    source_root = _extract_tar_safely(archive, destination)
    _validate_extracted_plugin(source_root, payload)
    return source_root


def install_native_plugin_executable(
    plugin_id: str,
    destination: Path,
    env: Mapping[str, str] | None = None,
) -> Path:
    payload = plugin_payload(plugin_id, env)
    if payload is None:
        raise ManagedPluginPayloadError(f"Bundled payload for {plugin_id} is unavailable")
    if str(payload.get("runtime") or "") != "native":
        raise ManagedPluginPayloadError(f"Bundled payload for {plugin_id} is not a native plugin")

    root = Path(str(payload["payload_root"]))
    source = _payload_path(root, _required_string(payload, "executable"), executable=True)
    expected_sha256 = _required_sha256(payload)
    _verify_sha256(source, expected_sha256)

    destination = Path(destination).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(f".{destination.name}.tmp-{uuid.uuid4().hex}")
    try:
        shutil.copy2(source, tmp)
        tmp.chmod(tmp.stat().st_mode | 0o755)
        _verify_sha256(tmp, expected_sha256)
        if plugin_id == "across-orchestrator":
            validate_orchestrator_runtime_compatibility(tmp)
        os.replace(tmp, destination)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    return destination


def validate_orchestrator_runtime_compatibility(
    executable: Path,
    *,
    runner: Any = subprocess.run,
) -> None:
    """Require the sidecar contract used by the packaged AAA host.

    A basic ``plugin-manifest`` or ``health`` command is not sufficient: an
    older executable can pass both while rejecting the flag AAA needs to keep
    tasks inside the project directory selected by the user.
    """

    executable = Path(executable)
    try:
        completed = runner(
            [str(executable), "serve", "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=_ORCHESTRATOR_COMPATIBILITY_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception as exc:
        raise ManagedPluginPayloadError(
            "Bundled Across Orchestrator runtime compatibility check failed"
        ) from exc

    help_text = f"{getattr(completed, 'stdout', '') or ''}\n{getattr(completed, 'stderr', '') or ''}"
    if int(getattr(completed, "returncode", 1)) != 0 or "--allow-client-project-roots" not in help_text:
        raise ManagedPluginPayloadError(
            "Bundled Across Orchestrator runtime does not support client project roots"
        )


def _load_manifest(root: Path) -> dict[str, Any]:
    path = root / "manifest.json"
    try:
        if path.stat().st_size > _MAX_MANIFEST_BYTES:
            raise ManagedPluginPayloadError("Bundled plugin payload manifest is too large")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except ManagedPluginPayloadError:
        raise
    except Exception as exc:
        raise ManagedPluginPayloadError("Bundled plugin payload manifest cannot be read") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != PAYLOAD_SCHEMA:
        raise ManagedPluginPayloadError("Bundled plugin payload manifest is invalid")
    return payload


def _payload_path(root: Path, value: str, *, directory: bool = False, executable: bool = False) -> Path:
    relative = PurePosixPath(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ManagedPluginPayloadError("Bundled plugin payload path is invalid")
    candidate = root.joinpath(*relative.parts)
    try:
        candidate.resolve().relative_to(root.resolve())
    except Exception as exc:
        raise ManagedPluginPayloadError("Bundled plugin payload escapes its root") from exc
    if candidate.is_symlink():
        raise ManagedPluginPayloadError("Bundled plugin payload path cannot be a symlink")
    if directory and not candidate.is_dir():
        raise ManagedPluginPayloadError("Bundled plugin payload directory is missing")
    if not directory and not candidate.is_file():
        raise ManagedPluginPayloadError("Bundled plugin payload file is missing")
    if executable and not _is_executable(candidate):
        raise ManagedPluginPayloadError("Bundled plugin payload executable is not executable")
    return candidate


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ManagedPluginPayloadError(f"Bundled plugin payload field {key} is missing")
    return value


def _required_sha256(payload: Mapping[str, Any]) -> str:
    value = _required_string(payload, "sha256").lower()
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ManagedPluginPayloadError("Bundled plugin payload checksum is invalid")
    return value


def _verify_sha256(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ManagedPluginPayloadError(f"Bundled plugin payload checksum failed for {path.name}")


def _validate_payload_tree(root: Path) -> None:
    root_resolved = root.resolve()
    for path in root.rglob("*"):
        if not path.is_symlink():
            continue
        try:
            path.resolve().relative_to(root_resolved)
        except Exception as exc:
            raise ManagedPluginPayloadError("Bundled runtime contains an escaping symlink") from exc


def _copy_tree_atomic(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(f".{destination.name}.tmp-{uuid.uuid4().hex}")
    backup = destination.with_name(f".{destination.name}.backup-{uuid.uuid4().hex}")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(backup, ignore_errors=True)
    try:
        shutil.copytree(source, tmp, symlinks=True)
        if destination.exists():
            os.replace(destination, backup)
        try:
            os.replace(tmp, destination)
        except Exception:
            if backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)


def _runtime_marker_matches(marker: Path, *, version: str, sha256: str) -> bool:
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except Exception:
        return False
    return (
        isinstance(payload, dict)
        and payload.get("runtime") == "node"
        and payload.get("version") == version
        and payload.get("sha256") == sha256
    )


def _extract_tar_safely(archive_path: Path, destination: Path) -> Path:
    file_count = 0
    total_bytes = 0
    top_level: set[str] = set()
    with tarfile.open(archive_path, mode="r:gz") as archive:
        for member in archive:
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or not relative.parts or ".." in relative.parts:
                raise ManagedPluginPayloadError("Bundled plugin archive contains an unsafe path")
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise ManagedPluginPayloadError("Bundled plugin archive contains an unsafe entry")
            if not (member.isdir() or member.isfile()):
                continue
            file_count += 1
            total_bytes += max(0, int(member.size or 0))
            if file_count > _MAX_ARCHIVE_FILES or total_bytes > _MAX_ARCHIVE_BYTES:
                raise ManagedPluginPayloadError("Bundled plugin archive exceeds safety limits")
            top_level.add(relative.parts[0])
            target = destination.joinpath(*relative.parts)
            try:
                target.resolve().relative_to(destination.resolve())
            except Exception as exc:
                raise ManagedPluginPayloadError("Bundled plugin archive escapes its destination") from exc
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ManagedPluginPayloadError("Bundled plugin archive entry cannot be read")
            with extracted, target.open("wb") as output:
                shutil.copyfileobj(extracted, output)
            target.chmod(member.mode & 0o755 or 0o644)

    roots = [destination / item for item in sorted(top_level) if item not in {".", ".DS_Store"}]
    if len(roots) != 1 or not roots[0].is_dir():
        raise ManagedPluginPayloadError("Bundled plugin archive must contain one package root")
    return roots[0]


def _validate_extracted_plugin(source_root: Path, payload: Mapping[str, Any]) -> None:
    metadata_path = _payload_path(
        source_root,
        _required_string(payload, "metadata"),
        executable=False,
    )
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ManagedPluginPayloadError("Bundled Node plugin metadata is invalid") from exc
    if not isinstance(metadata, dict):
        raise ManagedPluginPayloadError("Bundled Node plugin metadata is invalid")
    if str(metadata.get("name") or "") != _required_string(payload, "package_name"):
        raise ManagedPluginPayloadError("Bundled Node plugin package name does not match")
    if str(metadata.get("version") or "") != _required_string(payload, "version"):
        raise ManagedPluginPayloadError("Bundled Node plugin version does not match")
    _payload_path(source_root, _required_string(payload, "entrypoint"), executable=False)


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)
