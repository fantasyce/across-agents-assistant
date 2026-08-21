from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from across_agents_assistant import source_mirror_refresh as source_mirror_refresh_module
from across_agents_assistant.autopilot_client import AutopilotClient
from across_agents_assistant.plugin_runtime import KNOWN_PLUGINS
from across_agents_assistant.source_mirror_refresh import (
    DEFAULT_RELEASE_SOURCES,
    RELEASE_SOURCE_ENV,
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
    subprocess.check_call(["git", "-C", str(repo), "tag", "v1.0.0"])
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


def _release_source_env(tmp_path: Path, source_root: Path) -> dict[str, str]:
    env = {
        "HOME": str(tmp_path / "home"),
        "ACROSS_HOME": str(tmp_path / "across"),
        "ACROSS_AAA_SOURCE_MIRROR_REQUIRE_ORIGIN_MAIN": "0",
    }
    for repo_id in REQUIRED_SOURCE_REPOS:
        url_env, ref_env = RELEASE_SOURCE_ENV[repo_id]
        env[url_env] = str(source_root / repo_id)
        env[ref_env] = "v1.0.0"
    return env


def _git_source_parts(source: str) -> tuple[str, str]:
    body = source.removeprefix("git+")
    if "#" in body:
        url, ref = body.rsplit("#", 1)
    else:
        url, ref = body.rsplit("@", 1)
    return url, ref


def test_default_release_sources_match_managed_plugin_pins():
    plugins = {plugin.plugin_id: plugin for plugin in KNOWN_PLUGINS}
    for repo_id in ("across-orchestrator", "across-context", "across-autopilot"):
        plugin = plugins[repo_id]
        assert plugin.default_install_source
        url, ref = _git_source_parts(plugin.default_install_source)
        assert DEFAULT_RELEASE_SOURCES[repo_id] == {"url": url, "ref": ref}


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


def test_source_mirror_status_does_not_implicitly_probe_home_projects(tmp_path):
    home = tmp_path / "home"
    projects = home / "Documents" / "projects"
    for repo_id in REQUIRED_SOURCE_REPOS:
        _create_repo(projects, repo_id)
    env = {"HOME": str(home), "ACROSS_HOME": str(tmp_path / "across")}

    status = source_mirror_status(env)

    assert status["status"] == "failed"
    assert set(status["missing_repos"]) == set(REQUIRED_SOURCE_REPOS)
    assert all(repo["source"] is None for repo in status["repos"])


def test_refresh_source_mirrors_bootstraps_release_sources_without_dev_checkouts(tmp_path):
    source_root = _create_sources(tmp_path / "release-sources")
    env = _release_source_env(tmp_path, source_root)

    refreshed = refresh_source_mirrors(env)
    status = source_mirror_status(env)

    assert refreshed["status"] == "passed"
    assert status["status"] == "passed"
    assert status["stale_repos"] == []
    primary_root = Path(env["ACROSS_HOME"]) / "data" / "across-autopilot" / "source-mirrors"
    manifest = json.loads((primary_root / "manifest.json").read_text(encoding="utf-8"))
    assert {item["source_mode"] for item in manifest["repos"]} == {"release_source"}
    assert {item["source_ref"] for item in manifest["repos"]} == {"v1.0.0"}
    assert (primary_root / "across-agents-assistant" / "backend" / "pyproject.toml").exists()


def test_refresh_source_mirrors_reuses_fresh_release_mirrors_when_one_ref_changes(tmp_path, monkeypatch):
    source_root = _create_sources(tmp_path / "release-sources")
    env = _release_source_env(tmp_path, source_root)
    env.pop("ACROSS_AAA_SOURCE_MIRROR_REQUIRE_ORIGIN_MAIN")
    refresh_source_mirrors(env)

    repo = source_root / "across-autopilot"
    (repo / "package.json").write_text(json.dumps({"version": "1.0.1"}) + "\n", encoding="utf-8")
    subprocess.check_call(["git", "-C", str(repo), "add", "package.json"])
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
            "release 1.0.1",
        ]
    )
    subprocess.check_call(["git", "-C", str(repo), "tag", "v1.0.1"])
    _, ref_env = RELEASE_SOURCE_ENV["across-autopilot"]
    env[ref_env] = "v1.0.1"
    assert source_mirror_status(env)["stale_repos"] == ["across-autopilot"]

    cloned: list[str] = []
    original_git_clone = source_mirror_refresh_module._git_clone

    def tracking_git_clone(url, ref, target, repo_id, git_env):
        cloned.append(repo_id)
        return original_git_clone(url, ref, target, repo_id, git_env)

    monkeypatch.setattr(source_mirror_refresh_module, "_git_clone", tracking_git_clone)

    refresh_source_mirrors(env)
    status = source_mirror_status(env)
    primary_root = Path(env["ACROSS_HOME"]) / "data" / "across-autopilot" / "source-mirrors"
    manifest = json.loads((primary_root / "manifest.json").read_text(encoding="utf-8"))
    refs = {item["id"]: item["source_ref"] for item in manifest["repos"]}

    assert cloned == ["across-autopilot"]
    assert status["status"] == "passed"
    assert refs["across-autopilot"] == "v1.0.1"
    assert {refs[repo_id] for repo_id in REQUIRED_SOURCE_REPOS if repo_id != "across-autopilot"} == {"v1.0.0"}


def test_git_clone_retries_with_http1_fallback_and_cleans_failed_target(tmp_path, monkeypatch):
    target = tmp_path / "clone"
    calls = []
    saw_leftover = []

    def fake_run_git(args, cwd, *, timeout, include_cwd=True, cancellable=False):
        assert cancellable is True
        calls.append(list(args))
        saw_leftover.append((target / "partial").exists())
        target.mkdir(parents=True, exist_ok=True)
        (target / "partial").write_text("failed clone residue\n", encoding="utf-8")
        if len(calls) < 3:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="fatal: Error in the HTTP2 framing layer")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(source_mirror_refresh_module, "_run_git", fake_run_git)
    monkeypatch.setattr(source_mirror_refresh_module.time, "sleep", lambda _seconds: None)

    source_mirror_refresh_module._git_clone("https://example.invalid/repo.git", "v1.0.0", target, "repo", {})

    assert len(calls) == 3
    assert calls[2][:3] == ["-c", "http.version=HTTP/1.1", "clone"]
    assert saw_leftover == [False, False, False]


def test_git_clone_stops_before_retry_when_host_cancels(tmp_path, monkeypatch):
    target = tmp_path / "clone"
    source_mirror_refresh_module.cancel_active_source_mirror_refreshes(grace_seconds=0)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("cancelled refresh must not start another Git process")

    monkeypatch.setattr(source_mirror_refresh_module, "_run_git", fail_if_called)
    with pytest.raises(SourceMirrorRefreshError) as exc:
        source_mirror_refresh_module._git_clone(
            "https://example.invalid/repo.git", "v1.0.0", target, "repo", {}
        )

    assert exc.value.payload["reason"] == "source_mirror_refresh_cancelled"
    source_mirror_refresh_module._source_mirror_cancel_event.clear()


def test_release_source_bootstrap_clones_missing_repositories_concurrently(tmp_path, monkeypatch):
    import threading
    import time

    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_clone(url, ref, target, repo_id, env):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        target.mkdir(parents=True)
        with lock:
            active -= 1

    monkeypatch.setattr(source_mirror_refresh_module, "_git_clone", fake_clone)
    env = {
        url_env: f"https://example.invalid/{repo_id}.git"
        for repo_id, (url_env, _) in RELEASE_SOURCE_ENV.items()
    }
    env.update({ref_env: "v1.0.0" for _, ref_env in RELEASE_SOURCE_ENV.values()})

    sources, metadata = source_mirror_refresh_module._clone_release_sources(
        list(REQUIRED_SOURCE_REPOS), env, tmp_path
    )

    assert max_active > 1
    assert list(sources) == list(REQUIRED_SOURCE_REPOS)
    assert all(metadata[repo_id]["source_ref"] == "v1.0.0" for repo_id in REQUIRED_SOURCE_REPOS)


def test_release_source_clone_timeout_is_short_and_bounded():
    assert source_mirror_refresh_module._git_clone_timeout_seconds({}) == 30
    assert source_mirror_refresh_module._git_clone_timeout_seconds(
        {"ACROSS_AAA_SOURCE_MIRROR_CLONE_TIMEOUT_SECONDS": "1"}
    ) == 10


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


def test_autopilot_client_bootstraps_release_mirrors_before_candidate_run(tmp_path, monkeypatch):
    source_root = _create_sources(tmp_path / "release-sources")
    env = _release_source_env(tmp_path, source_root)
    calls = []
    retention_calls = []

    def fake_cli(args, *, env=None, timeout=60):
        calls.append({"args": args, "env": dict(env or {}), "timeout": timeout})
        return {"run": {"run_id": "run-1", "status": "completed"}, "evidence": {}}

    def fake_retention(**kwargs):
        retention_calls.append(kwargs)
        return {"status": "applied", "summary": {"deleted_count": 0}}

    monkeypatch.setattr("across_agents_assistant.autopilot_client.run_autopilot_cli_json", fake_cli)
    monkeypatch.setattr("across_agents_assistant.autopilot_client.run_retention", fake_retention)

    result = AutopilotClient(env=env).run("aaa-autonomous-self-iteration")

    assert result["run"]["status"] == "completed"
    mirror_root = Path(env["ACROSS_HOME"]) / "data" / "across-autopilot" / "source-mirrors"
    assert Path(calls[0]["env"]["ACROSS_AGENTS_ASSISTANT_SOURCE"]) == mirror_root / "across-agents-assistant"
    manifest = json.loads((mirror_root / "manifest.json").read_text(encoding="utf-8"))
    assert {item["source_mode"] for item in manifest["repos"]} == {"release_source"}
    assert len(retention_calls) == 1
    policy = retention_calls[0]["policy"]
    assert retention_calls[0]["across_home"] == env["ACROSS_HOME"]
    assert policy.keep_latest == 2
    assert policy.delete_beyond_keep_latest is True
    assert policy.include_promotion_ready is False
    assert policy.include_source_mirrors is False


def test_source_mirror_refresh_does_not_write_legacy_root_by_default(tmp_path):
    source_root = _create_sources(tmp_path)
    env = _env(tmp_path, source_root)

    refresh_source_mirrors(env)

    primary_root = Path(env["ACROSS_HOME"]) / "data" / "across-autopilot" / "source-mirrors"
    legacy_root = Path(env["ACROSS_HOME"]) / "source-mirrors"
    assert (primary_root / "manifest.json").exists()
    assert not (legacy_root / "manifest.json").exists()


def test_source_mirror_refresh_can_still_write_legacy_root_when_explicitly_enabled(tmp_path):
    source_root = _create_sources(tmp_path)
    env = _env(tmp_path, source_root)
    env["ACROSS_AAA_REFRESH_LEGACY_SOURCE_MIRRORS"] = "1"

    refresh_source_mirrors(env)

    primary_root = Path(env["ACROSS_HOME"]) / "data" / "across-autopilot" / "source-mirrors"
    legacy_root = Path(env["ACROSS_HOME"]) / "source-mirrors"
    assert (primary_root / "manifest.json").exists()
    assert (legacy_root / "manifest.json").exists()


def test_autopilot_client_refreshes_before_queued_candidate_trigger(tmp_path, monkeypatch):
    source_root = _create_sources(tmp_path)
    env = _env(tmp_path, source_root)
    calls = []
    retention_calls = []

    def fake_cli(args, *, env=None, timeout=60):
        calls.append(args)
        if args[:2] == ["loop", "claim-trigger"]:
            return {
                "status": "claimed",
                "trigger": {
                    "trigger_id": "trg-self",
                    "spec_id": "aaa-autonomous-self-iteration",
                    "status": "claimed",
                },
            }
        return {"status": "completed", "trigger": {"trigger_id": "trg-self"}}

    def fake_retention(**kwargs):
        retention_calls.append(kwargs)
        return {"status": "applied", "summary": {"deleted_count": 0}}

    monkeypatch.setattr("across_agents_assistant.autopilot_client.run_autopilot_cli_json", fake_cli)
    monkeypatch.setattr("across_agents_assistant.autopilot_client.run_retention", fake_retention)

    result = AutopilotClient(env=env).run_trigger("trg-self")

    assert result["status"] == "completed"
    assert calls[0][:2] == ["loop", "claim-trigger"]
    assert calls[1][:2] == ["loop", "run-claimed-trigger"]
    assert (Path(env["ACROSS_HOME"]) / "data" / "across-autopilot" / "source-mirrors" / "manifest.json").exists()
    assert len(retention_calls) == 1
    assert retention_calls[0]["policy"].prune_trigger_queue is True


def test_autopilot_client_does_not_refresh_for_non_candidate_loop(tmp_path, monkeypatch):
    source_root = _create_sources(tmp_path)
    env = _env(tmp_path, source_root)
    retention_calls = []

    def fake_cli(args, *, env=None, timeout=60):
        return {"run": {"run_id": "run-1", "status": "completed"}, "evidence": {}}

    monkeypatch.setattr("across_agents_assistant.autopilot_client.run_autopilot_cli_json", fake_cli)
    monkeypatch.setattr(
        "across_agents_assistant.autopilot_client.run_retention",
        lambda **kwargs: retention_calls.append(kwargs),
    )

    AutopilotClient(env=env).run("daily-news-brief")

    assert not (Path(env["ACROSS_HOME"]) / "data" / "across-autopilot" / "source-mirrors" / "manifest.json").exists()
    assert retention_calls == []


def test_candidate_retention_still_runs_when_source_mirror_refresh_is_disabled(tmp_path, monkeypatch):
    source_root = _create_sources(tmp_path)
    env = _env(tmp_path, source_root)
    env["ACROSS_AAA_SOURCE_MIRROR_REFRESH"] = "0"
    retention_calls = []

    def fake_cli(args, *, env=None, timeout=60):
        return {"run": {"run_id": "run-1", "spec_id": "aaa-autonomous-self-iteration", "status": "completed"}}

    def fake_retention(**kwargs):
        retention_calls.append(kwargs)
        return {"status": "applied", "summary": {"deleted_count": 0}}

    monkeypatch.setattr("across_agents_assistant.autopilot_client.run_autopilot_cli_json", fake_cli)
    monkeypatch.setattr("across_agents_assistant.autopilot_client.run_retention", fake_retention)

    AutopilotClient(env=env).run("aaa-autonomous-self-iteration")

    assert not (Path(env["ACROSS_HOME"]) / "data" / "across-autopilot" / "source-mirrors" / "manifest.json").exists()
    assert len(retention_calls) == 1
