"""Safe session scaffold for the five-person vNext beginner study.

The tool launches only the formal /Applications candidate, gives every person
an isolated runtime home and preference suite, and records draft observations.
It never creates a passed release-evidence file and never accepts names, goals,
audio, or transcripts as command input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import shutil
import signal
import subprocess
import sys
import termios
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


SESSION_SCHEMA = "across-vnext-beginner-study-session/1.0"
FIXTURE_SCHEMA = "across-vnext-beginner-public-fixture/1.0"
RESULT_SCHEMA = "across-no-key-demo-result/1.0"
FORMAL_APP = Path("/Applications/Across Agents Assistant.app")
BUNDLE_ID = "app.acrossagents.assistant"
PREFERENCE_PREFIX = "app.acrossagents.assistant.beginner-study."
PROFILE_ID = re.compile(r"^study-profile-[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")
PARTICIPANT_ID = re.compile(r"^anonymous-[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")


def _read_hidden_goal(prompt: str) -> str:
    """Read a non-secret study goal without echoing or retaining the raw text."""
    descriptor = sys.stdin.fileno()
    original = termios.tcgetattr(descriptor)
    hidden = termios.tcgetattr(descriptor)
    hidden[3] &= ~termios.ECHO
    sys.stderr.write(prompt)
    sys.stderr.flush()
    try:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, hidden)
        return sys.stdin.readline().strip()
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, original)
        sys.stderr.write("\n")
        sys.stderr.flush()
RUN_ID = re.compile(r"^run-[A-Za-z0-9][A-Za-z0-9._-]{1,159}$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
FAILURE_REASONS = (
    "abandoned",
    "external_docs",
    "operator_help",
    "timeout",
    "wrong_action",
    "workflow_error",
)
COMPLETED_STEPS = (
    "choose_project",
    "install_capability",
    "enter_goal",
    "run_mission",
    "inspect_trust_compass",
    "inspect_evidence",
    "choose_final_action",
)
CONFUSION_CODES = (
    "choose_project",
    "install_capability",
    "goal_entry",
    "mission_start",
    "trust_compass",
    "evidence_path",
    "final_action",
    "timeout",
)


class StudySessionError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    data = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StudySessionError(f"invalid JSON artifact: {path}") from exc
    if not isinstance(payload, dict):
        raise StudySessionError(f"JSON artifact must be an object: {path}")
    return payload


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_bool(value: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "yes", "1"}:
        return True
    if normalized in {"false", "no", "0"}:
        return False
    raise argparse.ArgumentTypeError("expected yes/no or true/false")


def inspect_candidate(app_path: Path = FORMAL_APP) -> dict[str, Any]:
    if not app_path.is_dir():
        raise StudySessionError(f"formal candidate is missing: {app_path}")
    info_path = app_path / "Contents" / "Info.plist"
    try:
        with info_path.open("rb") as handle:
            info = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException) as exc:
        raise StudySessionError("candidate Info.plist is missing or invalid") from exc
    executable_name = str(info.get("CFBundleExecutable") or "")
    executable = app_path / "Contents" / "MacOS" / executable_name
    if info.get("CFBundleIdentifier") != BUNDLE_ID:
        raise StudySessionError("candidate bundle identifier is not the formal AAA identifier")
    if info.get("AcrossStudyProfileIsolationVersion") != 1:
        raise StudySessionError("candidate lacks the study-profile isolation marker; rebuild it before launching a study")
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise StudySessionError("candidate executable is missing or not executable")
    executable_bytes = executable.read_bytes()
    for marker in (b"ACROSS_STUDY_PROFILE_ID", b"ACROSS_AGENTS_PREFERENCES_SUITE"):
        if marker not in executable_bytes:
            raise StudySessionError("candidate marker exists but the executable lacks isolated-preference support")
    identity = {
        "app_path": str(app_path),
        "bundle_identifier": BUNDLE_ID,
        "version": str(info.get("CFBundleShortVersionString") or ""),
        "build_version": str(info.get("CFBundleVersion") or ""),
        "executable": executable_name,
        "executable_sha256": hashlib.sha256(executable_bytes).hexdigest(),
        "info_plist_sha256": _sha256_file(info_path),
        "study_profile_isolation_version": 1,
    }
    if not identity["version"]:
        raise StudySessionError("candidate version is missing")
    identity["fingerprint_sha256"] = hashlib.sha256(_canonical(identity)).hexdigest()
    return identity


def inspect_fixture(fixture_root: Path) -> dict[str, Any]:
    manifest_path = fixture_root / "fixture-manifest.json"
    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != FIXTURE_SCHEMA:
        raise StudySessionError("public fixture schema is invalid")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise StudySessionError("public fixture manifest has no files")
    expected_paths = set(files)
    actual_paths: set[str] = set()
    for path in fixture_root.rglob("*"):
        if path.is_symlink():
            raise StudySessionError("public fixture must not contain symlinks")
        if path.is_file() and path != manifest_path:
            actual_paths.add(path.relative_to(fixture_root).as_posix())
    if actual_paths != expected_paths:
        raise StudySessionError("public fixture file set does not match its manifest")
    for relative, expected_digest in files.items():
        path = fixture_root / str(relative)
        if not SHA256.fullmatch(str(expected_digest)) or _sha256_file(path) != expected_digest:
            raise StudySessionError(f"public fixture checksum mismatch: {relative}")
    privacy = manifest.get("privacy")
    if privacy != {
        "contains_credentials": False,
        "contains_private_data": False,
        "network_required": False,
    }:
        raise StudySessionError("public fixture privacy declaration is unsafe")
    return {
        "fixture_id": str(manifest.get("fixture_id") or ""),
        "manifest_sha256": _sha256_file(manifest_path),
        "file_count": len(files),
    }


def validate_result_artifact(path: Path, *, across_home: Path) -> dict[str, Any]:
    allowed_root = (across_home / "data" / "across-agents-assistant" / "beginner-study-results").resolve()
    resolved = path.resolve(strict=True)
    if resolved.parent != allowed_root:
        raise StudySessionError("result file is outside this isolated study profile")
    payload = _read_json(resolved)
    required = {
        "schema_version",
        "pattern_id",
        "mission_id",
        "run_id",
        "status",
        "verdict",
        "evidence_route",
        "gates",
        "policy",
        "evidence_sha256",
        "goal_sha256",
        "next_action_id",
        "next_action",
        "result_sha256",
    }
    if set(payload) != required:
        raise StudySessionError("result file is not the privacy-bounded study artifact")
    run_id = str(payload.get("run_id") or "")
    if payload.get("schema_version") != RESULT_SCHEMA or not RUN_ID.fullmatch(run_id):
        raise StudySessionError("result schema or run identifier is invalid")
    if payload.get("status") != "completed" or payload.get("verdict") != "verified":
        raise StudySessionError("successful study evidence requires a completed verified result")
    if (
        payload.get("pattern_id") != "first-verified-task"
        or payload.get("mission_id") != "first_verified_task"
    ):
        raise StudySessionError("result does not belong to the fixed first verified task")
    if payload.get("evidence_route") != f"run://{run_id}/evidence":
        raise StudySessionError("result evidence route does not match its run identifier")
    if payload.get("next_action_id") != "inspect_evidence":
        raise StudySessionError("fixed study result must require inspect_evidence")
    if not isinstance(payload.get("next_action"), str) or not payload["next_action"].strip():
        raise StudySessionError("fixed study result must explain its next action")
    for key in ("evidence_sha256", "goal_sha256", "result_sha256"):
        if not SHA256.fullmatch(str(payload.get(key) or "")):
            raise StudySessionError(f"result {key} is invalid")
    if payload.get("policy") != {
        "provider_key_used": False,
        "network_used": False,
        "model_calls": 0,
        "external_side_effects_performed": False,
    }:
        raise StudySessionError("result does not prove the read-only no-key policy")
    gates = payload.get("gates")
    if not isinstance(gates, list) or not gates:
        raise StudySessionError("result must include bounded gate evidence")
    for gate in gates:
        if not isinstance(gate, dict) or set(gate) != {"id", "status", "required"}:
            raise StudySessionError("result gate evidence is not bounded")
        if gate.get("required") is True and gate.get("status") != "passed":
            raise StudySessionError("result contains a failed required gate")
    claimed_result_sha256 = payload["result_sha256"]
    unhashed = {key: value for key, value in payload.items() if key != "result_sha256"}
    if hashlib.sha256(_canonical(unhashed)).hexdigest() != claimed_result_sha256:
        raise StudySessionError("result_sha256 does not match the compact result payload")
    evidence_path = across_home / "data" / "across-autopilot" / "runs" / run_id / "evidence.json"
    evidence = _read_json(evidence_path)
    integrity = evidence.get("integrity")
    if not isinstance(integrity, dict) or integrity.get("root_hash") != payload["evidence_sha256"]:
        raise StudySessionError("real run evidence does not match the bounded result")
    return {
        "payload": payload,
        "path": str(resolved),
        "file_sha256": _sha256_file(resolved),
        "evidence_path": str(evidence_path.resolve()),
    }


class StudySessionManager:
    def __init__(
        self,
        *,
        repository_root: Path,
        records_root: Path,
        app_path: Path = FORMAL_APP,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
        wall_now: Callable[[], str] = _iso_now,
        boot_id: Callable[[], str] | None = None,
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.records_root = records_root.expanduser().resolve()
        self.app_path = app_path
        self.fixture_root = self.repository_root / "fixtures" / "vnext-beginner-study-public"
        self.monotonic_ns = monotonic_ns
        self.wall_now = wall_now
        self.boot_id = boot_id or self._boot_id

    @property
    def session_dir(self) -> Path:
        return self.records_root / "sessions"

    @property
    def profile_dir(self) -> Path:
        return self.records_root / "profiles"

    @property
    def result_dir(self) -> Path:
        return self.records_root / "results"

    def preflight(self) -> dict[str, Any]:
        return {
            "schema_version": SESSION_SCHEMA,
            "status": "ready",
            "candidate": inspect_candidate(self.app_path),
            "fixture": inspect_fixture(self.fixture_root),
            "isolation": {
                "home": "per-session",
                "across_home": "per-session",
                "app_home": "per-session",
                "preferences": "validated-per-session-suite",
                "production_preference_domain_unchanged": True,
            },
            "release_evidence_created": False,
        }

    def start(
        self,
        *,
        participant_id: str,
        profile_id: str,
        self_reported_beginner: bool,
        not_involved_in_build: bool,
        anonymous_consent_observed: bool,
        readiness_timeout: float = 60.0,
    ) -> dict[str, Any]:
        self._validate_ids(participant_id, profile_id)
        preflight = self.preflight()
        session_path = self._session_path(profile_id)
        if session_path.exists():
            raise StudySessionError("profile_id already has a preserved study record; use a new fresh profile")
        for existing_path in self.session_dir.glob("*.json"):
            existing = _read_json(existing_path)
            if existing.get("participant_id") == participant_id:
                raise StudySessionError("participant_id already has a study record")
        candidate = preflight["candidate"]
        executable = self.app_path / "Contents" / "MacOS" / candidate["executable"]
        running = self._candidate_pids(executable)
        if running:
            raise StudySessionError("close the existing formal candidate before starting an isolated session")

        profile_root = self.profile_dir / profile_id
        if profile_root.exists():
            raise StudySessionError("fresh profile directory already exists")
        home = profile_root / "home"
        across_home = profile_root / "across-home"
        app_home = across_home / "data" / "across-agents-assistant"
        workspace = app_home / "workspace"
        tmp = profile_root / "tmp"
        for path in (home, across_home, app_home, tmp):
            path.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.fixture_root, workspace)
        copied_fixture = inspect_fixture(workspace)
        if copied_fixture != preflight["fixture"]:
            raise StudySessionError("copied public fixture fingerprint changed")

        nonce = os.urandom(16).hex()
        study_profile_token = hashlib.sha256(f"{profile_id}:{nonce}".encode("utf-8")).hexdigest()[:16]
        preference_suite = f"{PREFERENCE_PREFIX}{study_profile_token}"
        fresh_profile_preflight = self._inspect_fresh_profile(
            across_home=across_home,
            app_home=app_home,
            preference_suite=preference_suite,
        )
        launch_started_at = self.wall_now()
        launch_started_monotonic_ns = self.monotonic_ns()
        session: dict[str, Any] = {
            "schema_version": SESSION_SCHEMA,
            "status": "starting",
            "participant_id": participant_id,
            "fresh_profile_id": profile_id,
            "self_reported_beginner": self_reported_beginner,
            "not_involved_in_build": not_involved_in_build,
            "anonymous_consent_observed": anonymous_consent_observed,
            "candidate": candidate,
            "fixture": copied_fixture,
            "privacy": {
                "name_stored": False,
                "audio_stored": False,
                "transcript_stored": False,
                "goal_text_stored": False,
            },
            "profile": {
                "root": str(profile_root),
                "home": str(home),
                "across_home": str(across_home),
                "app_home": str(app_home),
                "workspace": str(workspace),
                "study_profile_token": study_profile_token,
                "preference_suite": preference_suite,
            },
            "launch_started_at": launch_started_at,
            "launch_started_monotonic_ns": launch_started_monotonic_ns,
            "boot_id": self.boot_id(),
            "fresh_profile_preflight": fresh_profile_preflight,
            "release_evidence_created": False,
            "finish_attempts": [],
        }
        _atomic_json(session_path, session)

        clean_env = self._launch_environment(
            home=home,
            across_home=across_home,
            app_home=app_home,
            tmp=tmp,
            study_profile_token=study_profile_token,
            preference_suite=preference_suite,
        )
        log_path = profile_root / "candidate.log"
        try:
            log_handle = log_path.open("ab", buffering=0)
            process = subprocess.Popen(
                [str(executable)],
                cwd=workspace,
                env=clean_env,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            log_handle.close()
        except Exception as exc:
            session.update({"status": "failed", "failure_reason": "workflow_error", "failed_at": self.wall_now()})
            _atomic_json(session_path, session)
            raise StudySessionError("formal candidate could not be launched") from exc

        session["pid"] = process.pid
        session["executable_path"] = str(executable)
        _atomic_json(session_path, session)
        socket_path = app_home / "run" / "across-agents.sock"
        deadline = time.monotonic() + max(1.0, readiness_timeout)
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            if socket_path.exists():
                session.update({
                    "status": "ready_for_timing",
                    "backend_socket": str(socket_path),
                })
                _atomic_json(session_path, session)
                return self._public_status(session)
            time.sleep(0.1)

        self._terminate_process(session)
        session.update({"status": "failed", "failure_reason": "workflow_error", "failed_at": self.wall_now()})
        _atomic_json(session_path, session)
        raise StudySessionError("formal candidate did not become ready; failure record was preserved")

    def begin(self, *, profile_id: str) -> dict[str, Any]:
        """Start the independent timer when the fresh Work screen is visible."""

        session = _read_json(self._session_path(profile_id))
        if session.get("status") != "ready_for_timing":
            raise StudySessionError("session is not ready to start timing")
        pid = session.get("pid")
        executable = str(session.get("executable_path") or "")
        if not isinstance(pid, int) or not self._pid_matches(pid, executable):
            raise StudySessionError("formal candidate stopped before the timed session began")
        session.update({
            "status": "running",
            "started_at": self.wall_now(),
            "started_monotonic_ns": self.monotonic_ns(),
            "boot_id": self.boot_id(),
        })
        _atomic_json(self._session_path(profile_id), session)
        return self._public_status(session)

    def finish(
        self,
        *,
        profile_id: str,
        outcome: str,
        external_docs: bool,
        operator_help: bool,
        observed_by_facilitator: bool,
        goal_input_method: str,
        capability_install_observed: bool,
        completed_steps: list[str],
        confusion_codes: list[str],
        failure_reason: str | None,
        actual_final_action: str,
        goal_sha256: str,
        result_file: Path | None,
    ) -> dict[str, Any]:
        session = self._load_running(profile_id)
        completed_at = self.wall_now()
        elapsed = self._elapsed_seconds(session)
        success_claimed = outcome == "success"
        self._validate_observation_lists(completed_steps, confusion_codes)
        validation_error: str | None = None
        result: dict[str, Any] | None = None
        if not SHA256.fullmatch(goal_sha256):
            validation_error = "participant goal_sha256 must be a lowercase SHA-256 digest"
        elif success_claimed:
            if session.get("self_reported_beginner") is not True:
                validation_error = "participant was not recorded as a beginner"
            elif session.get("not_involved_in_build") is not True:
                validation_error = "participant was involved in building the release"
            elif session.get("anonymous_consent_observed") is not True or not observed_by_facilitator:
                validation_error = "human consent and facilitator observation must be explicit"
            elif external_docs or operator_help:
                validation_error = "successful independent session cannot use external docs or operator help"
            elif not capability_install_observed:
                validation_error = "successful session must visibly install the required capability"
            elif set(completed_steps) != set(COMPLETED_STEPS):
                validation_error = "successful session must complete every fixed study step"
            elif result_file is None:
                validation_error = "successful session requires an explicit bounded result file"
            else:
                try:
                    result = validate_result_artifact(
                        result_file,
                        across_home=Path(session["profile"]["across_home"]),
                    )
                    if result["payload"]["goal_sha256"] != goal_sha256:
                        validation_error = "bounded result is not bound to the observed goal hash"
                    elif actual_final_action != result["payload"]["next_action_id"]:
                        validation_error = "participant did not choose the result-derived final action"
                    elif inspect_candidate(self.app_path)["fingerprint_sha256"] != session["candidate"]["fingerprint_sha256"]:
                        validation_error = "installed candidate changed during the session"
                except StudySessionError as exc:
                    validation_error = str(exc)
        elif failure_reason not in FAILURE_REASONS:
            validation_error = "failed finish requires a bounded failure reason"

        accepted_success = success_claimed and validation_error is None
        session["finish_attempts"].append({
            "at": completed_at,
            "outcome_claimed": outcome,
            "accepted": accepted_success or outcome == "failure",
            "error_code": "evidence_validation_failed" if validation_error else None,
        })
        session.update({
            "status": "draft_finished" if accepted_success else "draft_failed",
            "completed_at": completed_at,
            "completed_monotonic_ns": self.monotonic_ns(),
            "seconds": elapsed,
            "outcome_claimed": outcome,
            "validation_error": validation_error,
        })
        participant = {
            "participant_id": session["participant_id"],
            "fresh_profile_id": session["fresh_profile_id"],
            "self_reported_beginner": session["self_reported_beginner"],
            "not_involved_in_build": session["not_involved_in_build"],
            "anonymous_consent_observed": session["anonymous_consent_observed"],
            "observed_by_facilitator": observed_by_facilitator,
            "started_at": session["started_at"],
            "completed_at": completed_at,
            "seconds": elapsed,
            "success": accepted_success,
            "external_docs": external_docs,
            "operator_help": operator_help,
            "goal_input_method": goal_input_method,
            "goal_sha256": goal_sha256,
            "fresh_profile_preflight": session["fresh_profile_preflight"],
            "capability_install_observed": capability_install_observed,
            "completed_steps": list(dict.fromkeys(completed_steps)),
            "confusion_codes": list(dict.fromkeys(confusion_codes)),
        }
        if result is not None and accepted_success:
            preserved = self.result_dir / f"{profile_id}.json"
            preserved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(result["path"], preserved)
            os.chmod(preserved, 0o600)
            payload = result["payload"]
            participant.update({
                "actual_final_action": actual_final_action,
                "verified_result_id": payload["run_id"],
                "verified_result_path": str(preserved),
                "verified_result_file_sha256": _sha256_file(preserved),
                "verified_result_sha256": payload["result_sha256"],
                "verified_evidence_sha256": payload["evidence_sha256"],
            })
        elif not accepted_success:
            participant.update({
                "actual_final_action": actual_final_action,
                "failure_reason": failure_reason or "workflow_error",
            })
        session["participant_draft"] = participant
        self._terminate_process(session)
        _atomic_json(self._session_path(profile_id), session)
        _atomic_json(self.session_dir / f"{profile_id}.participant-draft.json", participant)
        return self._public_status(session)

    def fail(
        self,
        *,
        profile_id: str,
        reason: str,
        external_docs: bool,
        operator_help: bool,
        observed_by_facilitator: bool,
        goal_input_method: str,
        capability_install_observed: bool,
        completed_steps: list[str],
        confusion_codes: list[str],
        actual_final_action: str,
        goal_sha256: str,
    ) -> dict[str, Any]:
        if reason not in FAILURE_REASONS:
            raise StudySessionError("failure reason is not one of the bounded study codes")
        if not SHA256.fullmatch(goal_sha256):
            raise StudySessionError("participant goal_sha256 must be a lowercase SHA-256 digest")
        self._validate_observation_lists(completed_steps, confusion_codes)
        session = self._load_running(profile_id)
        completed_at = self.wall_now()
        elapsed = self._elapsed_seconds(session)
        participant = {
            "participant_id": session["participant_id"],
            "fresh_profile_id": session["fresh_profile_id"],
            "self_reported_beginner": session["self_reported_beginner"],
            "not_involved_in_build": session["not_involved_in_build"],
            "anonymous_consent_observed": session["anonymous_consent_observed"],
            "observed_by_facilitator": observed_by_facilitator,
            "started_at": session["started_at"],
            "completed_at": completed_at,
            "seconds": elapsed,
            "success": False,
            "external_docs": external_docs,
            "operator_help": operator_help,
            "goal_input_method": goal_input_method,
            "goal_sha256": goal_sha256,
            "fresh_profile_preflight": session["fresh_profile_preflight"],
            "capability_install_observed": capability_install_observed,
            "completed_steps": list(dict.fromkeys(completed_steps)),
            "confusion_codes": list(dict.fromkeys(confusion_codes)),
            "actual_final_action": actual_final_action,
            "failure_reason": reason,
        }
        session.update({
            "status": "draft_failed",
            "completed_at": completed_at,
            "completed_monotonic_ns": self.monotonic_ns(),
            "seconds": elapsed,
            "failure_reason": reason,
            "participant_draft": participant,
        })
        self._terminate_process(session)
        _atomic_json(self._session_path(profile_id), session)
        _atomic_json(self.session_dir / f"{profile_id}.participant-draft.json", participant)
        return self._public_status(session)

    def status(self, profile_id: str | None = None) -> dict[str, Any]:
        if profile_id:
            session = _read_json(self._session_path(profile_id))
            result_root = Path(session["profile"]["app_home"]) / "beginner-study-results"
            available_results = sorted(str(path) for path in result_root.glob("*.json"))
            public = self._public_status(session)
            public["available_result_files"] = available_results
            return public
        sessions = []
        for path in sorted(self.session_dir.glob("study-profile-*.json")):
            if path.name.endswith(".participant-draft.json"):
                continue
            sessions.append(self._public_status(_read_json(path)))
        return {
            "schema_version": SESSION_SCHEMA,
            "status": "draft_only",
            "sessions": sessions,
            "release_evidence_created": False,
        }

    def cleanup(self, *, profile_id: str) -> dict[str, Any]:
        session_path = self._session_path(profile_id)
        session = _read_json(session_path)
        if session.get("status") in {"starting", "ready_for_timing", "running"}:
            raise StudySessionError("finish or fail the active session before cleanup")
        profile = session.get("profile") or {}
        profile_root = Path(str(profile.get("root") or ""))
        if profile_root.resolve().parent != self.profile_dir.resolve():
            raise StudySessionError("refusing to clean a path outside the managed study profile root")
        shutil.rmtree(profile_root, ignore_errors=False) if profile_root.exists() else None
        suite = str(profile.get("preference_suite") or "")
        if suite.startswith(PREFERENCE_PREFIX):
            subprocess.run(
                ["/usr/bin/defaults", "delete", suite],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        session["profile_cleaned_at"] = self.wall_now()
        session["profile_data_preserved"] = False
        session["draft_record_preserved"] = True
        _atomic_json(session_path, session)
        return self._public_status(session)

    def _validate_ids(self, participant_id: str, profile_id: str) -> None:
        if not PARTICIPANT_ID.fullmatch(participant_id):
            raise StudySessionError("participant_id must be an anonymous-* identifier, never a name")
        if not PROFILE_ID.fullmatch(profile_id):
            raise StudySessionError("profile_id must be a bounded study-profile-* identifier")

    @staticmethod
    def _validate_observation_lists(completed_steps: list[str], confusion_codes: list[str]) -> None:
        if any(step not in COMPLETED_STEPS for step in completed_steps):
            raise StudySessionError("completed_steps contains an unknown fixed-protocol step")
        if any(code not in CONFUSION_CODES for code in confusion_codes):
            raise StudySessionError("confusion_codes contains an unknown bounded code")
        if len(confusion_codes) != len(set(confusion_codes)):
            raise StudySessionError("confusion_codes must not contain duplicates")

    def _session_path(self, profile_id: str) -> Path:
        if not PROFILE_ID.fullmatch(profile_id):
            raise StudySessionError("invalid study profile identifier")
        return self.session_dir / f"{profile_id}.json"

    def _load_running(self, profile_id: str) -> dict[str, Any]:
        session = _read_json(self._session_path(profile_id))
        if session.get("status") != "running":
            raise StudySessionError("session is not running")
        if session.get("boot_id") != self.boot_id():
            raise StudySessionError("Mac rebooted during the timed session; record it as failed")
        return session

    def _elapsed_seconds(self, session: Mapping[str, Any]) -> float:
        started = session.get("started_monotonic_ns")
        if not isinstance(started, int):
            raise StudySessionError("session has no monotonic start time")
        elapsed = (self.monotonic_ns() - started) / 1_000_000_000
        if elapsed < 0:
            raise StudySessionError("monotonic session timing is invalid")
        return round(elapsed, 3)

    def _terminate_process(self, session: Mapping[str, Any]) -> None:
        pid = session.get("pid")
        executable = str(session.get("executable_path") or "")
        if not isinstance(pid, int) or pid <= 1 or not executable:
            return
        if not self._pid_matches(pid, executable):
            return
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if not self._pid_matches(pid, executable):
                return
            time.sleep(0.1)
        if self._pid_matches(pid, executable):
            os.kill(pid, signal.SIGKILL)

    @staticmethod
    def _pid_matches(pid: int, executable: str) -> bool:
        completed = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "command="],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return completed.returncode == 0 and completed.stdout.strip().startswith(executable)

    @staticmethod
    def _candidate_pids(executable: Path) -> list[int]:
        completed = subprocess.run(
            ["/bin/ps", "-axo", "pid=,command="],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        values = []
        prefix = str(executable)
        for line in completed.stdout.splitlines():
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2 and parts[1].startswith(prefix):
                values.append(int(parts[0]))
        return values

    @staticmethod
    def _launch_environment(
        *,
        home: Path,
        across_home: Path,
        app_home: Path,
        tmp: Path,
        study_profile_token: str,
        preference_suite: str,
    ) -> dict[str, str]:
        source = os.environ
        env = {
            "HOME": str(home),
            "ACROSS_HOME": str(across_home),
            "ACROSS_AGENTS_HOME": str(app_home),
            "ACROSS_AGENTS_PRODUCT_MODE": "1",
            "ACROSS_STUDY_PROFILE_ID": study_profile_token,
            "ACROSS_AGENTS_PREFERENCES_SUITE": preference_suite,
            "TMPDIR": str(tmp),
            "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "USER": source.get("USER", ""),
            "LOGNAME": source.get("LOGNAME", ""),
            "SHELL": source.get("SHELL", "/bin/zsh"),
            "LANG": source.get("LANG", "en_US.UTF-8"),
        }
        for key in ("__CF_USER_TEXT_ENCODING", "LC_ALL", "LC_CTYPE"):
            if source.get(key):
                env[key] = source[key]
        return {key: value for key, value in env.items() if value}

    @staticmethod
    def _inspect_fresh_profile(
        *,
        across_home: Path,
        app_home: Path,
        preference_suite: str,
    ) -> dict[str, Any]:
        plugin_root = across_home / "plugins"
        plugins_before = sum(1 for path in plugin_root.iterdir() if path.is_dir()) if plugin_root.exists() else 0

        tasks_before = 0
        task_registry = app_home / "orchestrator-plugin" / "tasks.json"
        if task_registry.exists():
            task_payload = _read_json(task_registry)
            tasks = task_payload.get("tasks", task_payload)
            if isinstance(tasks, list):
                tasks_before = len(tasks)
            elif isinstance(tasks, Mapping):
                tasks_before = len(tasks)
            else:
                raise StudySessionError("fresh profile task registry is malformed")

        learning_events_before = 0
        learning_path = app_home / "learning-progress.json"
        if learning_path.exists():
            learning_payload = _read_json(learning_path)
            events = learning_payload.get("events")
            if not isinstance(events, list):
                raise StudySessionError("fresh profile learning ledger is malformed")
            learning_events_before = len(events)

        preference_probe = subprocess.run(
            ["/usr/bin/defaults", "read", preference_suite],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        isolated_preferences = preference_probe.returncode != 0
        result = {
            "plugins_before": plugins_before,
            "tasks_before": tasks_before,
            "learning_events_before": learning_events_before,
            "isolated_preferences": isolated_preferences,
        }
        if result != {
            "plugins_before": 0,
            "tasks_before": 0,
            "learning_events_before": 0,
            "isolated_preferences": True,
        }:
            raise StudySessionError("study profile is not fresh")
        return result

    @staticmethod
    def _boot_id() -> str:
        completed = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "kern.boottime"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        value = completed.stdout.strip() if completed.returncode == 0 else ""
        if not value:
            value = "unknown-boot"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _public_status(session: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": SESSION_SCHEMA,
            "status": session.get("status"),
            "participant_id": session.get("participant_id"),
            "fresh_profile_id": session.get("fresh_profile_id"),
            "candidate_fingerprint_sha256": (session.get("candidate") or {}).get("fingerprint_sha256"),
            "fixture_id": (session.get("fixture") or {}).get("fixture_id"),
            "started_at": session.get("started_at"),
            "seconds": session.get("seconds"),
            "validation_error": session.get("validation_error"),
            "participant_draft": session.get("participant_draft"),
            "release_evidence_created": False,
        }


def _default_records_root() -> Path:
    return Path.home() / ".across" / "data" / "across-agents-assistant" / "release-reports" / "vnext-beginner-study-sessions"


def _manager() -> StudySessionManager:
    repository_root = Path(__file__).resolve().parents[3]
    return StudySessionManager(repository_root=repository_root, records_root=_default_records_root())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run isolated draft sessions for the vNext beginner study")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight")
    subparsers.add_parser("hash-goal")

    start = subparsers.add_parser("start")
    start.add_argument("--participant-id", required=True)
    start.add_argument("--profile-id", required=True)
    start.add_argument("--self-reported-beginner", required=True, type=_parse_bool)
    start.add_argument("--not-involved-in-build", required=True, type=_parse_bool)
    start.add_argument("--anonymous-consent-observed", required=True, type=_parse_bool)
    start.add_argument("--readiness-timeout", type=float, default=60.0)

    begin = subparsers.add_parser("begin")
    begin.add_argument("--profile-id", required=True)

    finish = subparsers.add_parser("finish")
    finish.add_argument("--profile-id", required=True)
    finish.add_argument("--outcome", choices=("success", "failure"), required=True)
    finish.add_argument("--external-docs", required=True, type=_parse_bool)
    finish.add_argument("--operator-help", required=True, type=_parse_bool)
    finish.add_argument("--observed-by-facilitator", required=True, type=_parse_bool)
    finish.add_argument("--goal-input-method", choices=("voice", "keyboard"), required=True)
    finish.add_argument("--goal-sha256", required=True)
    finish.add_argument("--capability-install-observed", required=True, type=_parse_bool)
    finish.add_argument("--completed-step", choices=COMPLETED_STEPS, action="append", required=True)
    finish.add_argument("--confusion-code", choices=CONFUSION_CODES, action="append", default=[])
    finish.add_argument("--failure-reason", choices=FAILURE_REASONS)
    finish.add_argument("--actual-final-action", required=True)
    finish.add_argument("--result-file", type=Path)

    fail = subparsers.add_parser("fail")
    fail.add_argument("--profile-id", required=True)
    fail.add_argument("--reason", choices=FAILURE_REASONS, required=True)
    fail.add_argument("--external-docs", required=True, type=_parse_bool)
    fail.add_argument("--operator-help", required=True, type=_parse_bool)
    fail.add_argument("--observed-by-facilitator", required=True, type=_parse_bool)
    fail.add_argument("--goal-input-method", choices=("voice", "keyboard"), required=True)
    fail.add_argument("--goal-sha256", required=True)
    fail.add_argument("--capability-install-observed", required=True, type=_parse_bool)
    fail.add_argument("--completed-step", choices=COMPLETED_STEPS, action="append", required=True)
    fail.add_argument("--confusion-code", choices=CONFUSION_CODES, action="append", default=[])
    fail.add_argument("--actual-final-action", default="none")

    status = subparsers.add_parser("status")
    status.add_argument("--profile-id")
    cleanup = subparsers.add_parser("cleanup")
    cleanup.add_argument("--profile-id", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manager = _manager()
    try:
        if args.command == "preflight":
            result = manager.preflight()
        elif args.command == "hash-goal":
            if not sys.stdin.isatty():
                raise StudySessionError("hash-goal requires an interactive terminal so raw goal text is not echoed")
            goal = _read_hidden_goal("Goal text (hashed only; never stored): ")
            if not goal:
                raise StudySessionError("goal text cannot be blank")
            result = {
                "schema_version": SESSION_SCHEMA,
                "status": "hashed",
                # This is a non-secret content fingerprint used for result binding;
                # SHA-256 must match the Autopilot result contract.
                "goal_sha256": hashlib.sha256(goal.encode("utf-8")).hexdigest(),
                "raw_goal_stored": False,
                "release_evidence_created": False,
            }
        elif args.command == "start":
            result = manager.start(
                participant_id=args.participant_id,
                profile_id=args.profile_id,
                self_reported_beginner=args.self_reported_beginner,
                not_involved_in_build=args.not_involved_in_build,
                anonymous_consent_observed=args.anonymous_consent_observed,
                readiness_timeout=args.readiness_timeout,
            )
        elif args.command == "begin":
            result = manager.begin(profile_id=args.profile_id)
        elif args.command == "finish":
            result = manager.finish(
                profile_id=args.profile_id,
                outcome=args.outcome,
                external_docs=args.external_docs,
                operator_help=args.operator_help,
                observed_by_facilitator=args.observed_by_facilitator,
                goal_input_method=args.goal_input_method,
                capability_install_observed=args.capability_install_observed,
                completed_steps=args.completed_step,
                confusion_codes=args.confusion_code,
                failure_reason=args.failure_reason,
                actual_final_action=args.actual_final_action,
                goal_sha256=args.goal_sha256,
                result_file=args.result_file,
            )
        elif args.command == "fail":
            result = manager.fail(
                profile_id=args.profile_id,
                reason=args.reason,
                external_docs=args.external_docs,
                operator_help=args.operator_help,
                observed_by_facilitator=args.observed_by_facilitator,
                goal_input_method=args.goal_input_method,
                capability_install_observed=args.capability_install_observed,
                completed_steps=args.completed_step,
                confusion_codes=args.confusion_code,
                actual_final_action=args.actual_final_action,
                goal_sha256=args.goal_sha256,
            )
        elif args.command == "status":
            result = manager.status(args.profile_id)
        else:
            result = manager.cleanup(profile_id=args.profile_id)
    except StudySessionError as exc:
        print(json.dumps({
            "schema_version": SESSION_SCHEMA,
            "status": "error",
            "error": str(exc),
            "release_evidence_created": False,
        }, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
