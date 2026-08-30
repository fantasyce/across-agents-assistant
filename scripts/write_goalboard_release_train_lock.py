#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import tomllib
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "goalboard-release-train-lock/1.0"


class ReleaseTrainError(ValueError):
    pass


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise ReleaseTrainError(f"required file is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_tree(path: Path) -> str:
    if not path.is_dir():
        raise ReleaseTrainError(f"required directory is missing: {path}")
    digest = hashlib.sha256()
    for item in sorted(path.rglob("*"), key=lambda value: value.relative_to(path).as_posix()):
        relative = item.relative_to(path).as_posix().encode("utf-8")
        mode = stat.S_IMODE(item.lstat().st_mode)
        if item.is_symlink():
            kind = b"symlink"
            content_digest = hashlib.sha256(os.readlink(item).encode("utf-8")).hexdigest()
        elif item.is_file():
            kind = b"file"
            content_digest = _sha256_file(item)
        elif item.is_dir():
            kind = b"directory"
            content_digest = ""
        else:
            raise ReleaseTrainError(f"unsupported App entry: {item}")
        digest.update(kind + b"\0" + str(mode).encode() + b"\0" + relative + b"\0")
        digest.update(content_digest.encode("ascii") + b"\n")
    return digest.hexdigest()


def _git(root: Path, *arguments: str, binary: bool = False) -> str | bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=False,
        capture_output=True,
        text=not binary,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode() if binary else completed.stderr
        raise ReleaseTrainError(f"git command failed for {root}: {stderr.strip()}")
    return completed.stdout


def _repository_facts(root: Path, component_id: str) -> dict[str, Any]:
    if not root.is_dir():
        raise ReleaseTrainError(f"repository is missing for {component_id}: {root}")
    dirty_output = str(_git(root, "status", "--porcelain", "--untracked-files=all"))
    if dirty_output.strip():
        raise ReleaseTrainError(f"dirty repository is not lockable: {component_id}")
    commit = str(_git(root, "rev-parse", "HEAD")).strip()
    source_archive = _git(root, "archive", "--format=tar", "HEAD", binary=True)
    assert isinstance(source_archive, bytes)
    return {
        "repository_root": str(root),
        "commit": commit,
        "dirty": False,
        "source_sha256": hashlib.sha256(source_archive).hexdigest(),
    }


def _version_from_file(repository: Path, relative_path: str) -> str:
    path = repository / relative_path
    if not path.is_file():
        raise ReleaseTrainError(f"version file is missing: {path}")
    if path.suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8")).get("version")
    elif path.suffix == ".toml":
        value = tomllib.loads(path.read_text(encoding="utf-8")).get("project", {}).get("version")
    else:
        value = path.read_text(encoding="utf-8").splitlines()[0].strip()
    normalized = str(value or "").strip()
    if not normalized:
        raise ReleaseTrainError(f"version file has no version: {path}")
    return normalized


def _capability_digest(path: Path) -> str:
    if not path.is_file():
        raise ReleaseTrainError(f"capability document is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseTrainError(f"capability document is invalid: {path}") from exc
    if not isinstance(payload, Mapping) or not payload:
        raise ReleaseTrainError(f"capability document is empty: {path}")
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _component_lock(component_id: str, candidate: Mapping[str, Any]) -> dict[str, Any]:
    repository = Path(str(candidate.get("repository_root") or "")).resolve()
    facts = _repository_facts(repository, component_id)
    declared_version = str(candidate.get("version") or "").strip()
    expected_version = str(candidate.get("expected_version") or "").strip()
    version_file = str(candidate.get("version_file") or "").strip()
    actual_version = _version_from_file(repository, version_file)
    if not declared_version or declared_version != expected_version or actual_version != declared_version:
        raise ReleaseTrainError(
            f"version mismatch for {component_id}: declared={declared_version or 'missing'} "
            f"expected={expected_version or 'missing'} actual={actual_version}"
        )

    asset_path = Path(str(candidate.get("asset_path") or "")).resolve()
    executable_path = Path(str(candidate.get("executable_path") or "")).resolve()
    capability_value = str(candidate.get("capability_path") or "").strip()
    if not capability_value:
        raise ReleaseTrainError(f"capability path is required for {component_id}")
    capability_path = Path(capability_value).resolve()
    asset_sha256 = _sha256_file(asset_path)
    published = str(candidate.get("published_asset_sha256") or "").strip().lower()
    if published and published != asset_sha256:
        raise ReleaseTrainError(f"published asset hash mismatch for {component_id}")
    result = {
        **facts,
        "version": declared_version,
        "version_file": version_file,
        "asset_path": str(asset_path),
        "asset_sha256": asset_sha256,
        "published_asset_sha256": published or None,
        "executable_path": str(executable_path),
        "executable_sha256": _sha256_file(executable_path),
        "capability_path": str(capability_path),
        "capability_digest": _capability_digest(capability_path),
    }
    app_value = str(candidate.get("app_path") or "").strip()
    if app_value:
        app_path = Path(app_value).resolve()
        result["app_path"] = str(app_path)
        result["app_sha256"] = _sha256_tree(app_path)
    return result


def build_lock(candidate: Mapping[str, Any]) -> dict[str, Any]:
    components = candidate.get("components")
    if not isinstance(components, Mapping) or set(components) != {
        "orchestrator",
        "context",
        "autopilot",
        "aaa",
    }:
        raise ReleaseTrainError("candidate must contain exactly the four release-train components")
    baseline_path = Path(str(candidate.get("acceptance_baseline_path") or "")).resolve()
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseTrainError("acceptance baseline is missing or invalid") from exc
    if baseline.get("schema_version") != "across-goal-cross-process-catalog/1.0":
        raise ReleaseTrainError("acceptance baseline schema is invalid")
    lock: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "components": {
            component_id: _component_lock(component_id, components[component_id])
            for component_id in ("orchestrator", "context", "autopilot", "aaa")
        },
        "acceptance_baseline": {
            "path": str(baseline_path),
            "sha256": _sha256_file(baseline_path),
        },
    }
    lock["lock_sha256"] = hashlib.sha256(_canonical_bytes(lock)).hexdigest()
    return lock


def verify_lock(lock: Mapping[str, Any]) -> dict[str, Any]:
    if lock.get("schema_version") != SCHEMA_VERSION:
        raise ReleaseTrainError("release-train lock schema is invalid")
    expected_lock_hash = str(lock.get("lock_sha256") or "")
    unsigned = {key: value for key, value in lock.items() if key != "lock_sha256"}
    if hashlib.sha256(_canonical_bytes(unsigned)).hexdigest() != expected_lock_hash:
        raise ReleaseTrainError("release-train lock hash drift")
    for component_id, component in lock.get("components", {}).items():
        repository = Path(component["repository_root"])
        current = _repository_facts(repository, str(component_id))
        if current["commit"] != component["commit"] or current["source_sha256"] != component["source_sha256"]:
            raise ReleaseTrainError(f"source hash drift for {component_id}")
        if _version_from_file(repository, component["version_file"]) != component["version"]:
            raise ReleaseTrainError(f"version mismatch for {component_id}")
        if _sha256_file(Path(component["asset_path"])) != component["asset_sha256"]:
            raise ReleaseTrainError(f"asset hash drift for {component_id}")
        if _sha256_file(Path(component["executable_path"])) != component["executable_sha256"]:
            raise ReleaseTrainError(f"executable hash drift for {component_id}")
        if _capability_digest(Path(component["capability_path"])) != component["capability_digest"]:
            raise ReleaseTrainError(f"capability hash drift for {component_id}")
        if component.get("app_path") and _sha256_tree(Path(component["app_path"])) != component["app_sha256"]:
            raise ReleaseTrainError(f"App hash drift for {component_id}")
        published = component.get("published_asset_sha256")
        if published and published != component["asset_sha256"]:
            raise ReleaseTrainError(f"published asset hash mismatch for {component_id}")
    baseline = lock.get("acceptance_baseline", {})
    if _sha256_file(Path(baseline["path"])) != baseline["sha256"]:
        raise ReleaseTrainError("acceptance baseline hash drift")
    return dict(lock)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or verify an immutable GoalBoard release-train lock.")
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    arguments = parser.parse_args()
    if arguments.verify:
        verify_lock(json.loads(arguments.verify.read_text(encoding="utf-8")))
        return 0
    if not arguments.candidate or not arguments.output:
        parser.error("--candidate and --output are required when not using --verify")
    candidate = json.loads(arguments.candidate.read_text(encoding="utf-8"))
    lock = build_lock(candidate)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
