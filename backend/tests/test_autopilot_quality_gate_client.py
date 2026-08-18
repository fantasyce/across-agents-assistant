from pathlib import Path

import pytest

import across_agents_assistant.autopilot_client as autopilot_client
from across_agents_assistant.autopilot_client import AutopilotClient
from across_agents_assistant.plugin_runtime import PluginLifecycleError


def _gate_payload() -> dict:
    return {
        "schema_version": "across-autopilot-gate-result/1.0",
        "repository": {"name": "fixture"},
        "base_ref": "main",
        "head_ref": "feature",
        "head_sha": "abc123",
        "dirty_tree": False,
        "diff_summary": {"changed_files": ["src/example.py"]},
        "findings": [],
        "gate_verdict": "pass",
        "evidence_hash": "a" * 64,
        "pr_ready_summary": "PR-ready: checks passed with no blocking findings.",
    }


def test_gate_uses_managed_autopilot_contract(monkeypatch, tmp_path: Path):
    captured = {}
    ci_path = tmp_path / "ci.json"
    ci_path.write_text("{}\n", encoding="utf-8")

    def fake_run(args, *, env=None, timeout=60, allowed_returncodes=None):
        captured.update(
            args=args,
            env=env,
            timeout=timeout,
            allowed_returncodes=allowed_returncodes,
        )
        return _gate_payload()

    monkeypatch.setattr(autopilot_client, "run_autopilot_cli_json", fake_run)
    payload = AutopilotClient(env={"ACROSS_HOME": str(tmp_path / "across")}).gate(
        str(tmp_path),
        base_ref="main",
        head_ref="feature",
        branch="feature",
        commit="abc123",
        ci_path=str(ci_path),
        draft_pr=True,
        max_repairs=2,
        timeout=120,
    )

    assert captured["args"] == [
        "gate",
        "--repo",
        str(tmp_path.resolve()),
        "--base-ref",
        "main",
        "--head-ref",
        "feature",
        "--branch",
        "feature",
        "--commit",
        "abc123",
        "--ci-path",
        str(ci_path.resolve()),
        "--draft-pr",
        "--max-repairs",
        "2",
        "--json",
    ]
    assert captured["timeout"] == 120
    assert captured["allowed_returncodes"] == frozenset({0, 2})
    assert payload["gate_verdict"] == "pass"


def test_trigger_dispatch_claims_before_preparation_and_runs_claimed_item(monkeypatch, tmp_path: Path):
    calls = []

    def fake_run(args, *, env=None, timeout=60, allowed_returncodes=None, cwd=None):
        calls.append(list(args))
        if args[1] == "claim-trigger":
            return {
                "status": "claimed",
                "trigger": {
                    "trigger_id": "trg-two-phase",
                    "spec_id": "generic-loop",
                },
            }
        if args[1] == "run-claimed-trigger":
            return {"status": "completed", "run": {"run_id": "run-two-phase"}}
        raise AssertionError(args)

    client = AutopilotClient(env={"ACROSS_HOME": str(tmp_path / "across")})
    monkeypatch.setattr(autopilot_client, "run_autopilot_cli_json", fake_run)
    monkeypatch.setattr(
        AutopilotClient,
        "_refresh_source_mirrors_if_needed",
        lambda self, spec: calls.append(["prepare", spec]),
    )
    monkeypatch.setattr(AutopilotClient, "_candidate_retention_required", lambda self, spec: False)

    result = client.run_trigger("trg-two-phase")

    assert result["status"] == "completed"
    assert calls == [
        ["loop", "claim-trigger", "--json", "--trigger-id", "trg-two-phase", "--lease-ms", "300000"],
        ["prepare", "generic-loop"],
        ["loop", "run-claimed-trigger", "--trigger-id", "trg-two-phase", "--json"],
    ]


def test_trigger_dispatch_releases_claim_when_preparation_fails(monkeypatch, tmp_path: Path):
    calls = []

    def fake_run(args, *, env=None, timeout=60, allowed_returncodes=None, cwd=None):
        calls.append(list(args))
        if args[1] == "claim-trigger":
            return {"status": "claimed", "trigger": {"trigger_id": "trg-release", "spec_id": "generic-loop"}}
        if args[1] == "release-trigger":
            return {"status": "pending", "trigger": {"trigger_id": "trg-release", "status": "pending"}}
        raise AssertionError(args)

    client = AutopilotClient(env={"ACROSS_HOME": str(tmp_path / "across")})
    monkeypatch.setattr(autopilot_client, "run_autopilot_cli_json", fake_run)
    monkeypatch.setattr(AutopilotClient, "_candidate_retention_required", lambda self, spec: False)
    monkeypatch.setattr(
        AutopilotClient,
        "_refresh_source_mirrors_if_needed",
        lambda self, spec: (_ for _ in ()).throw(RuntimeError("offline")),
    )

    with pytest.raises(RuntimeError, match="offline"):
        client.run_trigger("trg-release")

    assert calls[0][1] == "claim-trigger"
    assert calls[1][1] == "release-trigger"
    assert "--retry-after-ms" in calls[1]
    assert not any(call[1:2] == ["run-claimed-trigger"] for call in calls)


def test_gate_passes_explicit_remote_intent_and_preserves_redacted_recovery_evidence(monkeypatch, tmp_path: Path):
    captured = {}
    github_token = "github_pat_fixture_remote_credential"
    approval_token = "host-approval-fixture"
    custom_policy_token = "custom-policy-host-credential"

    def fake_run(args, *, env=None, timeout=60, allowed_returncodes=None):
        captured.update(args=args, env=env, timeout=timeout, allowed_returncodes=allowed_returncodes)
        return {
            **_gate_payload(),
            "github_remote": {
                "status": "failed",
                "recoverable": True,
                "authorization": {
                    "approval_token_env": "ACROSS_REPO_GATE_APPROVAL_TOKEN",
                    "approval_token_verified": True,
                    "credential_present": True,
                    "secret_material_included": False,
                },
                "ci_watch": {
                    "status": "idle_timeout",
                    "heartbeats": [{"sequence": 3, "snapshot_sha256": "b" * 64}],
                },
                "operations": [
                    {
                        "id": "draft_pr",
                        "status": "unknown_after_attempt",
                        "recovery": "rerun_with_same_idempotency_key",
                    }
                ],
                "errors": [f"transport failed with {github_token}, {approval_token}, and {custom_policy_token}"],
                "auth_token": github_token,
            },
        }

    monkeypatch.setattr(autopilot_client, "run_autopilot_cli_json", fake_run)
    payload = AutopilotClient(
        env={
            "ACROSS_HOME": str(tmp_path / "across"),
            "GH_TOKEN": github_token,
            "ACROSS_REPO_GATE_APPROVAL_TOKEN": approval_token,
            "CUSTOM_REMOTE_CREDENTIAL": custom_policy_token,
        }
    ).gate(
        str(tmp_path),
        draft_pr=True,
        push_branch=True,
        approve_remote=True,
        watch_ci=True,
        ci_idle_timeout_seconds=30,
        ci_max_wall_timeout_seconds=120,
        timeout=60,
    )

    assert captured["args"][-10:] == [
        "--draft-pr",
        "--push-branch",
        "--approve-remote",
        "--watch-ci",
        "true",
        "--ci-idle-timeout-ms",
        "30000",
        "--ci-max-wall-timeout-ms",
        "120000",
        "--json",
    ]
    assert captured["timeout"] == 240
    assert "--approval-token" not in captured["args"]
    assert "--auth-token" not in captured["args"]
    assert captured["env"]["GH_TOKEN"] == github_token
    serialized = str(payload)
    assert github_token not in serialized
    assert approval_token not in serialized
    assert custom_policy_token not in serialized
    assert payload["github_remote"]["ci_watch"]["heartbeats"][0]["sequence"] == 3
    assert payload["github_remote"]["operations"][0]["recovery"] == "rerun_with_same_idempotency_key"
    assert payload["github_remote"]["authorization"]["approval_token_env"] == "ACROSS_REPO_GATE_APPROVAL_TOKEN"


def test_gate_default_has_no_remote_mutation_intent(monkeypatch, tmp_path: Path):
    captured = {}

    def fake_run(args, **kwargs):
        captured.update(args=args, **kwargs)
        return {**_gate_payload(), "github_remote": {"status": "not_requested", "mutation_performed": False}}

    monkeypatch.setattr(autopilot_client, "run_autopilot_cli_json", fake_run)
    payload = AutopilotClient().gate(str(tmp_path))

    assert not {"--push-branch", "--approve-remote", "--draft-pr"}.intersection(captured["args"])
    assert payload["github_remote"] == {"status": "not_requested", "mutation_performed": False}


def test_gate_rejects_missing_repo_and_invalid_repair_budget(tmp_path: Path):
    client = AutopilotClient()

    with pytest.raises(ValueError, match="existing directory"):
        client.gate(str(tmp_path / "missing"))
    with pytest.raises(ValueError, match="between 0 and 10"):
        client.gate(str(tmp_path), max_repairs=11)
    with pytest.raises(ValueError, match="ci_path must be an existing file"):
        client.gate(str(tmp_path), ci_path=str(tmp_path / "missing-ci.json"))
    with pytest.raises(ValueError, match="between 0 and 900"):
        client.gate(str(tmp_path), ci_wait_seconds=901)
    with pytest.raises(ValueError, match="ci_idle_timeout_seconds must be between"):
        client.gate(str(tmp_path), ci_idle_timeout_seconds=0)
    with pytest.raises(ValueError, match="ci_max_wall_timeout_seconds must be between"):
        client.gate(str(tmp_path), ci_max_wall_timeout_seconds=14_401)
    with pytest.raises(ValueError, match="must not exceed"):
        client.gate(str(tmp_path), ci_idle_timeout_seconds=120, ci_max_wall_timeout_seconds=60)


def test_gate_rejects_incompatible_plugin_payload(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        autopilot_client,
        "run_autopilot_cli_json",
        lambda *args, **kwargs: {"schema_version": "legacy-gate/0.1"},
    )

    with pytest.raises(PluginLifecycleError, match="incompatible gate result"):
        AutopilotClient().gate(str(tmp_path))
