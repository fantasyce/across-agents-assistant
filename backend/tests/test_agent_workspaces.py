import os
import subprocess
import tempfile
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault(
    "ACROSS_AGENTS_DB_PATH",
    os.path.join(tempfile.mkdtemp(), "test_agent_workspaces.db"),
)

from across_agents_assistant import agent_workspaces as workspaces
from across_agents_assistant import agent_workspace_readiness as readiness
from across_agents_assistant import api_server
from across_agents_assistant.agent_workspaces import AgentWorkspaceError, AgentWorkspaceManager
from across_agents_assistant.api_server import app


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "source-repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.name", "AAA Tests")
    _git(repo, "config", "user.email", "aaa-tests@example.invalid")
    (repo / "README.md").write_text("# Fixture\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "initial")
    return repo


def _health(*, force=False):
    return {
        "codex": {"available": True, "found": True, "status": "available"},
        "claude": {"available": True, "found": True, "status": "available"},
    }


def _editing_runner(agent_id, prompt, worktree, timeout, session_id):
    target = Path(worktree) / "quality-report.md"
    target.write_text(f"candidate={agent_id}\n", encoding="utf-8")
    return {
        "success": True,
        "output": f"completed by {agent_id}",
        "model": "test-model",
        "provider": "local",
        "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
    }


def _passing_quality_gate(worktree, base_sha, timeout, options):
    assert _git(Path(worktree), "status", "--porcelain=v1") == ""
    assert _git(Path(worktree), "rev-parse", "HEAD") != base_sha
    return {
        "schema_version": "across-autopilot-gate-result/1.0",
        "run_id": "gate-run-fixture",
        "gate_verdict": "pass",
        "findings": [
            {
                "id": "repo-quality",
                "state": "pass",
                "severity": "info",
                "summary": "Repository quality evidence is complete.",
                "evidence": [{"type": "diff", "hash": "b" * 64}],
                "suggested_action": None,
                "owner": "repo-quality-copilot",
                "repair_round": 0,
                "source_gate": "repo-quality",
            }
        ],
        "evidence_hash": "a" * 64,
        "pr_ready_summary": "PR-ready: managed checks passed.",
        "head_sha": _git(Path(worktree), "rev-parse", "HEAD"),
        "push_receipt": {
            "schema_version": "across-autopilot-push-receipt/1.0",
            "gate_verdict": "pass",
        },
    }


def _capability_preflight(prompt, agent_ids, workflow):
    return {
        "selected_agent_ids": list(agent_ids),
        "recommended_agent_ids": list(agent_ids),
        "agent_summaries": [
            {
                "agent_id": agent_id,
                "score": 4,
                "configured_count": 2,
                "matched_skill_ids": ["implementation"],
                "warnings": [],
            }
            for agent_id in agent_ids
        ],
        "warnings": [],
        "prompt_preview": "must never persist",
    }


@pytest.fixture
def workspace_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ACROSS_HOME", raising=False)
    return tmp_path


def _manager(runner=_editing_runner, canceller=None, quality_gate_runner=_passing_quality_gate):
    return AgentWorkspaceManager(
        agent_runner=runner,
        agent_canceller=canceller,
        agent_health_provider=_health,
        quality_gate_runner=quality_gate_runner,
        capability_preflight=_capability_preflight,
    )


def _create_and_wait(manager: AgentWorkspaceManager, repo: Path, **overrides):
    params = {
        "repo_root": str(repo),
        "prompt": "Run the repository quality task and make one bounded improvement.",
        "agent_ids": ["codex"],
        "validation_commands": [["git", "diff", "--check"]],
        "idempotency_key": "fixture-request",
        "workflow": "repo-quality-copilot",
    }
    params.update(overrides)
    created = manager.create(**params)
    return manager.wait(created["workspace_id"])


def test_parallel_workspace_happy_path_persists_comparison_without_touching_source(workspace_env):
    repo = _repo(workspace_env)
    manager = _manager()
    try:
        state = _create_and_wait(
            manager,
            repo,
            agent_ids=["codex", "claude"],
            idempotency_key="parallel-happy",
        )

        assert state["status"] == "review_ready"
        assert state["security"]["prompt_persisted"] is False
        assert state["security"]["agent_transcript_persisted"] is False
        assert state["capability_preflight"]["status"] == "ready"
        assert state["capability_preflight"]["prompt_preview_persisted"] is False
        assert "quality_gate_options" not in state
        assert "prompt_preview" not in state["capability_preflight"]
        assert not (repo / "quality-report.md").exists()
        source_worktrees = _git(repo, "worktree", "list", "--porcelain")
        assert source_worktrees.count("worktree ") == 1
        assert len(state["candidates"]) == 2
        assert all(candidate["status"] == "completed" for candidate in state["candidates"])
        assert all(candidate["comparison"]["tests"]["status"] == "passed" for candidate in state["candidates"])
        assert all(candidate["comparison"]["quality_gate"]["status"] == "passed" for candidate in state["candidates"])
        assert all(
            "path" not in candidate["comparison"]["quality_gate"]["push_receipt"].get("repository", {})
            for candidate in state["candidates"]
        )
        assert all(candidate["evidence"]["ready_for_review"] is True for candidate in state["candidates"])
        assert all("worktree" not in candidate and "session_id" not in candidate for candidate in state["candidates"])

        comparison = manager.comparison(state["workspace_id"])
        assert {item["agent_id"] for item in comparison["candidates"]} == {"codex", "claude"}
        assert all("diff --git" in item["diff"] for item in comparison["candidates"])
        events = manager.events(state["workspace_id"])["events"]
        assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
        assert any(event["type"] == "candidate.evidence.updated" for event in events)
    finally:
        manager.shutdown(wait=True)


def test_workspace_quality_gate_receives_private_ci_watcher_options(workspace_env):
    repo = _repo(workspace_env)
    ci_path = workspace_env / "ci-status.json"
    ci_path.write_text('{"checks":[{"id":"test","status":"passed"}]}\n', encoding="utf-8")
    captured = {}

    def gate(worktree, base_sha, timeout, options):
        captured.update(options)
        return _passing_quality_gate(worktree, base_sha, timeout, options)

    manager = _manager(quality_gate_runner=gate)
    try:
        state = _create_and_wait(
            manager,
            repo,
            idempotency_key="ci-watcher-options",
            quality_gate_ci_path=str(ci_path),
            quality_gate_ci_wait_seconds=30,
            quality_gate_draft_pr=True,
        )

        assert state["status"] == "review_ready"
        assert "quality_gate_options" not in state
        assert captured["ci_path"] == str(ci_path.resolve())
        assert captured["ci_wait_seconds"] == 30
        assert captured["draft_pr"] is True
        assert len(captured["ci_sha256"]) == 64
    finally:
        manager.shutdown(wait=True)


def test_unavailable_agent_is_rejected_before_worktree_creation(workspace_env):
    repo = _repo(workspace_env)

    def unavailable(*, force=False):
        return {"codex": {"available": False, "status": "unavailable"}}

    manager = AgentWorkspaceManager(agent_runner=_editing_runner, agent_health_provider=unavailable)
    try:
        with pytest.raises(AgentWorkspaceError) as raised:
            manager.create(repo_root=str(repo), prompt="quality", agent_ids=["codex"])
        assert raised.value.status_code == 409
        assert raised.value.code == "agents_unavailable"
        assert list(manager.root.glob("aws-*")) == []
    finally:
        manager.shutdown(wait=True)


@pytest.mark.parametrize(
    ("repo_value", "expected_code"),
    [
        ("relative/repo", "repo_root_not_absolute"),
        ("{home}", "unsafe_repo_root"),
        ("{missing}", "repo_root_not_found"),
    ],
)
def test_unsafe_repository_paths_are_rejected(workspace_env, repo_value, expected_code):
    value = repo_value.format(home=workspace_env, missing=workspace_env / "missing")
    with pytest.raises(AgentWorkspaceError) as raised:
        workspaces.inspect_git_repository(value)
    assert raised.value.code == expected_code


def test_repository_access_contract_rejects_inactive_scope_and_permission_errors(workspace_env):
    repo = _repo(workspace_env)
    with pytest.raises(AgentWorkspaceError) as raised:
        workspaces.inspect_git_repository(
            str(repo),
            repo_access={"mode": "security_scoped", "security_scope_active": False, "grant_id": "picker-grant"},
        )
    assert raised.value.status_code == 403
    assert raised.value.code == "repository_access_not_authorized"

    with pytest.raises(AgentWorkspaceError) as denied:
        workspaces._run_command(
            ["/bin/sh", "-c", "echo 'Operation not permitted' >&2; exit 1"],
            operation="Inspect protected repository",
        )
    assert denied.value.status_code == 403
    assert denied.value.code == "repository_access_denied"


def test_security_scoped_access_metadata_is_hashed_and_survives_lifecycle(workspace_env):
    repo = _repo(workspace_env)
    manager = _manager()
    grant_id = "picker-grant-123"
    try:
        state = _create_and_wait(
            manager,
            repo,
            idempotency_key="security-scoped-access",
            repo_access={"mode": "security_scoped", "security_scope_active": True, "grant_id": grant_id},
        )
        access = state["repo_access"]
        assert access["mode"] == "security_scoped"
        assert access["security_scope_active"] is True
        assert access["grant_id_sha256"] == workspaces._sha256_text(grant_id)
        durable_state = manager._state_path(state["workspace_id"]).read_text(encoding="utf-8")
        assert grant_id not in durable_state
        candidate_id = state["candidates"][0]["candidate_id"]
        manager.select(state["workspace_id"], candidate_id)
        promoted = manager.promote(
            state["workspace_id"],
            candidate_id=candidate_id,
            approved=True,
            approved_by="security-scope-reviewer",
        )
        assert promoted["status"] == "promoted"
    finally:
        manager.shutdown(wait=True)


def test_command_has_independent_idle_and_total_timeouts():
    with pytest.raises(AgentWorkspaceError) as idle:
        workspaces._run_command(
            ["/bin/sh", "-c", "sleep 2"],
            operation="Wait for silent command",
            timeout=1.0,
            idle_timeout=0.1,
        )
    assert idle.value.code == "command_idle_timeout"

    with pytest.raises(AgentWorkspaceError) as total:
        workspaces._run_command(
            ["/bin/sh", "-c", "while true; do echo progress; sleep 0.03; done"],
            operation="Wait for endless command",
            timeout=0.2,
            idle_timeout=0.15,
        )
    assert total.value.code == "command_total_timeout"


def test_candidate_validations_do_not_use_the_short_git_idle_timeout(workspace_env, monkeypatch):
    observed = {}

    def quiet_validation(argv, **kwargs):
        observed.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(workspaces, "_run_command", quiet_validation)
    manager = _manager()
    try:
        result = manager._run_validations(
            {
                "validation_commands": [["python3", "-m", "pytest"]],
                "test_timeout_seconds": 900.0,
            },
            {"worktree": str(workspace_env)},
        )
    finally:
        manager.shutdown(wait=True)

    assert result["status"] == "passed"
    assert observed["timeout"] == 900.0
    assert observed["idle_timeout"] == 900.0


def test_unified_diff_location_parser_does_not_confuse_content_with_headers():
    patch = """diff --git a/example.txt b/example.txt
index 1111111..2222222 100644
--- a/example.txt
+++ b/example.txt
@@ -1,2 +1,2 @@
--- removed-content
+++ added-content
 context
"""
    locations = workspaces._unified_diff_locations(patch)
    assert locations[("example.txt", "LEFT")] == {1, 2}
    assert locations[("example.txt", "RIGHT")] == {1, 2}


def test_cancellation_stops_candidate_and_never_touches_source(workspace_env):
    repo = _repo(workspace_env)
    started = threading.Event()
    release = threading.Event()

    def blocking_runner(agent_id, prompt, worktree, timeout, session_id):
        started.set()
        release.wait(5)
        return {"success": False, "error_code": "cancelled", "output": "stopped"}

    manager = _manager(blocking_runner, lambda _session_id: release.set() or True)
    try:
        created = manager.create(repo_root=str(repo), prompt="quality", agent_ids=["codex"])
        assert started.wait(2)
        cancelled = manager.cancel(created["workspace_id"], reason="review stopped")
        assert cancelled["status"] in {"cancelling", "cancelled"}
        final = manager.wait(created["workspace_id"])
        assert final["status"] == "cancelled"
        assert final["candidates"][0]["status"] == "cancelled"
        assert _git(repo, "status", "--porcelain") == ""
    finally:
        release.set()
        manager.shutdown(wait=True)


def test_promotion_rejects_base_drift(workspace_env):
    repo = _repo(workspace_env)
    manager = _manager()
    try:
        state = _create_and_wait(manager, repo, idempotency_key="base-drift")
        candidate_id = state["candidates"][0]["candidate_id"]
        manager.select(state["workspace_id"], candidate_id)
        (repo / "drift.txt").write_text("new base\n", encoding="utf-8")
        _git(repo, "add", "drift.txt")
        _git(repo, "commit", "-m", "advance base")

        with pytest.raises(AgentWorkspaceError) as raised:
            manager.promote(
                state["workspace_id"],
                candidate_id=candidate_id,
                approved=True,
                approved_by="reviewer@example.invalid",
            )
        assert raised.value.code == "base_drift"
        assert not (repo / "quality-report.md").exists()
    finally:
        manager.shutdown(wait=True)


def test_promotion_reports_conflict_before_source_mutation(workspace_env, monkeypatch):
    repo = _repo(workspace_env)
    manager = _manager()
    real_run_command = workspaces._run_command

    def conflict_on_apply_check(argv, **kwargs):
        if "apply" in argv and "--check" in argv:
            return subprocess.CompletedProcess(argv, 1, "", "conflict")
        return real_run_command(argv, **kwargs)

    try:
        state = _create_and_wait(manager, repo, idempotency_key="conflict")
        candidate_id = state["candidates"][0]["candidate_id"]
        monkeypatch.setattr(workspaces, "_run_command", conflict_on_apply_check)
        with pytest.raises(AgentWorkspaceError) as raised:
            manager.promote(
                state["workspace_id"],
                candidate_id=candidate_id,
                approved=True,
                approved_by="reviewer@example.invalid",
            )
        assert raised.value.code == "candidate_conflict"
        assert not (repo / "quality-report.md").exists()
    finally:
        manager.shutdown(wait=True)


def test_promotion_requires_approval_and_approved_promotion_applies_exact_candidate(workspace_env):
    repo = _repo(workspace_env)
    manager = _manager()
    try:
        state = _create_and_wait(manager, repo, idempotency_key="approved")
        workspace_id = state["workspace_id"]
        candidate_id = state["candidates"][0]["candidate_id"]
        manager.select(workspace_id, candidate_id)

        with pytest.raises(AgentWorkspaceError) as raised:
            manager.promote(workspace_id, candidate_id=candidate_id, approved=False, approved_by=None)
        assert raised.value.status_code == 403
        assert raised.value.code == "human_approval_required"
        assert not (repo / "quality-report.md").exists()

        promoted = manager.promote(
            workspace_id,
            candidate_id=candidate_id,
            approved=True,
            approved_by="human-reviewer",
        )
        assert promoted["status"] == "promoted"
        assert promoted["promotion"]["status"] == "promoted"
        assert promoted["promotion"]["approved"] is True
        assert promoted["candidates"][0]["evidence"]["conflicts_validated"] is True
        assert promoted["candidates"][0]["evidence"]["human_approval_validated"] is True
        assert (repo / "quality-report.md").read_text(encoding="utf-8") == "candidate=codex\n"
        assert _git(repo, "status", "--porcelain") == "?? quality-report.md"

        repeated = manager.promote(
            workspace_id,
            candidate_id=candidate_id,
            approved=True,
            approved_by="human-reviewer",
        )
        assert repeated["status"] == "promoted"
    finally:
        manager.shutdown(wait=True)


def test_failed_candidate_validation_blocks_promotion(workspace_env):
    repo = _repo(workspace_env)
    manager = _manager()
    try:
        state = _create_and_wait(
            manager,
            repo,
            idempotency_key="failed-validation",
            validation_commands=[["git", "diff", "--check"], ["git", "rev-parse", "missing-ref"]],
        )
        candidate = state["candidates"][0]
        assert candidate["comparison"]["tests"]["status"] == "failed"
        assert candidate["evidence"]["ready_for_review"] is False
        with pytest.raises(AgentWorkspaceError) as raised:
            manager.promote(
                state["workspace_id"],
                candidate_id=candidate["candidate_id"],
                approved=True,
                approved_by="human-reviewer",
            )
        assert raised.value.code == "tests_not_passed"
        assert not (repo / "quality-report.md").exists()
    finally:
        manager.shutdown(wait=True)


def test_restart_recovery_marks_active_state_interrupted(workspace_env):
    repo = _repo(workspace_env)
    manager = _manager()
    state = _create_and_wait(manager, repo, idempotency_key="restart")
    manager.shutdown(wait=True)

    durable = manager._load_state(state["workspace_id"])
    durable["status"] = "running"
    durable["candidates"][0]["status"] = "running"
    manager._write_state(durable)

    recovered = _manager()
    try:
        state_after_restart = recovered.get(state["workspace_id"])
        assert state_after_restart["status"] == "interrupted"
        assert state_after_restart["candidates"][0]["status"] == "interrupted"
        assert recovered.events(state["workspace_id"])["events"][-1]["type"] == "workspace.recovered_interrupted"
    finally:
        recovered.shutdown(wait=True)


def test_review_comment_is_sent_back_but_not_persisted(workspace_env):
    repo = _repo(workspace_env)
    prompts = []

    def revision_runner(agent_id, prompt, worktree, timeout, session_id):
        prompts.append(prompt)
        (Path(worktree) / "quality-report.md").write_text(f"revision={len(prompts)}\n", encoding="utf-8")
        return {"success": True, "output": "done"}

    manager = _manager(revision_runner)
    try:
        state = _create_and_wait(manager, repo, idempotency_key="comment")
        comment = "Add a regression check for the release evidence path."
        candidate_id = state["candidates"][0]["candidate_id"]
        manager.comment(state["workspace_id"], candidate_id, comment)
        revised = manager.wait(state["workspace_id"])
        assert revised["status"] == "review_ready"
        assert comment in prompts[-1]
        assert revised["review_comments"][0]["comment_length"] == len(comment)
        durable_text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in manager.root.rglob("*")
            if path.is_file() and path.stat().st_size < 1_000_000
        )
        assert comment not in durable_text
    finally:
        manager.shutdown(wait=True)


def test_line_review_is_anchored_redacted_idempotent_and_restart_safe(workspace_env):
    repo = _repo(workspace_env)
    prompts = []

    def revision_runner(agent_id, prompt, worktree, timeout, session_id):
        prompts.append(prompt)
        (Path(worktree) / "quality-report.md").write_text(f"revision={len(prompts)}\n", encoding="utf-8")
        return {"success": True, "output": "done"}

    manager = _manager(revision_runner)
    try:
        state = _create_and_wait(manager, repo, idempotency_key="line-review")
        workspace_id = state["workspace_id"]
        candidate = state["candidates"][0]
        body = "PRIVATE_REVIEW_BODY_fix_the_report_contract"
        request = {
            "anchor": candidate["comparison"]["review_anchor"],
            "comments": [
                {"path": "quality-report.md", "side": "RIGHT", "start_line": 1, "line": 1, "body": body}
            ],
            "idempotency_key": "line-review-request-1",
        }
        accepted = manager.line_review(workspace_id, candidate["candidate_id"], **request)
        assert accepted["status"] == "revising"
        repeated = manager.line_review(workspace_id, candidate["candidate_id"], **request)
        assert repeated["workspace_id"] == workspace_id
        with pytest.raises(AgentWorkspaceError) as conflict:
            manager.line_review(
                workspace_id,
                candidate["candidate_id"],
                anchor=request["anchor"],
                comments=[{"path": "quality-report.md", "side": "RIGHT", "line": 1, "body": "different body"}],
                idempotency_key="line-review-request-1",
            )
        assert conflict.value.code == "line_review_idempotency_conflict"
        revised = manager.wait(workspace_id)
        assert revised["status"] == "review_ready"
        assert len(prompts) == 2
        assert body in prompts[-1]
        batch = revised["line_review_batches"][0]
        assert batch["comment_count"] == 1
        assert batch["comments"][0]["path"] == "quality-report.md"
        assert batch["comments"][0]["side"] == "RIGHT"
        assert batch["comments"][0]["body_length"] == len(body)
        assert batch["comments"][0]["redacted"] is True

        durable_text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in manager.root.rglob("*")
            if path.is_file() and path.stat().st_size < 1_000_000
        )
        assert body not in durable_text
    finally:
        manager.shutdown(wait=True)

    recovered = _manager(revision_runner)
    try:
        restored = recovered.get(workspace_id)
        assert restored["line_review_batches"][0]["comment_count"] == 1
        before = len(prompts)
        idempotent = recovered.line_review(workspace_id, candidate["candidate_id"], **request)
        assert idempotent["workspace_id"] == workspace_id
        assert len(prompts) == before
    finally:
        recovered.shutdown(wait=True)


def test_line_review_rejects_stale_invalid_and_concurrent_feedback(workspace_env):
    repo = _repo(workspace_env)
    started = threading.Event()
    release = threading.Event()
    run_count = 0

    def blocking_revision_runner(agent_id, prompt, worktree, timeout, session_id):
        nonlocal run_count
        run_count += 1
        (Path(worktree) / "quality-report.md").write_text(f"revision={run_count}\n", encoding="utf-8")
        if run_count > 1:
            started.set()
            release.wait(2)
        return {"success": True, "output": "done"}

    manager = _manager(blocking_revision_runner)
    try:
        state = _create_and_wait(manager, repo, idempotency_key="line-review-errors")
        workspace_id = state["workspace_id"]
        candidate = state["candidates"][0]
        candidate_id = candidate["candidate_id"]
        anchor = candidate["comparison"]["review_anchor"]

        with pytest.raises(AgentWorkspaceError) as invalid:
            manager.line_review(
                workspace_id,
                candidate_id,
                anchor=anchor,
                comments=[{"path": "quality-report.md", "side": "LEFT", "line": 99, "body": "wrong side"}],
            )
        assert invalid.value.code == "review_location_not_in_diff"

        internal = manager._load_state(workspace_id)
        worktree = Path(internal["candidates"][0]["worktree"])
        (worktree / "quality-report.md").write_text("changed-after-review\n", encoding="utf-8")
        with pytest.raises(AgentWorkspaceError) as stale:
            manager.line_review(
                workspace_id,
                candidate_id,
                anchor=anchor,
                comments=[{"path": "quality-report.md", "side": "RIGHT", "line": 1, "body": "stale feedback"}],
            )
        assert stale.value.code == "stale_review_anchor"

        refreshed = manager.get(workspace_id)
        fresh_anchor = refreshed["candidates"][0]["comparison"]["review_anchor"]
        manager.line_review(
            workspace_id,
            candidate_id,
            anchor=fresh_anchor,
            comments=[{"path": "quality-report.md", "side": "RIGHT", "line": 1, "body": "current feedback"}],
            idempotency_key="concurrent-first",
        )
        assert started.wait(1)
        with pytest.raises(AgentWorkspaceError) as concurrent:
            manager.line_review(
                workspace_id,
                candidate_id,
                anchor=fresh_anchor,
                comments=[{"path": "quality-report.md", "side": "RIGHT", "line": 1, "body": "second feedback"}],
                idempotency_key="concurrent-second",
            )
        assert concurrent.value.code == "candidate_not_reviewable"
    finally:
        release.set()
        manager.shutdown(wait=True)


def test_secret_candidate_is_quarantined_and_redacted_from_durable_state(workspace_env):
    repo = _repo(workspace_env)
    prompt_secret = "sk-prompt-secret-12345"
    file_secret = "sk-file-secret-12345"
    output_secret = "sk-output-secret-12345"
    source_objects_before = _git(repo, "count-objects", "-v")

    def secret_runner(agent_id, prompt, worktree, timeout, session_id):
        candidate = Path(worktree)
        (candidate / "credentials.txt").write_text(file_secret, encoding="utf-8")
        _git(candidate, "config", "user.name", "Candidate")
        _git(candidate, "config", "user.email", "candidate@example.invalid")
        _git(candidate, "add", "credentials.txt")
        _git(candidate, "commit", "-m", "unsafe candidate commit")
        return {"success": True, "output": output_secret}

    manager = _manager(secret_runner)
    try:
        created = manager.create(repo_root=str(repo), prompt=prompt_secret, agent_ids=["codex"])
        final = manager.wait(created["workspace_id"])
        assert final["status"] == "failed"
        assert final["candidates"][0]["status"] == "blocked"
        assert final["candidates"][0]["comparison"]["risk"]["blocking"] is True
        assert final["candidates"][0]["worktree_removed"] is True

        durable_bytes = b"\n".join(path.read_bytes() for path in manager.root.rglob("*") if path.is_file())
        assert prompt_secret.encode() not in durable_bytes
        assert file_secret.encode() not in durable_bytes
        assert output_secret.encode() not in durable_bytes
        assert not list(manager.root.rglob("*.patch"))
        assert _git(repo, "count-objects", "-v") == source_objects_before
    finally:
        manager.shutdown(wait=True)


def test_idempotent_create_and_cleanup_are_restart_safe(workspace_env):
    repo = _repo(workspace_env)
    manager = _manager()
    try:
        first = _create_and_wait(manager, repo, idempotency_key="same-request")
        repeated = manager.create(
            repo_root=str(repo),
            prompt="Run the repository quality task and make one bounded improvement.",
            agent_ids=["codex"],
            validation_commands=[["git", "diff", "--check"]],
            idempotency_key="same-request",
            workflow="repo-quality-copilot",
        )
        assert repeated["workspace_id"] == first["workspace_id"]
        cleaned = manager.cleanup(first["workspace_id"])
        assert cleaned["status"] == "cleaned"
        assert cleaned["cleanup"]["status"] == "completed"
        assert manager.cleanup(first["workspace_id"])["cleanup"]["status"] == "completed"
    finally:
        manager.shutdown(wait=True)


def test_agent_workspace_api_end_to_end_contract(workspace_env, monkeypatch):
    repo = _repo(workspace_env)
    monkeypatch.setattr(readiness, "detect_local_agents", lambda *, force=False: _health(force=force))
    monkeypatch.setattr(readiness, "_host_capability_registry", lambda: {"agents": []})
    client = TestClient(app)
    readiness_response = client.get(
        "/api/agent-workspaces/readiness",
        params={"repo_root": str(repo), "selected_agent_ids": "codex"},
    )
    assert readiness_response.status_code == 200
    assert readiness_response.json()["status"] == "ready"
    assert readiness_response.json()["readonly"] is True
    assert readiness_response.json()["workspace_isolation"]["can_create_isolated_workspaces"] is True

    rejected_bookmark = client.post(
        "/api/agent-workspaces",
        json={
            "repo_root": str(repo),
            "prompt": "quality",
            "agent_ids": ["codex"],
            "repo_access": {
                "mode": "security_scoped",
                "security_scope_active": True,
                "bookmark_data": "must-stay-in-swift",
            },
        },
    )
    assert rejected_bookmark.status_code == 422

    manager = _manager()
    monkeypatch.setattr(api_server, "_agent_workspace_manager", manager)
    try:
        create_response = client.post(
            "/api/agent-workspaces",
            json={
                "repo_root": str(repo),
                "prompt": "Run a realistic repository quality review and write the evidence report.",
                "agent_ids": ["codex"],
                "validation_commands": [["git", "diff", "--check"]],
                "workflow": "repo-quality-copilot",
                "idempotency_key": "api-e2e",
                "repo_access": {"mode": "implicit", "security_scope_active": False},
            },
        )
        assert create_response.status_code == 201
        workspace_id = create_response.json()["workspace_id"]
        final = manager.wait(workspace_id)
        candidate_id = final["candidates"][0]["candidate_id"]

        get_response = client.get(f"/api/agent-workspaces/{workspace_id}")
        assert get_response.status_code == 200
        assert get_response.json()["status"] == "review_ready"

        events_response = client.get(f"/api/agent-workspaces/{workspace_id}/events")
        assert events_response.status_code == 200
        assert events_response.json()["events"]
        stream_response = client.get(f"/api/agent-workspaces/{workspace_id}/events?stream=true")
        assert stream_response.status_code == 200
        assert "event: workspace.created" in stream_response.text

        comparison_response = client.get(f"/api/agent-workspaces/{workspace_id}/comparison")
        assert comparison_response.status_code == 200
        evidence = comparison_response.json()["candidates"][0]["evidence"]
        assert evidence["ready_for_review"] is True
        assert evidence["human_approval_required"] is True
        quality_gate = comparison_response.json()["candidates"][0]["comparison"]["quality_gate"]
        assert quality_gate["status"] == "passed"
        assert quality_gate["findings"][0]["state"] == "pass"
        assert quality_gate["evidence_routes"] == ["/api/autopilot/runs/gate-run-fixture/evidence"]

        line_review_response = client.post(
            f"/api/agent-workspaces/{workspace_id}/line-reviews",
            json={
                "candidate_id": candidate_id,
                "anchor": final["candidates"][0]["comparison"]["review_anchor"],
                "comments": [
                    {
                        "path": "quality-report.md",
                        "side": "RIGHT",
                        "line": 1,
                        "body": "Make the report evidence explicit.",
                    }
                ],
                "idempotency_key": "api-line-review",
            },
        )
        assert line_review_response.status_code == 200
        final = manager.wait(workspace_id)
        assert final["line_review_batches"][0]["comment_count"] == 1

        select_response = client.post(
            f"/api/agent-workspaces/{workspace_id}/select",
            json={"candidate_id": candidate_id},
        )
        assert select_response.status_code == 200

        no_approval = client.post(
            f"/api/agent-workspaces/{workspace_id}/promote",
            json={"candidate_id": candidate_id, "approved": False},
        )
        assert no_approval.status_code == 403
        assert no_approval.json()["detail"]["code"] == "human_approval_required"
        assert not (repo / "quality-report.md").exists()

        promoted = client.post(
            f"/api/agent-workspaces/{workspace_id}/promote",
            json={"candidate_id": candidate_id, "approved": True, "approved_by": "api-reviewer"},
        )
        assert promoted.status_code == 200
        assert promoted.json()["status"] == "promoted"
        assert (repo / "quality-report.md").exists()

        missing = client.get("/api/agent-workspaces/aws-does-not-exist")
        assert missing.status_code == 404
        assert missing.json()["detail"]["code"] == "workspace_not_found"
    finally:
        manager.shutdown(wait=True)
