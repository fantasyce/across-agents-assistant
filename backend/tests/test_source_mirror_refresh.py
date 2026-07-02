from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from across_agents_assistant.autopilot_client import AutopilotClient
from across_agents_assistant.source_mirror_refresh import (
    REQUIRED_SOURCE_REPOS,
    SourceMirrorRefreshError,
    refresh_source_mirrors,
    source_mirror_status,
)


def _create_repo(root: Path, repo_id: str, *, version: str = "1.0.0") -> Path:
    repo = root / repo_id
    repo.mkdir(parents=True)
    if repo_id == "across-agents-assistant":
        (repo / "backend").mkdir()
        (repo / "backend" / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n', encoding="utf-8")
    else:
        (repo / "package.json").write_text(json.dumps({"version": version}) + "\n", encoding="utf-8")
    (repo / "README.md").write_text(f"# {repo_id}\n", encoding="utf-8")
    subprocess.check_call(["git", "-C", str(repo), "init", "-q"])
    subprocess.check_call(["git", "-C", str(repo), "add", "."])
    subprocess.check_call(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=pytest",
            "-c",
            "user.email=pytest@example.invalid",
            "commit",
            "-q",
            "-m",
            "initial",
        ]
    )
    return repo


def _create_sources(root: Path) -> Path:
    source_root = root / "projects"
    for repo_id in REQUIRED_SOURCE_REPOS:
        _create_repo(source_root, repo_id)
    return source_root


def _env(tmp_path: Path, source_root: Path) -> dict[str, str]:
    return {
        "ACROSS_HOME": str(tmp_path / "across"),
        "ACROSS_LOOP_SOURCE_ROOT": str(source_root),
        "ACROSS_AAA_SOURCE_MIRROR_REQUIRE_ORIGIN_MAIN": "0",
    }


def test_refresh_source_mirrors_copies_clean_a_sources_and_detects_drift(tmp_path):
    source_root = _create_sources(tmp_path)
    env = _env(tmp_path, source_root)

    refreshed = refresh_source_mirrors(env)

    assert refreshed["status"] == "passed"
    primary_root = tmp_path / "across" / "data" / "across-autopilot" / "source-mirrors"
    manifest = json.loads((primary_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "passed"
    assert {item["id"] for item in manifest["repos"]} == set(REQUIRED_SOURCE_REPOS)
    assert (primary_root / "across-agents-assistant" / "backend" / "pyproject.toml").exists()
    assert source_mirror_status(env)["status"] == "passed"

    repo = source_root / "across-agents-assistant"
    (repo / "README.md").write_text("# across-agents-assistant\n\nnew baseline\n", encoding="utf-8")
    subprocess.check_call(["git", "-C", str(repo), "add", "README.md"])
    subprocess.check_call(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=pytest",
            "-c",
            "user.email=pytest@example.invalid",
            "commit",
            "-q",
            "-m",
            "advance baseline",
        ]
    )

    drifted = source_mirror_status(env)
    assert drifted["status"] == "failed"
    assert "across-agents-assistant" in drifted["drifted_repos"]

    refresh_source_mirrors(env)
    assert source_mirror_status(env)["status"] == "passed"


def test_refresh_source_mirrors_blocks_dirty_a_source(tmp_path):
    source_root = _create_sources(tmp_path)
    env = _env(tmp_path, source_root)
    refresh_source_mirrors(env)
    (source_root / "across-context" / "DIRTY.md").write_text("uncommitted\n", encoding="utf-8")

    status = source_mirror_status(env)
    assert status["status"] == "failed"
    assert "across-context" in status["dirty_repos"]

    with pytest.raises(SourceMirrorRefreshError) as exc:
        refresh_source_mirrors(env)

    assert exc.value.payload["repo"] == "across-context"
    assert exc.value.payload["reason"] == "dirty_source"


def test_autopilot_client_refreshes_before_candidate_run(tmp_path, monkeypatch):
    source_root = _create_sources(tmp_path)
    env = _env(tmp_path, source_root)
    calls = []

    def fake_cli(args, *, env=None, timeout=60):
        calls.append({"args": args, "env": dict(env or {}), "timeout": timeout})
        return {"run": {"run_id": "run-1", "status": "completed"}, "evidence": {}}

    monkeypatch.setattr("across_agents_assistant.autopilot_client.run_autopilot_cli_json", fake_cli)

    result = AutopilotClient(env=env).run("aaa-autonomous-self-iteration")

    assert result["run"]["status"] == "completed"
    assert calls[0]["args"][:2] == ["loop", "run"]
    mirror_root = Path(env["ACROSS_HOME"]) / "data" / "across-autopilot" / "source-mirrors"
    assert Path(calls[0]["env"]["ACROSS_AGENTS_ASSISTANT_SOURCE"]) == mirror_root / "across-agents-assistant"
    assert (mirror_root / "manifest.json").exists()


def test_autopilot_client_refreshes_before_queued_candidate_trigger(tmp_path, monkeypatch):
    source_root = _create_sources(tmp_path)
    env = _env(tmp_path, source_root)
    calls = []

    def fake_cli(args, *, env=None, timeout=60):
        calls.append(args)
        if args[:2] == ["loop", "trigger-queue"]:
            return {
                "items": [
                    {
                        "trigger_id": "trg-self",
                        "spec_id": "aaa-autonomous-self-iteration",
                        "status": "pending",
                    }
                ]
            }
        return {"status": "completed", "trigger": {"trigger_id": "trg-self"}}

    monkeypatch.setattr("across_agents_assistant.autopilot_client.run_autopilot_cli_json", fake_cli)

    result = AutopilotClient(env=env).run_trigger("trg-self")

    assert result["status"] == "completed"
    assert calls[0][:2] == ["loop", "trigger-queue"]
    assert calls[1][:2] == ["loop", "run-trigger"]
    assert (Path(env["ACROSS_HOME"]) / "data" / "across-autopilot" / "source-mirrors" / "manifest.json").exists()


def test_autopilot_client_does_not_refresh_for_non_candidate_loop(tmp_path, monkeypatch):
    source_root = _create_sources(tmp_path)
    env = _env(tmp_path, source_root)

    def fake_cli(args, *, env=None, timeout=60):
        return {"run": {"run_id": "run-1", "status": "completed"}, "evidence": {}}

    monkeypatch.setattr("across_agents_assistant.autopilot_client.run_autopilot_cli_json", fake_cli)

    AutopilotClient(env=env).run("daily-news-brief")

    assert not (Path(env["ACROSS_HOME"]) / "data" / "across-autopilot" / "source-mirrors" / "manifest.json").exists()
