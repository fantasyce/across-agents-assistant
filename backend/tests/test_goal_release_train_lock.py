from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from write_goal_release_train_lock import (  # noqa: E402
    ReleaseTrainError,
    build_lock,
    verify_lock,
)


def _git_repo(path: Path, version: str) -> Path:
    path.mkdir(parents=True)
    (path / "VERSION").write_text(version + "\n", encoding="utf-8")
    (path / "source.txt").write_text(f"source {version}\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "add", "VERSION", "source.txt"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.name=Release Test",
            "-c",
            "user.email=release@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    return path


def _candidate_fixture(tmp_path: Path) -> dict:
    components = {}
    versions = {
        "orchestrator": "0.12.2",
        "context": "0.12.0",
        "autopilot": "0.6.0",
        "aaa": "0.17.1",
    }
    for component_id, version in versions.items():
        repository = _git_repo(tmp_path / component_id, version)
        asset = tmp_path / "assets" / f"{component_id}-{version}.tar.gz"
        executable = tmp_path / "bin" / component_id
        capability = tmp_path / "capabilities" / f"{component_id}.json"
        asset.parent.mkdir(exist_ok=True)
        executable.parent.mkdir(exist_ok=True)
        capability.parent.mkdir(exist_ok=True)
        asset.write_bytes(f"asset:{component_id}:{version}".encode())
        executable.write_bytes(f"executable:{component_id}:{version}".encode())
        capability.write_text(
            json.dumps({"component": component_id, "capabilities": ["goal-contract"]}),
            encoding="utf-8",
        )
        components[component_id] = {
            "repository_root": str(repository),
            "version": version,
            "expected_version": version,
            "version_file": "VERSION",
            "asset_path": str(asset),
            "executable_path": str(executable),
            "capability_path": str(capability),
        }
    app = tmp_path / "Across Agents Assistant.app"
    (app / "Contents/MacOS").mkdir(parents=True)
    (app / "Contents/MacOS/Across Agents Assistant").write_bytes(b"app executable")
    components["aaa"]["app_path"] = str(app)
    baseline = tmp_path / "cross-process-contracts.json"
    baseline.write_text(
        json.dumps({"schema_version": "across-goal-cross-process-catalog/1.0"}),
        encoding="utf-8",
    )
    return {
        "components": components,
        "acceptance_baseline_path": str(baseline),
    }


def test_lock_captures_clean_immutable_candidate_and_verifies(tmp_path):
    lock = build_lock(_candidate_fixture(tmp_path))

    assert lock["schema_version"] == "across-goal-release-train-lock/1.0"
    assert set(lock["components"]) == {"orchestrator", "context", "autopilot", "aaa"}
    assert all(component["dirty"] is False for component in lock["components"].values())
    assert all(len(component["source_sha256"]) == 64 for component in lock["components"].values())
    assert all(len(component["capability_digest"]) == 64 for component in lock["components"].values())
    assert len(lock["components"]["aaa"]["app_sha256"]) == 64
    assert verify_lock(lock) == lock


def test_lock_rejects_asset_hash_drift(tmp_path):
    lock = build_lock(_candidate_fixture(tmp_path))
    Path(lock["components"]["orchestrator"]["asset_path"]).write_bytes(b"changed")

    with pytest.raises(ReleaseTrainError, match="asset hash drift"):
        verify_lock(lock)


def test_lock_rejects_dirty_repository(tmp_path):
    candidate = _candidate_fixture(tmp_path)
    repository = Path(candidate["components"]["aaa"]["repository_root"])
    (repository / "source.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(ReleaseTrainError, match="dirty repository"):
        build_lock(candidate)


def test_lock_rejects_wrong_component_version(tmp_path):
    candidate = _candidate_fixture(tmp_path)
    candidate["components"]["orchestrator"]["expected_version"] = "0.11.0"

    with pytest.raises(ReleaseTrainError, match="version mismatch"):
        build_lock(candidate)


def test_lock_requires_capability_digest(tmp_path):
    candidate = _candidate_fixture(tmp_path)
    candidate["components"]["context"].pop("capability_path")

    with pytest.raises(ReleaseTrainError, match="capability"):
        build_lock(candidate)


def test_lock_rejects_mismatched_published_asset_hash(tmp_path):
    candidate = _candidate_fixture(tmp_path)
    candidate["components"]["autopilot"]["published_asset_sha256"] = "f" * 64

    with pytest.raises(ReleaseTrainError, match="published asset hash"):
        build_lock(candidate)


def test_lock_rejects_executable_and_app_drift(tmp_path):
    candidate = _candidate_fixture(tmp_path)
    lock = build_lock(candidate)
    executable = Path(lock["components"]["context"]["executable_path"])
    executable.write_bytes(b"changed executable")
    with pytest.raises(ReleaseTrainError, match="executable hash drift"):
        verify_lock(lock)

    restored = build_lock(_candidate_fixture(tmp_path / "app-drift"))
    app_file = Path(restored["components"]["aaa"]["app_path"]) / "Contents/MacOS/Across Agents Assistant"
    app_file.write_bytes(b"changed app")
    with pytest.raises(ReleaseTrainError, match="App hash drift"):
        verify_lock(restored)


def test_candidate_versions_match_release_train():
    aaa_pyproject = (ROOT / "backend/pyproject.toml").read_text(encoding="utf-8")
    orchestrator_root = Path(
        os.environ.get(
            "ACROSS_ORCHESTRATOR_PROVIDER_ROOT",
            str(ROOT.parents[1] / "goal-contract-v2/across-orchestrator"),
        )
    ).resolve()
    orchestrator_pyproject = (orchestrator_root / "pyproject.toml").read_text(encoding="utf-8")

    assert 'version = "0.17.1"' in aaa_pyproject
    assert 'version = "0.12.2"' in orchestrator_pyproject


def test_packaged_acceptance_requires_and_records_release_train_lock():
    script = (ROOT / "scripts/run_vnext_single_release_acceptance.sh").read_text(encoding="utf-8")

    assert "ACROSS_GOAL_RELEASE_TRAIN_CANDIDATE" in script
    assert "write_goal_release_train_lock.py" in script
    packaged_e2e = script.index("packaged_app_cross_plugin_e2e")
    lock_gate = script.index("goal_release_train_lock")
    assert packaged_e2e < lock_gate
    assert "'$ROOT_DIR/backend/.venv/bin/python' scripts/write_goal_release_train_lock.py" in script
    assert "python3 scripts/write_goal_release_train_lock.py" not in script
