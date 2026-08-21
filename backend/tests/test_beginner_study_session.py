import hashlib
import json
import os
import plistlib
import shutil
from pathlib import Path

import pytest

from across_agents_assistant.beginner_study_artifacts import (
    persist_beginner_study_result,
    sanitized_beginner_study_result,
)
from across_agents_assistant.beginner_study_session import (
    COMPLETED_STEPS,
    CONFUSION_CODES,
    StudySessionError,
    StudySessionManager,
    inspect_candidate,
    inspect_fixture,
    validate_result_artifact,
)
from across_agents_assistant.release_evidence import (
    BEGINNER_CONFUSION_CODES,
    BEGINNER_REQUIRED_STEPS,
)


def canonical_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fake_candidate(root: Path) -> Path:
    app = root / "Across Agents Assistant.app"
    executable = app / "Contents" / "MacOS" / "AcrossAgentsAssistant"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(
        b"fake-mach-o\0ACROSS_STUDY_PROFILE_ID\0ACROSS_AGENTS_PREFERENCES_SUITE\0"
    )
    executable.chmod(0o755)
    info = {
        "CFBundleIdentifier": "app.acrossagents.assistant",
        "CFBundleExecutable": executable.name,
        "CFBundleShortVersionString": "0.14.0",
        "CFBundleVersion": "0.14.0",
        "AcrossStudyProfileIsolationVersion": 1,
    }
    info_path = app / "Contents" / "Info.plist"
    with info_path.open("wb") as handle:
        plistlib.dump(info, handle)
    return app


def bounded_result(run_id: str = "run-study-fixture-1") -> dict:
    payload = {
        "schema_version": "across-no-key-demo-result/1.0",
        "pattern_id": "first-verified-task",
        "mission_id": "first_verified_task",
        "run_id": run_id,
        "status": "completed",
        "verdict": "verified",
        "evidence_route": f"run://{run_id}/evidence",
        "gates": [
            {"id": "source_reachable", "status": "passed", "required": True},
            {"id": "manifest_readable", "status": "passed", "required": True},
            {"id": "license_acceptable", "status": "passed", "required": True},
        ],
        "policy": {
            "provider_key_used": False,
            "network_used": False,
            "model_calls": 0,
            "external_side_effects_performed": False,
        },
        "evidence_sha256": "a" * 64,
        "goal_sha256": "b" * 64,
        "next_action_id": "inspect_evidence",
        "next_action": "Open the evidence.",
    }
    payload["result_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return payload


def test_study_result_persistence_is_opt_in_and_strips_goal(tmp_path):
    unsafe = {
        **bounded_result(),
        "goal": "private words must never be stored",
        "transcript": "also private",
        "project_dir": "/private/repository",
    }
    env = {"HOME": str(tmp_path), "ACROSS_HOME": str(tmp_path / "across")}
    assert persist_beginner_study_result(unsafe, env=env) is None

    env["ACROSS_STUDY_PROFILE_ID"] = "0123456789abcdef"
    path = persist_beginner_study_result(unsafe, env=env)
    assert path is not None
    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted == sanitized_beginner_study_result(unsafe)
    assert "goal" not in persisted
    assert "transcript" not in persisted
    assert "project_dir" not in persisted

    tampered = dict(unsafe)
    tampered["next_action_id"] = "approve"
    assert sanitized_beginner_study_result(tampered) is None
    assert persist_beginner_study_result(tampered, env=env) is None


def test_study_helper_uses_the_exact_release_protocol_vocabulary():
    assert set(COMPLETED_STEPS) == BEGINNER_REQUIRED_STEPS
    assert set(CONFUSION_CODES) == BEGINNER_CONFUSION_CODES


def test_candidate_requires_marker_and_both_isolation_environment_literals(tmp_path):
    app = fake_candidate(tmp_path)
    candidate = inspect_candidate(app)
    assert candidate["bundle_identifier"] == "app.acrossagents.assistant"
    assert len(candidate["fingerprint_sha256"]) == 64

    executable = app / "Contents" / "MacOS" / "AcrossAgentsAssistant"
    executable.write_bytes(b"fake-mach-o-without-runtime-support")
    executable.chmod(0o755)
    with pytest.raises(StudySessionError, match="lacks isolated-preference support"):
        inspect_candidate(app)


def test_fixed_public_fixture_manifest_detects_any_change(tmp_path):
    source = Path(__file__).resolve().parents[2] / "fixtures" / "vnext-beginner-study-public"
    fixture = tmp_path / "fixture"
    shutil.copytree(source, fixture)
    assert inspect_fixture(fixture)["fixture_id"] == "pocket-checklist-1.0.0"
    (fixture / "README.md").write_text("changed\n", encoding="utf-8")
    with pytest.raises(StudySessionError, match="checksum mismatch"):
        inspect_fixture(fixture)


def test_result_artifact_must_match_real_isolated_run_evidence(tmp_path):
    across_home = tmp_path / "across"
    payload = bounded_result()
    result_path = across_home / "data" / "across-agents-assistant" / "beginner-study-results" / "run-study-fixture-1.json"
    evidence_path = across_home / "data" / "across-autopilot" / "runs" / "run-study-fixture-1" / "evidence.json"
    canonical_file(result_path, payload)
    canonical_file(evidence_path, {"integrity": {"root_hash": "a" * 64}})

    result = validate_result_artifact(result_path, across_home=across_home)
    assert result["payload"]["run_id"] == "run-study-fixture-1"
    assert result["file_sha256"] == hashlib.sha256(result_path.read_bytes()).hexdigest()

    payload["evidence_sha256"] = "d" * 64
    canonical_file(result_path, payload)
    with pytest.raises(StudySessionError, match="does not match"):
        validate_result_artifact(result_path, across_home=across_home)


def test_explicit_success_creates_only_a_verified_draft_fragment(tmp_path):
    repository = Path(__file__).resolve().parents[2]
    app = fake_candidate(tmp_path / "candidate")
    records = tmp_path / "records"
    manager = StudySessionManager(
        repository_root=repository,
        records_root=records,
        app_path=app,
        monotonic_ns=lambda: 370_000_000_000,
        wall_now=lambda: "2026-07-15T06:00:00Z",
        boot_id=lambda: "boot-1",
    )
    profile_id = "study-profile-1"
    profile_root = records / "profiles" / profile_id
    across_home = profile_root / "across-home"
    app_home = across_home / "data" / "across-agents-assistant"
    result_path = app_home / "beginner-study-results" / "run-study-fixture-1.json"
    evidence_path = across_home / "data" / "across-autopilot" / "runs" / "run-study-fixture-1" / "evidence.json"
    canonical_file(result_path, bounded_result())
    canonical_file(evidence_path, {"integrity": {"root_hash": "a" * 64}})
    session = {
        "schema_version": "across-vnext-beginner-study-session/1.0",
        "status": "running",
        "participant_id": "anonymous-1",
        "fresh_profile_id": profile_id,
        "self_reported_beginner": True,
        "not_involved_in_build": True,
        "anonymous_consent_observed": True,
        "candidate": inspect_candidate(app),
        "fixture": {"fixture_id": "pocket-checklist-1.0.0"},
        "profile": {
            "root": str(profile_root),
            "across_home": str(across_home),
            "app_home": str(app_home),
        },
        "started_at": "2026-07-15T05:54:00Z",
        "started_monotonic_ns": 10_000_000_000,
        "boot_id": "boot-1",
        "fresh_profile_preflight": {
            "plugins_before": 0,
            "tasks_before": 0,
            "learning_events_before": 0,
            "isolated_preferences": True,
        },
        "finish_attempts": [],
        "release_evidence_created": False,
    }
    canonical_file(manager.session_dir / f"{profile_id}.json", session)

    status = manager.finish(
        profile_id=profile_id,
        outcome="success",
        external_docs=False,
        operator_help=False,
        observed_by_facilitator=True,
        goal_input_method="keyboard",
        capability_install_observed=True,
        completed_steps=list(COMPLETED_STEPS),
        confusion_codes=[],
        failure_reason=None,
        actual_final_action="inspect_evidence",
        goal_sha256="b" * 64,
        result_file=result_path,
    )

    assert status["status"] == "draft_finished"
    assert status["release_evidence_created"] is False
    participant = status["participant_draft"]
    assert participant["success"] is True
    assert participant["seconds"] == 360
    assert participant["verified_result_sha256"] == bounded_result()["result_sha256"]
    assert participant["verified_evidence_sha256"] == "a" * 64
    assert participant["goal_sha256"] == "b" * 64
    assert participant["actual_final_action"] == "inspect_evidence"
    assert Path(participant["verified_result_path"]).is_file()
    assert not (records / "vnext-beginner-study-evidence.json").exists()


def test_success_claim_without_real_result_is_preserved_as_failed_draft(tmp_path):
    repository = Path(__file__).resolve().parents[2]
    app = fake_candidate(tmp_path / "candidate")
    records = tmp_path / "records"
    manager = StudySessionManager(
        repository_root=repository,
        records_root=records,
        app_path=app,
        monotonic_ns=lambda: 11_000_000_000,
        wall_now=lambda: "2026-07-15T06:00:01Z",
        boot_id=lambda: "boot-1",
    )
    profile_id = "study-profile-2"
    profile_root = records / "profiles" / profile_id
    profile_root.mkdir(parents=True)
    session = {
        "schema_version": "across-vnext-beginner-study-session/1.0",
        "status": "running",
        "participant_id": "anonymous-2",
        "fresh_profile_id": profile_id,
        "self_reported_beginner": True,
        "not_involved_in_build": True,
        "anonymous_consent_observed": True,
        "candidate": inspect_candidate(app),
        "fixture": {"fixture_id": "pocket-checklist-1.0.0"},
        "profile": {
            "root": str(profile_root),
            "across_home": str(profile_root / "across-home"),
            "app_home": str(profile_root / "app-home"),
        },
        "started_at": "2026-07-15T06:00:00Z",
        "started_monotonic_ns": 10_000_000_000,
        "boot_id": "boot-1",
        "fresh_profile_preflight": {
            "plugins_before": 0,
            "tasks_before": 0,
            "learning_events_before": 0,
            "isolated_preferences": True,
        },
        "finish_attempts": [],
        "release_evidence_created": False,
    }
    canonical_file(manager.session_dir / f"{profile_id}.json", session)

    status = manager.finish(
        profile_id=profile_id,
        outcome="success",
        external_docs=False,
        operator_help=False,
        observed_by_facilitator=True,
        goal_input_method="keyboard",
        capability_install_observed=True,
        completed_steps=list(COMPLETED_STEPS),
        confusion_codes=[],
        failure_reason=None,
        actual_final_action="inspect_evidence",
        goal_sha256="b" * 64,
        result_file=None,
    )

    assert status["status"] == "draft_failed"
    assert status["participant_draft"]["success"] is False
    assert "explicit bounded result file" in status["validation_error"]


def test_success_claim_cannot_replace_the_participants_actual_final_action(tmp_path):
    repository = Path(__file__).resolve().parents[2]
    app = fake_candidate(tmp_path / "candidate")
    records = tmp_path / "records"
    manager = StudySessionManager(
        repository_root=repository,
        records_root=records,
        app_path=app,
        monotonic_ns=lambda: 20_000_000_000,
        wall_now=lambda: "2026-07-15T06:00:10Z",
        boot_id=lambda: "boot-1",
    )
    profile_id = "study-profile-wrong-action"
    profile_root = records / "profiles" / profile_id
    across_home = profile_root / "across-home"
    app_home = across_home / "data" / "across-agents-assistant"
    result_path = app_home / "beginner-study-results" / "run-study-fixture-1.json"
    evidence_path = across_home / "data" / "across-autopilot" / "runs" / "run-study-fixture-1" / "evidence.json"
    canonical_file(result_path, bounded_result())
    canonical_file(evidence_path, {"integrity": {"root_hash": "a" * 64}})
    canonical_file(manager.session_dir / f"{profile_id}.json", {
        "schema_version": "across-vnext-beginner-study-session/1.0",
        "status": "running",
        "participant_id": "anonymous-wrong-action",
        "fresh_profile_id": profile_id,
        "self_reported_beginner": True,
        "not_involved_in_build": True,
        "anonymous_consent_observed": True,
        "candidate": inspect_candidate(app),
        "fixture": {"fixture_id": "pocket-checklist-1.0.0"},
        "profile": {
            "root": str(profile_root),
            "across_home": str(across_home),
            "app_home": str(app_home),
        },
        "started_at": "2026-07-15T06:00:00Z",
        "started_monotonic_ns": 10_000_000_000,
        "boot_id": "boot-1",
        "fresh_profile_preflight": {
            "plugins_before": 0,
            "tasks_before": 0,
            "learning_events_before": 0,
            "isolated_preferences": True,
        },
        "finish_attempts": [],
        "release_evidence_created": False,
    })

    status = manager.finish(
        profile_id=profile_id,
        outcome="success",
        external_docs=False,
        operator_help=False,
        observed_by_facilitator=True,
        goal_input_method="keyboard",
        capability_install_observed=True,
        completed_steps=list(COMPLETED_STEPS),
        confusion_codes=[],
        failure_reason="wrong_action",
        actual_final_action="approve",
        goal_sha256="b" * 64,
        result_file=result_path,
    )

    assert status["status"] == "draft_failed"
    assert status["participant_draft"]["success"] is False
    assert status["participant_draft"]["actual_final_action"] == "approve"
    assert status["participant_draft"]["failure_reason"] == "wrong_action"
    assert "result-derived final action" in status["validation_error"]


def test_begin_starts_timing_only_after_the_fresh_screen_is_ready(tmp_path, monkeypatch):
    manager = StudySessionManager(
        repository_root=Path(__file__).resolve().parents[2],
        records_root=tmp_path / "records",
        app_path=fake_candidate(tmp_path / "candidate"),
        monotonic_ns=lambda: 12_345,
        wall_now=lambda: "2026-07-15T06:00:00Z",
        boot_id=lambda: "boot-1",
    )
    profile_id = "study-profile-timer"
    canonical_file(manager.session_dir / f"{profile_id}.json", {
        "schema_version": "across-vnext-beginner-study-session/1.0",
        "status": "ready_for_timing",
        "participant_id": "anonymous-timer",
        "fresh_profile_id": profile_id,
        "pid": 123,
        "executable_path": "/Applications/fake",
        "candidate": {"fingerprint_sha256": "a" * 64},
        "fixture": {"fixture_id": "pocket-checklist-1.0.0"},
    })
    monkeypatch.setattr(manager, "_pid_matches", lambda pid, executable: True)

    status = manager.begin(profile_id=profile_id)
    stored = json.loads((manager.session_dir / f"{profile_id}.json").read_text())

    assert status["status"] == "running"
    assert stored["started_at"] == "2026-07-15T06:00:00Z"
    assert stored["started_monotonic_ns"] == 12_345
    assert stored["boot_id"] == "boot-1"


def test_launch_environment_is_no_key_and_uses_matching_private_suite(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    env = StudySessionManager._launch_environment(
        home=tmp_path / "home",
        across_home=tmp_path / "across",
        app_home=tmp_path / "app",
        tmp=tmp_path / "tmp",
        study_profile_token="0123456789abcdef",
        preference_suite="app.acrossagents.assistant.beginner-study.0123456789abcdef",
    )
    assert "OPENAI_API_KEY" not in env
    assert env["ACROSS_STUDY_PROFILE_ID"] == "0123456789abcdef"
    assert env["ACROSS_AGENTS_PREFERENCES_SUITE"].endswith(env["ACROSS_STUDY_PROFILE_ID"])
    assert env["HOME"] != os.environ["HOME"]
