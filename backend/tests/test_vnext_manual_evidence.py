from __future__ import annotations

import hashlib
import json
import sys
import struct
import zlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import plistlib

from across_agents_assistant.release_evidence import (
    BEGINNER_SCHEMA,
    RELEASE_DECISION_SCHEMA,
    UI_SCHEMA,
    VOICE_SCHEMA,
    validate_manual_evidence,
    validate_release_decision,
)


APP = {
    "app_path": "/Applications/Across Agents Assistant.app",
    "version": "0.13.0",
    "bundle_identifier": "app.acrossagents.assistant",
    "executable_sha256": "a" * 64,
}
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_vnext_synthetic_beginner_evidence import (  # noqa: E402
    SYNTHETIC_BEGINNER_SCHEMA,
    validate_synthetic_beginner_evidence,
)


def stamp(offset_seconds: int = 0) -> str:
    return (
        datetime(2026, 7, 15, 1, 0, tzinfo=timezone.utc)
        + timedelta(seconds=offset_seconds)
    ).isoformat()


def png_bytes(width: int = 640, height: int = 400, tone: int = 0) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    pixel = bytes((tone % 256, 0, 0))
    rows = b"".join(b"\x00" + (pixel * width) for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def ui_payload(tmp_path):
    combinations = [
        ("work", "zh-Hans", "dark", False, "default"),
        ("memory", "zh-Hans", "dark", False, "default"),
        ("workflows", "zh-Hans", "dark", False, "default"),
        ("loop_engineering", "zh-Hans", "dark", False, "default"),
        ("growth", "en", "light", True, "full-size"),
        ("settings", "en", "light", True, "full-size"),
        ("task_detail", "en", "light", True, "full-size"),
        ("approval", "en", "light", True, "full-size"),
    ]
    observations = []
    for index, (screen, locale, appearance, reduce_motion, window_mode) in enumerate(combinations):
        screenshot = tmp_path / f"observation-{index}.png"
        screenshot.write_bytes(png_bytes(tone=index + 1))
        observations.append({
            "screen": screen,
            "observed_at": stamp(len(screen)),
            "locale": locale,
            "appearance": appearance,
            "reduce_motion": reduce_motion,
            "window_mode": window_mode,
            "checks": ["no clipping", "state has a text equivalent"],
            "screenshot_path": str(screenshot),
            "screenshot_sha256": hashlib.sha256(screenshot.read_bytes()).hexdigest(),
        })
    return {
        "schema_version": UI_SCHEMA,
        "status": "passed",
        "completed_at": stamp(60),
        "summary": "Observed every required packaged screen and interaction.",
        "candidate": APP,
        "observations": observations,
        "interaction_observations": ui_interaction_observations(),
    }


def ui_interaction_observations():
    details = {
        "window_default_1280x800": {"window_frame": {"width": 1280, "height": 800}},
        "window_full_size_reversible": {
            "full_size_frame": {"width": 1920, "height": 1050},
            "restored_frame": {"width": 1280, "height": 800},
        },
        "project_detail_linkage": {
            "matching_project_selected": True,
            "switch_exited_unrelated_detail": True,
        },
        "approve_archive_idempotent": {
            "approve_observed": True,
            "archive_observed": True,
            "immediate_refresh": True,
            "stable_result": True,
            "repeat_count": 2,
        },
        "decision_mark_receipt_bound": {
            "receipt_id": "approval-fixture",
            "receipt_sha256": "b" * 64,
            "subject_id_sha256": "c" * 64,
            "integrity_status": "verified",
        },
        "keyboard_focus": {
            "controls_checked": 12,
            "all_reachable": True,
            "focus_visible": True,
        },
        "voiceover_labels": {
            "controls_checked": 12,
            "all_labeled": True,
            "state_not_color_only": True,
        },
        "loading_empty_error": {
            "states": ["loading", "empty", "error"],
            "recovery_action_observed": True,
        },
        "plugin_lifecycle_preserves_data": {
            "states": ["install", "upgrade", "repair", "uninstall"],
            "data_preserved": True,
            "module_visibility_updated": True,
        },
    }
    return [
        {
            "check": check,
            "observed_at": stamp(index),
            "summary": f"Observed the real packaged interaction for {check}.",
            "details": item,
        }
        for index, (check, item) in enumerate(details.items(), start=1)
    ]


def voice_payload():
    def session(locale, index):
        states = [
            "listening",
            "pause-without-transcription",
            "finish",
            "transcribing-full-recording",
            "transcript-ready",
            "edit",
            "explicit-submit",
            "cancel",
        ]
        if locale == "zh-Hans":
            states = ["permission", *states, "denied", "unavailable"]
        return {
            "session_id": f"voice-{index}",
            "locale": locale,
            "real_microphone": True,
            "started_at": stamp(index * 60),
            "completed_at": stamp(index * 60 + 45),
            "events": [
                {"state": state, "observed_at": stamp(index * 60 + event_index * 4 + 1)}
                for event_index, state in enumerate(states)
            ],
            "editable_draft_observed": True,
            "explicit_submit_observed": True,
            "cancel_without_submit_observed": True,
            "tts_stopped_before_listening": True,
            "pause_did_not_publish_draft": True,
            "full_recording_transcribed_once": True,
            "privacy": {
                "raw_audio_persisted": False,
                "full_transcript_persisted": False,
                "public_evidence_contains_transcript": False,
            },
        }

    return {
        "schema_version": VOICE_SCHEMA,
        "status": "passed",
        "completed_at": stamp(180),
        "summary": "Observed two real microphone sessions without retained speech data.",
        "candidate": APP,
        "sessions": [session("zh-Hans", 1), session("en-US", 2)],
    }


def release_decision_payload():
    return {
        "schema_version": RELEASE_DECISION_SCHEMA,
        "decision": "authorized",
        "authorized_at": stamp(240),
        "summary": "The product owner authorized this release and accepted the bounded residual microphone hardware risk.",
        "candidate": APP,
        "voice_hardware_gate": {
            "status": "waived",
            "scope": "remaining-real-microphone-edge-paths",
            "reason_code": "product-owner-accepted-residual-hardware-risk",
            "core_chinese_observed": True,
            "core_english_observed": True,
            "remaining_edges_not_tested": True,
            "no_full_coverage_claim": True,
        },
    }


def canonical_sha256(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def beginner_payload(tmp_path):
    participants = []
    for index, seconds in enumerate((300, 360, 420, 450, 600), start=1):
        goal_sha256 = hashlib.sha256(f"private goal {index}".encode()).hexdigest()
        participant = {
            "participant_id": f"anonymous-{index}",
            "fresh_profile_id": f"study-profile-{index}",
            "self_reported_beginner": True,
            "not_involved_in_build": True,
            "anonymous_consent_observed": True,
            "observed_by_facilitator": True,
            "goal_input_method": "voice" if index % 2 else "keyboard",
            "goal_sha256": goal_sha256,
            "fresh_profile_preflight": {
                "plugins_before": 0,
                "tasks_before": 0,
                "learning_events_before": 0,
                "isolated_preferences": True,
            },
            "started_at": stamp(index * 1000),
            "completed_at": stamp(index * 1000 + seconds),
            "seconds": seconds,
            "success": index <= 4,
            "external_docs": False,
            "operator_help": False,
            "capability_install_observed": index <= 4,
            "completed_steps": sorted(BEGINNER_STEPS if index <= 4 else {"choose_project", "install_capability"}),
            "confusion_codes": [] if index <= 4 else ["timeout"],
            "actual_final_action": "inspect_evidence" if index <= 4 else "",
        }
        if index <= 4:
            run_id = f"run-study-{index}"
            result = {
                "schema_version": "across-no-key-demo-result/1.0",
                "pattern_id": "first-verified-task",
                "mission_id": "first_verified_task",
                "run_id": run_id,
                "status": "completed",
                "verdict": "verified",
                "evidence_route": f"run://{run_id}/evidence",
                "gates": [{"id": "fixture", "status": "passed", "required": True}],
                "policy": {
                    "provider_key_used": False,
                    "network_used": False,
                    "model_calls": 0,
                    "external_side_effects_performed": False,
                },
                "evidence_sha256": hashlib.sha256(f"evidence-{index}".encode()).hexdigest(),
                "goal_sha256": goal_sha256,
                "next_action": "Open the evidence.",
                "next_action_id": "inspect_evidence",
            }
            result["result_sha256"] = canonical_sha256(result)
            result_path = tmp_path / f"beginner-result-{index}.json"
            result_path.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
            participant.update({
                "verified_result_id": run_id,
                "verified_result_path": str(result_path),
                "verified_result_file_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
                "verified_result_sha256": result["result_sha256"],
                "verified_evidence_sha256": result["evidence_sha256"],
            })
        else:
            participant["failure_reason"] = "timeout"
        participants.append(participant)
    return {
        "schema_version": BEGINNER_SCHEMA,
        "status": "passed",
        "completed_at": stamp(7000),
        "summary": "Five independent beginner sessions completed the fixed protocol.",
        "candidate": APP,
        "participants": participants,
    }


def synthetic_beginner_payload(tmp_path):
    human = beginner_payload(tmp_path)
    fifth = deepcopy(human["participants"][0])
    fifth["participant_id"] = "anonymous-5"
    fifth["fresh_profile_id"] = "study-profile-5"
    fifth["started_at"] = stamp(5000)
    fifth["completed_at"] = stamp(5300)
    fifth["seconds"] = 300
    fifth["goal_sha256"] = hashlib.sha256(b"private synthetic goal 5").hexdigest()
    fifth_result_path = tmp_path / "beginner-result-synthetic-5.json"
    first_result = json.loads(Path(fifth["verified_result_path"]).read_text(encoding="utf-8"))
    first_result["run_id"] = "run-study-synthetic-5"
    first_result["evidence_route"] = "run://run-study-synthetic-5/evidence"
    first_result["evidence_sha256"] = hashlib.sha256(b"synthetic-evidence-5").hexdigest()
    first_result["goal_sha256"] = fifth["goal_sha256"]
    first_result.pop("result_sha256")
    first_result["result_sha256"] = canonical_sha256(first_result)
    fifth_result_path.write_text(json.dumps(first_result, sort_keys=True) + "\n", encoding="utf-8")
    fifth.update({
        "verified_result_id": first_result["run_id"],
        "verified_result_path": str(fifth_result_path),
        "verified_result_file_sha256": hashlib.sha256(fifth_result_path.read_bytes()).hexdigest(),
        "verified_result_sha256": first_result["result_sha256"],
        "verified_evidence_sha256": first_result["evidence_sha256"],
    })
    human["participants"][4] = fifth

    personas = []
    for index, participant in enumerate(human.pop("participants"), start=1):
        for key in (
            "participant_id",
            "self_reported_beginner",
            "not_involved_in_build",
            "anonymous_consent_observed",
            "observed_by_facilitator",
        ):
            participant.pop(key, None)
        participant.update({
            "persona_id": f"synthetic-beginner-{index}",
            "simulated_ai_beginner": True,
            "human_participant": False,
            "goal_input_method": "simulated-keyboard",
        })
        personas.append(participant)
    human.update({
        "schema_version": SYNTHETIC_BEGINNER_SCHEMA,
        "summary": "Five isolated AI-beginner simulations completed the no-key product path; this is not human research.",
        "product_owner_decision": {
            "real_human_study_deferred": True,
            "synthetic_substitute_for_this_release": True,
            "recorded_at": stamp(),
        },
        "limitations": {
            "not_human_research": True,
            "does_not_measure_real_user_comprehension": True,
            "must_not_be_described_as_participant_evidence": True,
        },
        "personas": personas,
    })
    return human


BEGINNER_STEPS = {
    "choose_project",
    "install_capability",
    "enter_goal",
    "run_mission",
    "inspect_trust_compass",
    "inspect_evidence",
    "choose_final_action",
}


def validate(gate_id, payload, tmp_path):
    return validate_manual_evidence(
        gate_id,
        payload,
        report_root=tmp_path,
        expected_version="0.13.0",
    )


def test_minimal_self_attestation_cannot_pass(tmp_path):
    status, error = validate(
        "packaged_ui_sweep",
        {
            "status": "passed",
            "completed_at": stamp(),
            "summary": "A long enough but unsupported pass assertion.",
            "screens": ["work", "memory"],
        },
        tmp_path,
    )
    assert status == "failed"
    assert "schema_version" in error


def test_complete_ui_observations_pass(tmp_path):
    assert validate("packaged_ui_sweep", ui_payload(tmp_path), tmp_path) == ("passed", None)


def test_candidate_fingerprint_is_required_and_can_bind_the_installed_binary(tmp_path, monkeypatch):
    missing = ui_payload(tmp_path)
    missing["candidate"] = deepcopy(APP)
    missing["candidate"].pop("executable_sha256")
    assert "executable_sha256" in validate("packaged_ui_sweep", missing, tmp_path)[1]

    app_path = tmp_path / "Across Agents Assistant.app"
    executable = app_path / "Contents" / "MacOS" / "AcrossAgentsAssistant"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"candidate executable")
    info_path = app_path / "Contents" / "Info.plist"
    with info_path.open("wb") as handle:
        plistlib.dump({
            "CFBundleIdentifier": "app.acrossagents.assistant",
            "CFBundleShortVersionString": "0.13.0",
            "CFBundleExecutable": "AcrossAgentsAssistant",
        }, handle)
    monkeypatch.setattr(
        "across_agents_assistant.release_evidence.PACKAGED_APP_PATH",
        str(app_path),
    )
    bound = ui_payload(tmp_path)
    bound["candidate"] = {
        "app_path": str(app_path),
        "version": "0.13.0",
        "bundle_identifier": "app.acrossagents.assistant",
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
    }
    assert validate_manual_evidence(
        "packaged_ui_sweep",
        bound,
        report_root=tmp_path,
        expected_version="0.13.0",
        verify_installed_candidate=True,
    ) == ("passed", None)
    executable.write_bytes(b"changed candidate")
    assert "executable hash" in validate_manual_evidence(
        "packaged_ui_sweep",
        bound,
        report_root=tmp_path,
        expected_version="0.13.0",
        verify_installed_candidate=True,
    )[1]


def test_ui_screenshot_tampering_is_rejected(tmp_path):
    payload = ui_payload(tmp_path)
    Path(payload["observations"][0]["screenshot_path"]).write_bytes(b"changed")
    status, error = validate("packaged_ui_sweep", payload, tmp_path)
    assert status == "failed"
    assert "hash does not match" in error


def test_ui_screenshot_must_be_a_real_png_not_just_a_png_filename(tmp_path):
    payload = ui_payload(tmp_path)
    screenshot = Path(payload["observations"][0]["screenshot_path"])
    screenshot.write_bytes(b"\xff\xd8\xffrenamed-jpeg")
    screenshot_hash = hashlib.sha256(screenshot.read_bytes()).hexdigest()
    payload["observations"][0]["screenshot_sha256"] = screenshot_hash
    status, error = validate("packaged_ui_sweep", payload, tmp_path)
    assert status == "failed"
    assert "not a valid PNG" in error


def test_ui_screenshot_must_be_large_enough_to_inspect(tmp_path):
    payload = ui_payload(tmp_path)
    screenshot = Path(payload["observations"][0]["screenshot_path"])
    screenshot.write_bytes(png_bytes(width=32, height=32))
    screenshot_hash = hashlib.sha256(screenshot.read_bytes()).hexdigest()
    payload["observations"][0]["screenshot_sha256"] = screenshot_hash
    status, error = validate("packaged_ui_sweep", payload, tmp_path)
    assert status == "failed"
    assert "too small" in error


def test_ui_rejects_reused_screenshots_and_unstructured_interaction_claims(tmp_path):
    reused = ui_payload(tmp_path)
    reused["observations"][1]["screenshot_path"] = reused["observations"][0]["screenshot_path"]
    reused["observations"][1]["screenshot_sha256"] = reused["observations"][0]["screenshot_sha256"]
    assert "unique screenshot" in validate("packaged_ui_sweep", reused, tmp_path)[1]

    unstructured = ui_payload(tmp_path)
    unstructured.pop("interaction_observations")
    unstructured["interaction_checks"] = list({item["check"] for item in ui_interaction_observations()})
    assert "structured UI interaction" in validate(
        "packaged_ui_sweep", unstructured, tmp_path
    )[1]


def test_complete_real_voice_sessions_pass(tmp_path):
    assert validate("voice_hardware_smoke", voice_payload(), tmp_path) == ("passed", None)


def test_release_decision_accepts_only_a_bounded_voice_waiver():
    assert validate_release_decision(
        release_decision_payload(), expected_version="0.13.0"
    ) == ("passed", None)

    overclaim = release_decision_payload()
    overclaim["voice_hardware_gate"]["no_full_coverage_claim"] = False
    assert "no_full_coverage_claim" in validate_release_decision(
        overclaim, expected_version="0.13.0"
    )[1]

    private = release_decision_payload()
    private["voice_hardware_gate"]["transcript"] = "private speech"
    assert "audio or transcript" in validate_release_decision(
        private, expected_version="0.13.0"
    )[1]


def test_voice_evidence_rejects_transcripts_and_missing_hardware(tmp_path):
    with_transcript = voice_payload()
    with_transcript["sessions"][0]["transcript"] = "must not be retained"
    assert "raw audio or transcript" in validate(
        "voice_hardware_smoke", with_transcript, tmp_path
    )[1]

    without_hardware = voice_payload()
    without_hardware["sessions"][0]["real_microphone"] = False
    assert "real microphone" in validate(
        "voice_hardware_smoke", without_hardware, tmp_path
    )[1]


def test_voice_evidence_requires_ordered_timestamped_states(tmp_path):
    unordered = voice_payload()
    unordered["sessions"][0]["events"][1], unordered["sessions"][0]["events"][2] = (
        unordered["sessions"][0]["events"][2],
        unordered["sessions"][0]["events"][1],
    )
    assert "timestamp order" in validate("voice_hardware_smoke", unordered, tmp_path)[1]

    missing_recovery = voice_payload()
    missing_recovery["sessions"][0]["events"] = [
        event
        for event in missing_recovery["sessions"][0]["events"]
        if event["state"] not in {"denied", "unavailable"}
    ]
    assert "recovery states" in validate(
        "voice_hardware_smoke", missing_recovery, tmp_path
    )[1]

    pause_published_a_draft = voice_payload()
    pause_published_a_draft["sessions"][0]["pause_did_not_publish_draft"] = False
    assert "pause_did_not_publish_draft" in validate(
        "voice_hardware_smoke", pause_published_a_draft, tmp_path
    )[1]


def test_complete_beginner_study_passes(tmp_path):
    assert validate("beginner_human_study", beginner_payload(tmp_path), tmp_path) == ("passed", None)


def test_complete_synthetic_beginner_evidence_passes_without_claiming_humans(tmp_path):
    payload = synthetic_beginner_payload(tmp_path)
    assert validate_synthetic_beginner_evidence(
        payload,
        report_root=tmp_path,
        expected_version="0.13.0",
    ) == ("passed", None)

    false_human_claim = deepcopy(payload)
    false_human_claim["personas"][0]["human_participant"] = True
    assert "must not claim to be human" in validate_synthetic_beginner_evidence(
        false_human_claim,
        report_root=tmp_path,
        expected_version="0.13.0",
    )[1]

    missing_limitations = deepcopy(payload)
    missing_limitations.pop("limitations")
    assert "non-human limitations" in validate_synthetic_beginner_evidence(
        missing_limitations,
        report_root=tmp_path,
        expected_version="0.13.0",
    )[1]


def test_beginner_study_rejects_duplicate_profiles_and_unproven_results(tmp_path):
    duplicate = beginner_payload(tmp_path)
    duplicate["participants"][1]["fresh_profile_id"] = "study-profile-1"
    assert "fresh_profile_id" in validate(
        "beginner_human_study", duplicate, tmp_path
    )[1]

    no_result = beginner_payload(tmp_path)
    no_result["participants"][0]["verified_result_sha256"] = ""
    assert "result hash" in validate(
        "beginner_human_study", no_result, tmp_path
    )[1]


def test_beginner_study_rejects_inconsistent_timing_and_slow_median(tmp_path):
    inconsistent = beginner_payload(tmp_path)
    inconsistent["participants"][0]["seconds"] = 1
    assert "duration does not match" in validate(
        "beginner_human_study", inconsistent, tmp_path
    )[1]

    slow = beginner_payload(tmp_path)
    for participant in slow["participants"][:4]:
        participant["seconds"] = 600
        participant["completed_at"] = (
            datetime.fromisoformat(participant["started_at"]) + timedelta(seconds=600)
        ).isoformat()
    assert "exceeds eight minutes" in validate(
        "beginner_human_study", slow, tmp_path
    )[1]


def test_beginner_study_binds_goal_result_and_repeated_confusion(tmp_path):
    goal_mismatch = beginner_payload(tmp_path)
    goal_mismatch["participants"][0]["goal_sha256"] = "f" * 64
    assert "entered goal" in validate(
        "beginner_human_study", goal_mismatch, tmp_path
    )[1]

    tampered = beginner_payload(tmp_path)
    result_path = Path(tampered["participants"][0]["verified_result_path"])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["next_action_id"] = "approve"
    result_path.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    tampered["participants"][0]["verified_result_file_sha256"] = hashlib.sha256(
        result_path.read_bytes()
    ).hexdigest()
    assert "inspect_evidence" in validate(
        "beginner_human_study", tampered, tmp_path
    )[1]

    repeated = beginner_payload(tmp_path)
    repeated["participants"][0]["confusion_codes"] = ["evidence_path"]
    repeated["participants"][1]["confusion_codes"] = ["evidence_path"]
    assert "repeated beginner confusion" in validate(
        "beginner_human_study", repeated, tmp_path
    )[1]


def test_beginner_study_rejects_private_identity_fields_and_zero_duration(tmp_path):
    private = beginner_payload(tmp_path)
    private["participants"][0]["name"] = "Private Person"
    assert "must not contain identity" in validate(
        "beginner_human_study", private, tmp_path
    )[1]

    zero = beginner_payload(tmp_path)
    zero["participants"][0]["seconds"] = 0
    zero["participants"][0]["completed_at"] = zero["participants"][0]["started_at"]
    assert "invalid duration" in validate("beginner_human_study", zero, tmp_path)[1]


def test_wrong_candidate_version_is_rejected(tmp_path):
    payload = ui_payload(tmp_path)
    payload["candidate"] = deepcopy(APP)
    payload["candidate"]["version"] = "0.10.0"
    assert "candidate version" in validate("packaged_ui_sweep", payload, tmp_path)[1]


def test_acceptance_runner_cannot_report_success_when_summary_generation_fails():
    script = (ROOT / "scripts/run_vnext_single_release_acceptance.sh").read_text(encoding="utf-8")
    assert 'python3 - <<\'PY\' || SUMMARY_GENERATION_EXIT="$?"' in script
    assert 'if [[ "$SUMMARY_GENERATION_EXIT" -ne 0 ]]' in script
    assert 'exit "$SUMMARY_GENERATION_EXIT"' in script
    assert "import tomllib" not in script
    assert '"waived"' in script
