"""Strict validation for the vNext manual release evidence files.

The validator deliberately checks observable records rather than accepting a
top-level "passed" assertion. It does not claim to replace a human test; it
prevents incomplete or privacy-unsafe evidence from authorizing the final gate.
"""

from __future__ import annotations

import hashlib
import json
import plistlib
import re
import statistics
import struct
import zlib
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


UI_SCHEMA = "across-vnext-ui-manual-evidence/1.0"
VOICE_SCHEMA = "across-vnext-voice-hardware-evidence/1.2"
BEGINNER_SCHEMA = "across-vnext-beginner-study-evidence/1.0"
RELEASE_DECISION_SCHEMA = "across-vnext-release-decision/1.0"
PACKAGED_APP_PATH = "/Applications/Across Agents Assistant.app"
PACKAGED_APP_BUNDLE_ID = "app.acrossagents.assistant"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
BEGINNER_RUN_ID_PATTERN = re.compile(r"^run-[A-Za-z0-9][A-Za-z0-9._-]{1,159}$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MIN_SCREENSHOT_WIDTH = 640
MIN_SCREENSHOT_HEIGHT = 400
MAX_SCREENSHOT_DIMENSION = 20_000
MAX_SCREENSHOT_FILE_BYTES = 100 * 1024 * 1024
MAX_SCREENSHOT_DECOMPRESSED_BYTES = 128 * 1024 * 1024

REQUIRED_UI_SCREENS = {
    "work",
    "memory",
    "workflows",
    "loop_engineering",
    "growth",
    "settings",
    "task_detail",
    "approval",
}
REQUIRED_UI_CHECKS = {
    "window_default_1280x800",
    "window_full_size_reversible",
    "project_detail_linkage",
    "approve_archive_idempotent",
    "decision_mark_receipt_bound",
    "keyboard_focus",
    "voiceover_labels",
    "loading_empty_error",
    "plugin_lifecycle_preserves_data",
}
REQUIRED_VOICE_SESSION_STATES = {
    "listening",
    "pause-without-transcription",
    "finish",
    "transcribing-full-recording",
    "transcript-ready",
    "edit",
    "explicit-submit",
    "cancel",
}
REQUIRED_VOICE_GLOBAL_STATES = {
    "permission",
    "denied",
    "unavailable",
}
VOICE_CORE_SEQUENCE = (
    "listening",
    "pause-without-transcription",
    "finish",
    "transcribing-full-recording",
    "transcript-ready",
    "edit",
    "explicit-submit",
    "cancel",
)
FORBIDDEN_VOICE_KEYS = {
    "audio",
    "audio_data",
    "audio_path",
    "final_text",
    "partial_text",
    "raw_audio",
    "raw_transcript",
    "recognized_text",
    "transcript",
    "transcript_text",
    "utterance",
}
ALLOWED_VOICE_PRIVACY_KEYS = {
    "full_transcript_persisted",
    "public_evidence_contains_transcript",
}
BEGINNER_REQUIRED_STEPS = {
    "choose_project",
    "install_capability",
    "enter_goal",
    "run_mission",
    "inspect_trust_compass",
    "inspect_evidence",
    "choose_final_action",
}
BEGINNER_CONFUSION_CODES = {
    "choose_project",
    "install_capability",
    "goal_entry",
    "mission_start",
    "trust_compass",
    "evidence_path",
    "final_action",
    "timeout",
}
BEGINNER_FAILURE_REASONS = {
    "abandoned",
    "external_docs",
    "operator_help",
    "timeout",
    "wrong_action",
    "workflow_error",
}
FORBIDDEN_BEGINNER_KEYS = {
    "audio",
    "audio_path",
    "contact",
    "email",
    "full_name",
    "goal",
    "name",
    "project_path",
    "raw_audio",
    "raw_transcript",
    "recording",
    "repository_path",
    "screen_recording",
    "transcript",
    "user_goal",
}


def _is_iso8601(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validated_png_dimensions(path: Path) -> tuple[int, int] | None:
    """Return dimensions only for a structurally valid, decodable PNG.

    An extension check is not enough for release evidence: a JPEG renamed to
    ``.png`` must be rejected. Validate the PNG signature, chunk order and CRCs,
    then decompress the complete image-data stream before accepting it.
    """

    try:
        if path.stat().st_size > MAX_SCREENSHOT_FILE_BYTES:
            return None
        payload = path.read_bytes()
    except OSError:
        return None
    if not payload.startswith(PNG_SIGNATURE):
        return None

    offset = len(PNG_SIGNATURE)
    dimensions: tuple[int, int] | None = None
    idat = bytearray()
    saw_iend = False
    chunk_index = 0
    while offset + 12 <= len(payload):
        length = struct.unpack(">I", payload[offset:offset + 4])[0]
        chunk_type = payload[offset + 4:offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(payload):
            return None
        chunk_data = payload[data_start:data_end]
        expected_crc = struct.unpack(">I", payload[data_end:crc_end])[0]
        if zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF != expected_crc:
            return None
        if chunk_index == 0:
            if chunk_type != b"IHDR" or length != 13:
                return None
            width, height = struct.unpack(">II", chunk_data[:8])
            if (
                width <= 0
                or height <= 0
                or width > MAX_SCREENSHOT_DIMENSION
                or height > MAX_SCREENSHOT_DIMENSION
            ):
                return None
            dimensions = (width, height)
        elif chunk_type == b"IHDR":
            return None
        if chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            if length != 0:
                return None
            saw_iend = True
            offset = crc_end
            break
        offset = crc_end
        chunk_index += 1

    if dimensions is None or not idat or not saw_iend or offset != len(payload):
        return None
    try:
        decoder = zlib.decompressobj()
        decoded = decoder.decompress(bytes(idat), MAX_SCREENSHOT_DECOMPRESSED_BYTES + 1)
        if (
            not decoded
            or len(decoded) > MAX_SCREENSHOT_DECOMPRESSED_BYTES
            or decoder.unconsumed_tail
            or not decoder.eof
        ):
            return None
    except zlib.error:
        return None
    return dimensions


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _contains_forbidden_voice_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key in FORBIDDEN_VOICE_KEYS or (
                "transcript" in normalized_key
                and normalized_key not in ALLOWED_VOICE_PRIVACY_KEYS
            ):
                return True
            if _contains_forbidden_voice_key(item):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_voice_key(item) for item in value)
    return False


def _contains_forbidden_beginner_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key in FORBIDDEN_BEGINNER_KEYS or "transcript" in normalized_key:
                return True
            if _contains_forbidden_beginner_key(item):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_beginner_key(item) for item in value)
    return False


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_base(candidate: Mapping[str, Any]) -> str | None:
    if candidate.get("status") != "passed":
        return "status must be passed"
    if not _is_iso8601(candidate.get("completed_at")):
        return "completed_at must be an ISO-8601 timestamp"
    summary = candidate.get("summary")
    if not isinstance(summary, str) or len(summary.strip()) < 20:
        return "summary must describe the observed result"
    return None


def _validate_candidate(
    candidate: Mapping[str, Any],
    *,
    expected_version: str | None,
    verify_installed_candidate: bool,
) -> str | None:
    observed = candidate.get("candidate")
    if not isinstance(observed, Mapping):
        return "candidate identity is required"
    if observed.get("app_path") != PACKAGED_APP_PATH:
        return "manual evidence must come from the /Applications candidate"
    version = observed.get("version")
    if not isinstance(version, str) or not version:
        return "candidate version is required"
    if expected_version and version != expected_version:
        return f"candidate version must be {expected_version}"
    if observed.get("bundle_identifier") != PACKAGED_APP_BUNDLE_ID:
        return f"candidate bundle_identifier must be {PACKAGED_APP_BUNDLE_ID}"
    executable_sha256 = str(observed.get("executable_sha256") or "")
    if not SHA256_PATTERN.fullmatch(executable_sha256):
        return "candidate executable_sha256 is required"
    if verify_installed_candidate:
        app_path = Path(PACKAGED_APP_PATH)
        info_path = app_path / "Contents" / "Info.plist"
        try:
            with info_path.open("rb") as handle:
                info = plistlib.load(handle)
        except (OSError, plistlib.InvalidFileException):
            return "installed candidate Info.plist is missing or invalid"
        if info.get("CFBundleIdentifier") != PACKAGED_APP_BUNDLE_ID:
            return "installed candidate bundle identifier does not match"
        if info.get("CFBundleShortVersionString") != version:
            return "installed candidate version does not match the evidence"
        executable_name = info.get("CFBundleExecutable")
        if (
            not isinstance(executable_name, str)
            or not executable_name
            or Path(executable_name).name != executable_name
        ):
            return "installed candidate executable name is invalid"
        executable = app_path / "Contents" / "MacOS" / executable_name
        if not executable.is_file():
            return "installed candidate executable is missing"
        if _sha256_file(executable) != executable_sha256:
            return "installed candidate executable hash does not match the evidence"
    return None


def _frame(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, Mapping):
        return None
    width = value.get("width")
    height = value.get("height")
    if (
        not isinstance(width, int)
        or isinstance(width, bool)
        or not isinstance(height, int)
        or isinstance(height, bool)
        or width <= 0
        or height <= 0
    ):
        return None
    return width, height


def _positive_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_ui_interaction_details(check: str, details: Mapping[str, Any]) -> str | None:
    if check == "window_default_1280x800":
        if _frame(details.get("window_frame")) != (1280, 800):
            return "window_frame must record the 1280x800 default"
    elif check == "window_full_size_reversible":
        full_size = _frame(details.get("full_size_frame"))
        if full_size is None or (full_size[0] <= 1280 and full_size[1] <= 800):
            return "full_size_frame must be larger than the default"
        if _frame(details.get("restored_frame")) != (1280, 800):
            return "restored_frame must return to 1280x800"
    elif check == "project_detail_linkage":
        if details.get("matching_project_selected") is not True:
            return "matching_project_selected must be observed"
        if details.get("switch_exited_unrelated_detail") is not True:
            return "switch_exited_unrelated_detail must be observed"
    elif check == "approve_archive_idempotent":
        for flag in ("approve_observed", "archive_observed", "immediate_refresh", "stable_result"):
            if details.get(flag) is not True:
                return f"{flag} must be observed"
        if not _positive_count(details.get("repeat_count")) or int(details["repeat_count"]) < 2:
            return "repeat_count must be at least two"
    elif check == "decision_mark_receipt_bound":
        if not str(details.get("receipt_id") or "").startswith("approval-"):
            return "a Decision Mark receipt_id is required"
        for key in ("receipt_sha256", "subject_id_sha256"):
            if not SHA256_PATTERN.fullmatch(str(details.get(key) or "")):
                return f"{key} must be a SHA-256 digest"
        if details.get("integrity_status") != "verified":
            return "Decision Mark receipt integrity must be verified"
    elif check == "keyboard_focus":
        if not _positive_count(details.get("controls_checked")):
            return "controls_checked must be recorded"
        if details.get("all_reachable") is not True or details.get("focus_visible") is not True:
            return "all controls must be reachable with visible focus"
    elif check == "voiceover_labels":
        if not _positive_count(details.get("controls_checked")):
            return "controls_checked must be recorded"
        if details.get("all_labeled") is not True or details.get("state_not_color_only") is not True:
            return "all controls need labels and non-color state equivalents"
    elif check == "loading_empty_error":
        states = {str(item) for item in details.get("states", [])}
        if not {"loading", "empty", "error"}.issubset(states):
            return "loading, empty, and error states must all be observed"
        if details.get("recovery_action_observed") is not True:
            return "an error recovery action must be observed"
    elif check == "plugin_lifecycle_preserves_data":
        states = {str(item) for item in details.get("states", [])}
        if not {"install", "upgrade", "repair", "uninstall"}.issubset(states):
            return "install, upgrade, repair, and uninstall must all be observed"
        if details.get("data_preserved") is not True or details.get("module_visibility_updated") is not True:
            return "plugin data preservation and module visibility updates must be observed"
    return None


def _validate_ui(
    candidate: Mapping[str, Any],
    *,
    report_root: Path,
    expected_version: str | None,
    verify_installed_candidate: bool,
) -> str | None:
    if candidate.get("schema_version") != UI_SCHEMA:
        return f"schema_version must be {UI_SCHEMA}"
    if error := _validate_candidate(
        candidate,
        expected_version=expected_version,
        verify_installed_candidate=verify_installed_candidate,
    ):
        return error

    observations = candidate.get("observations")
    if not isinstance(observations, list) or not observations:
        return "per-screen UI observations are required"

    screens: set[str] = set()
    locales: set[str] = set()
    appearances: set[str] = set()
    motion_modes: set[bool] = set()
    window_modes: set[str] = set()
    screenshot_paths: set[Path] = set()
    screenshot_hashes: set[str] = set()
    latest_observed_at: datetime | None = None
    resolved_root = report_root.resolve()
    for index, observation in enumerate(observations):
        if not isinstance(observation, Mapping):
            return f"UI observation {index} must be an object"
        if not _is_iso8601(observation.get("observed_at")):
            return f"UI observation {index} needs an ISO-8601 timestamp with timezone"
        observed_at = datetime.fromisoformat(str(observation["observed_at"]).replace("Z", "+00:00"))
        latest_observed_at = max(latest_observed_at or observed_at, observed_at)
        screen = str(observation.get("screen") or "")
        locale = str(observation.get("locale") or "")
        appearance = str(observation.get("appearance") or "")
        reduce_motion = observation.get("reduce_motion")
        window_mode = str(observation.get("window_mode") or "")
        if screen not in REQUIRED_UI_SCREENS:
            return f"UI observation {index} has an unknown screen"
        if locale not in {"zh-Hans", "en"}:
            return f"UI observation {index} has an unsupported locale"
        if appearance not in {"light", "dark"}:
            return f"UI observation {index} has an unsupported appearance"
        if not isinstance(reduce_motion, bool):
            return f"UI observation {index} must record reduce_motion"
        if window_mode not in {"default", "full-size"}:
            return f"UI observation {index} has an unsupported window_mode"
        checks = observation.get("checks")
        if not isinstance(checks, list) or not checks or not all(
            isinstance(item, str) and item.strip() for item in checks
        ):
            return f"UI observation {index} must record observed checks"
        screenshot_value = observation.get("screenshot_path")
        screenshot_hash = str(observation.get("screenshot_sha256") or "")
        if not isinstance(screenshot_value, str) or not screenshot_value:
            return f"UI observation {index} must reference a screenshot"
        screenshot = Path(screenshot_value).expanduser().resolve()
        if not _is_under(screenshot, resolved_root):
            return f"UI observation {index} screenshot must stay under the release report root"
        if screenshot.suffix.lower() != ".png" or not screenshot.is_file():
            return f"UI observation {index} screenshot is missing or is not PNG"
        if not SHA256_PATTERN.fullmatch(screenshot_hash):
            return f"UI observation {index} screenshot_sha256 is invalid"
        if _sha256_file(screenshot) != screenshot_hash:
            return f"UI observation {index} screenshot hash does not match"
        if screenshot in screenshot_paths or screenshot_hash in screenshot_hashes:
            return f"UI observation {index} must use a unique screenshot"
        dimensions = _validated_png_dimensions(screenshot)
        if dimensions is None:
            return f"UI observation {index} screenshot is not a valid PNG image"
        if dimensions[0] < MIN_SCREENSHOT_WIDTH or dimensions[1] < MIN_SCREENSHOT_HEIGHT:
            return f"UI observation {index} screenshot is too small for UI evidence"
        screens.add(screen)
        locales.add(locale)
        appearances.add(appearance)
        motion_modes.add(reduce_motion)
        window_modes.add(window_mode)
        screenshot_paths.add(screenshot)
        screenshot_hashes.add(screenshot_hash)

    if not REQUIRED_UI_SCREENS.issubset(screens):
        return "required packaged screens are missing"
    if locales != {"zh-Hans", "en"}:
        return "both Simplified Chinese and English must be observed"
    if appearances != {"light", "dark"}:
        return "both light and dark appearance must be observed"
    if motion_modes != {False, True}:
        return "both normal and Reduce Motion modes must be observed"
    if window_modes != {"default", "full-size"}:
        return "both default and full-size window modes must be observed"
    interaction_observations = candidate.get("interaction_observations")
    if not isinstance(interaction_observations, list):
        return "structured UI interaction observations are required"
    observed_checks: set[str] = set()
    for index, observation in enumerate(interaction_observations):
        if not isinstance(observation, Mapping):
            return f"UI interaction observation {index} must be an object"
        check = str(observation.get("check") or "")
        if check not in REQUIRED_UI_CHECKS or check in observed_checks:
            return f"UI interaction observation {index} has an unknown or duplicate check"
        if not _is_iso8601(observation.get("observed_at")):
            return f"UI interaction observation {index} needs an ISO-8601 timestamp"
        observed_at = datetime.fromisoformat(str(observation["observed_at"]).replace("Z", "+00:00"))
        latest_observed_at = max(latest_observed_at or observed_at, observed_at)
        summary = observation.get("summary")
        if not isinstance(summary, str) or len(summary.strip()) < 12:
            return f"UI interaction observation {index} needs an observed summary"
        details = observation.get("details")
        if not isinstance(details, Mapping):
            return f"UI interaction observation {index} needs structured details"
        if error := _validate_ui_interaction_details(check, details):
            return f"UI interaction observation {index}: {error}"
        observed_checks.add(check)
    if observed_checks != REQUIRED_UI_CHECKS:
        return "required UI interaction observations are missing"
    completed_at = datetime.fromisoformat(str(candidate["completed_at"]).replace("Z", "+00:00"))
    if latest_observed_at is not None and completed_at < latest_observed_at:
        return "UI completed_at cannot precede an observation"
    return None


def _validate_voice(
    candidate: Mapping[str, Any],
    *,
    expected_version: str | None,
    verify_installed_candidate: bool,
) -> str | None:
    if candidate.get("schema_version") != VOICE_SCHEMA:
        return f"schema_version must be {VOICE_SCHEMA}"
    if error := _validate_candidate(
        candidate,
        expected_version=expected_version,
        verify_installed_candidate=verify_installed_candidate,
    ):
        return error
    if _contains_forbidden_voice_key(candidate):
        return "voice evidence must not contain raw audio or transcript fields"
    sessions = candidate.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        return "real microphone session records are required"
    by_locale: dict[str, list[Mapping[str, Any]]] = {"zh-Hans": [], "en-US": []}
    session_ids: set[str] = set()
    globally_observed_states: set[str] = set()
    latest_completed_at: datetime | None = None
    for index, session in enumerate(sessions):
        if not isinstance(session, Mapping):
            return f"voice session {index} must be an object"
        locale = str(session.get("locale") or "")
        if locale not in by_locale:
            return f"voice session {index} has an unsupported locale"
        session_id = str(session.get("session_id") or "")
        if not session_id or session_id in session_ids:
            return f"voice session {index} needs a unique session_id"
        session_ids.add(session_id)
        if session.get("real_microphone") is not True:
            return f"voice session {index} must use a real microphone"
        if not _is_iso8601(session.get("started_at")) or not _is_iso8601(session.get("completed_at")):
            return f"voice session {index} needs start and completion timestamps"
        started_at = datetime.fromisoformat(str(session["started_at"]).replace("Z", "+00:00"))
        completed_at = datetime.fromisoformat(str(session["completed_at"]).replace("Z", "+00:00"))
        if completed_at <= started_at:
            return f"voice session {index} must complete after it starts"
        latest_completed_at = max(latest_completed_at or completed_at, completed_at)
        events = session.get("events")
        if not isinstance(events, list) or not events:
            return f"voice session {index} needs timestamped state events"
        first_event_index: dict[str, int] = {}
        previous_event_at: datetime | None = None
        for event_index, event in enumerate(events):
            if not isinstance(event, Mapping):
                return f"voice session {index} event {event_index} must be an object"
            state = str(event.get("state") or "")
            if state not in REQUIRED_VOICE_SESSION_STATES | REQUIRED_VOICE_GLOBAL_STATES:
                return f"voice session {index} event {event_index} has an unknown state"
            if not _is_iso8601(event.get("observed_at")):
                return f"voice session {index} event {event_index} needs a timestamp"
            observed_at = datetime.fromisoformat(str(event["observed_at"]).replace("Z", "+00:00"))
            if observed_at < started_at or observed_at > completed_at:
                return f"voice session {index} event {event_index} falls outside the session"
            if previous_event_at is not None and observed_at <= previous_event_at:
                return f"voice session {index} events must be in strict timestamp order"
            previous_event_at = observed_at
            first_event_index.setdefault(state, event_index)
            globally_observed_states.add(state)
        states = set(first_event_index)
        if not REQUIRED_VOICE_SESSION_STATES.issubset(states):
            return f"voice session {index} is missing required locale states"
        if [first_event_index[state] for state in VOICE_CORE_SEQUENCE] != sorted(
            first_event_index[state] for state in VOICE_CORE_SEQUENCE
        ):
            return f"voice session {index} core states are out of order"
        for flag in (
            "editable_draft_observed",
            "explicit_submit_observed",
            "cancel_without_submit_observed",
            "tts_stopped_before_listening",
            "pause_did_not_publish_draft",
            "full_recording_transcribed_once",
        ):
            if session.get(flag) is not True:
                return f"voice session {index} must prove {flag}"
        privacy = session.get("privacy")
        if not isinstance(privacy, Mapping) or any(
            privacy.get(key) is not False
            for key in ("raw_audio_persisted", "full_transcript_persisted", "public_evidence_contains_transcript")
        ):
            return f"voice session {index} must prove the privacy checks"
        by_locale[locale].append(session)
    if not all(by_locale.values()):
        return "both zh-Hans and en-US real microphone sessions are required"
    if not REQUIRED_VOICE_GLOBAL_STATES.issubset(globally_observed_states):
        return "permission, denied, and unavailable recovery states must be observed"
    evidence_completed_at = datetime.fromisoformat(str(candidate["completed_at"]).replace("Z", "+00:00"))
    if latest_completed_at is not None and evidence_completed_at < latest_completed_at:
        return "voice completed_at cannot precede a microphone session"
    return None


def _validate_beginner_result(
    participant: Mapping[str, Any],
    *,
    report_root: Path,
) -> tuple[str | None, str | None, str | None]:
    path_value = participant.get("verified_result_path")
    if not isinstance(path_value, str) or not path_value:
        return "needs a verified no-key result path", None, None
    result_path = Path(path_value).expanduser().resolve()
    if not _is_under(result_path, report_root.resolve()):
        return "verified result must stay under the release report root", None, None
    if result_path.suffix.lower() != ".json" or not result_path.is_file():
        return "verified result JSON is missing", None, None
    try:
        if result_path.stat().st_size > 2 * 1024 * 1024:
            return "verified result JSON is unexpectedly large", None, None
        raw = result_path.read_bytes()
        result = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return "verified result JSON is invalid", None, None
    if not isinstance(result, Mapping) or _contains_forbidden_beginner_key(result):
        return "verified result is invalid or contains private input", None, None
    required_result_fields = {
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
    if set(result) != required_result_fields:
        return "verified result is not the privacy-bounded compact envelope", None, None

    file_sha256 = str(participant.get("verified_result_file_sha256") or "")
    if not SHA256_PATTERN.fullmatch(file_sha256) or hashlib.sha256(raw).hexdigest() != file_sha256:
        return "verified result file hash does not match", None, None
    if result.get("schema_version") != "across-no-key-demo-result/1.0":
        return "verified result schema is unsupported", None, None
    run_id = str(result.get("run_id") or "")
    if (
        not BEGINNER_RUN_ID_PATTERN.fullmatch(run_id)
        or run_id != str(participant.get("verified_result_id") or "")
    ):
        return "verified result id is missing or does not match", None, None
    if result.get("status") != "completed" or result.get("verdict") != "verified":
        return "verified result must be completed with a verified verdict", None, None
    if (
        result.get("pattern_id") != "first-verified-task"
        or result.get("mission_id") != "first_verified_task"
    ):
        return "verified result is not the fixed first verified task", None, None
    if result.get("evidence_route") != f"run://{run_id}/evidence":
        return "verified result evidence route is not bound to its run", None, None
    if result.get("next_action_id") != "inspect_evidence":
        return "verified result must derive the inspect_evidence final action", None, None
    if not isinstance(result.get("next_action"), str) or not result["next_action"].strip():
        return "verified result must explain its final action", None, None
    if participant.get("actual_final_action") != result.get("next_action_id"):
        return "participant did not choose the result-derived final action", None, None

    goal_sha256 = str(result.get("goal_sha256") or "")
    if not SHA256_PATTERN.fullmatch(goal_sha256) or goal_sha256 != participant.get("goal_sha256"):
        return "verified result is not bound to the entered goal", None, None
    evidence_sha256 = str(result.get("evidence_sha256") or "")
    if (
        not SHA256_PATTERN.fullmatch(evidence_sha256)
        or evidence_sha256 != participant.get("verified_evidence_sha256")
    ):
        return "verified evidence hash is missing or does not match", None, None

    policy = result.get("policy")
    if not isinstance(policy, Mapping) or any(
        (
            policy.get("provider_key_used") is not False,
            policy.get("network_used") is not False,
            policy.get("model_calls") != 0,
            policy.get("external_side_effects_performed") is not False,
        )
    ):
        return "verified result did not preserve the no-key read-only policy", None, None
    gates = result.get("gates")
    gate_ids: set[str] = set()
    if not isinstance(gates, list) or not gates:
        return "verified result contains invalid gate evidence", None, None
    for gate in gates:
        if (
            not isinstance(gate, Mapping)
            or set(gate) != {"id", "status", "required"}
            or not isinstance(gate.get("id"), str)
            or not gate.get("id")
            or gate.get("id") in gate_ids
            or gate.get("status") not in {"passed", "failed", "blocked", "skipped"}
            or not isinstance(gate.get("required"), bool)
        ):
            return "verified result contains invalid gate evidence", None, None
        gate_ids.add(str(gate["id"]))
        if gate.get("required") is True and gate.get("status") != "passed":
            return "verified result contains a failed required gate", None, None
    result_sha256 = str(result.get("result_sha256") or "")
    unsigned_result = dict(result)
    unsigned_result.pop("result_sha256", None)
    if (
        not SHA256_PATTERN.fullmatch(result_sha256)
        or _sha256_json(unsigned_result) != result_sha256
        or result_sha256 != participant.get("verified_result_sha256")
    ):
        return "verified result hash does not match its payload", None, None
    return None, run_id, result_sha256


def _validate_beginner(
    candidate: Mapping[str, Any],
    *,
    report_root: Path,
    expected_version: str | None,
    verify_installed_candidate: bool,
) -> str | None:
    if candidate.get("schema_version") != BEGINNER_SCHEMA:
        return f"schema_version must be {BEGINNER_SCHEMA}"
    if error := _validate_candidate(
        candidate,
        expected_version=expected_version,
        verify_installed_candidate=verify_installed_candidate,
    ):
        return error
    if _contains_forbidden_beginner_key(candidate):
        return "beginner evidence must not contain identity, path, audio, or transcript fields"
    participants = candidate.get("participants")
    if not isinstance(participants, list) or len(participants) < 5:
        return "at least five human participant records are required"
    participant_ids: set[str] = set()
    profile_ids: set[str] = set()
    result_ids: set[str] = set()
    result_hashes: set[str] = set()
    confusion_counts: Counter[str] = Counter()
    independent_successes: list[float] = []
    latest_completed_at: datetime | None = None
    for index, participant in enumerate(participants):
        if not isinstance(participant, Mapping):
            return f"participant {index} must be an object"
        participant_id = str(participant.get("participant_id") or "")
        profile_id = str(participant.get("fresh_profile_id") or "")
        if not participant_id or participant_id in participant_ids:
            return f"participant {index} needs a unique anonymous participant_id"
        if not profile_id or profile_id in profile_ids or "/" in profile_id:
            return f"participant {index} needs a unique non-path fresh_profile_id"
        participant_ids.add(participant_id)
        profile_ids.add(profile_id)
        if participant.get("self_reported_beginner") is not True:
            return f"participant {index} must be a beginner or early-stage AI user"
        if participant.get("not_involved_in_build") is not True:
            return f"participant {index} must not have been involved in this release"
        if participant.get("anonymous_consent_observed") is not True:
            return f"participant {index} needs anonymous study consent"
        if participant.get("observed_by_facilitator") is not True:
            return f"participant {index} needs a real facilitator observation"
        if participant.get("goal_input_method") not in {"voice", "keyboard"}:
            return f"participant {index} must record a voice or keyboard goal input"
        if not SHA256_PATTERN.fullmatch(str(participant.get("goal_sha256") or "")):
            return f"participant {index} needs a privacy-safe goal hash"
        preflight = participant.get("fresh_profile_preflight")
        if not isinstance(preflight, Mapping) or any(
            (
                preflight.get("plugins_before") != 0,
                preflight.get("tasks_before") != 0,
                preflight.get("learning_events_before") != 0,
                preflight.get("isolated_preferences") is not True,
            )
        ):
            return f"participant {index} did not start from a verified fresh profile"
        for flag in ("success", "external_docs", "operator_help"):
            if not isinstance(participant.get(flag), bool):
                return f"participant {index} must record {flag} as a boolean"
        started_at = participant.get("started_at")
        completed_at = participant.get("completed_at")
        if not _is_iso8601(started_at) or not _is_iso8601(completed_at):
            return f"participant {index} needs independent start and completion timestamps"
        start = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))
        seconds = participant.get("seconds")
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or seconds <= 0:
            return f"participant {index} has an invalid duration"
        if end <= start:
            return f"participant {index} must finish after the study starts"
        latest_completed_at = max(latest_completed_at or end, end)
        if abs((end - start).total_seconds() - float(seconds)) > 5:
            return f"participant {index} duration does not match its timestamps"
        independent = (
            participant.get("success") is True
            and participant.get("external_docs") is False
            and participant.get("operator_help") is False
        )
        completed_steps = {str(item) for item in participant.get("completed_steps", [])}
        if not completed_steps.issubset(BEGINNER_REQUIRED_STEPS):
            return f"participant {index} has an unknown study step"
        confusion_codes = [str(item) for item in participant.get("confusion_codes", [])]
        if len(confusion_codes) != len(set(confusion_codes)) or not set(confusion_codes).issubset(
            BEGINNER_CONFUSION_CODES
        ):
            return f"participant {index} has invalid confusion codes"
        confusion_counts.update(confusion_codes)
        if independent:
            if completed_steps != BEGINNER_REQUIRED_STEPS:
                return f"participant {index} did not complete every fixed study step"
            if participant.get("capability_install_observed") is not True:
                return f"participant {index} did not install the capability in-product"
            result_error, result_id, result_hash = _validate_beginner_result(
                participant,
                report_root=report_root,
            )
            if result_error:
                return f"participant {index} {result_error}"
            if result_id in result_ids or result_hash in result_hashes:
                return f"participant {index} must use a unique verified run and result"
            result_ids.add(str(result_id))
            result_hashes.add(str(result_hash))
            independent_successes.append(float(seconds))
        else:
            failure_reason = str(participant.get("failure_reason") or "")
            if failure_reason not in BEGINNER_FAILURE_REASONS:
                return f"participant {index} needs a bounded failure reason"
    if len(independent_successes) < 4:
        return "at least four independent participant successes are required"
    if statistics.median(independent_successes) > 480:
        return "median independent success time exceeds eight minutes"
    repeated_confusion = sorted(code for code, count in confusion_counts.items() if count >= 2)
    if repeated_confusion:
        return "repeated beginner confusion is release-blocking: " + ", ".join(repeated_confusion)
    evidence_completed_at = datetime.fromisoformat(str(candidate["completed_at"]).replace("Z", "+00:00"))
    if latest_completed_at is not None and evidence_completed_at < latest_completed_at:
        return "beginner study completed_at cannot precede a participant session"
    return None


def validate_manual_evidence(
    gate_id: str,
    candidate: Mapping[str, Any],
    *,
    report_root: Path,
    expected_version: str | None = None,
    verify_installed_candidate: bool = False,
) -> tuple[str, str | None]:
    """Return the gate status and a bounded validation error, if any."""

    if not isinstance(candidate, Mapping):
        return "failed", "manual evidence must be a JSON object"
    if error := _validate_base(candidate):
        return "failed", error
    validators = {
        "packaged_ui_sweep": lambda: _validate_ui(
            candidate,
            report_root=report_root,
            expected_version=expected_version,
            verify_installed_candidate=verify_installed_candidate,
        ),
        "voice_hardware_smoke": lambda: _validate_voice(
            candidate,
            expected_version=expected_version,
            verify_installed_candidate=verify_installed_candidate,
        ),
        "beginner_human_study": lambda: _validate_beginner(
            candidate,
            report_root=report_root,
            expected_version=expected_version,
            verify_installed_candidate=verify_installed_candidate,
        ),
    }
    validator = validators.get(gate_id)
    if validator is None:
        return "failed", f"unknown manual gate: {gate_id}"
    if error := validator():
        return "failed", error
    return "passed", None


def validate_release_decision(
    candidate: Mapping[str, Any],
    *,
    expected_version: str | None = None,
    verify_installed_candidate: bool = False,
) -> tuple[str, str | None]:
    """Validate an explicit product-owner release decision and bounded waiver.

    A waiver records accepted residual coverage; it never converts an untested
    microphone path into a claimed hardware-test pass.
    """

    if not isinstance(candidate, Mapping):
        return "failed", "release decision must be a JSON object"
    if candidate.get("schema_version") != RELEASE_DECISION_SCHEMA:
        return "failed", f"schema_version must be {RELEASE_DECISION_SCHEMA}"
    if candidate.get("decision") != "authorized":
        return "failed", "release decision must be authorized"
    if not _is_iso8601(candidate.get("authorized_at")):
        return "failed", "authorized_at must be an ISO-8601 timestamp"
    summary = candidate.get("summary")
    if not isinstance(summary, str) or len(summary.strip()) < 20:
        return "failed", "release decision summary is required"
    if error := _validate_candidate(
        candidate,
        expected_version=expected_version,
        verify_installed_candidate=verify_installed_candidate,
    ):
        return "failed", error

    voice = candidate.get("voice_hardware_gate")
    if not isinstance(voice, Mapping):
        return "failed", "voice_hardware_gate decision is required"
    required = {
        "status": "waived",
        "scope": "remaining-real-microphone-edge-paths",
        "reason_code": "product-owner-accepted-residual-hardware-risk",
        "core_chinese_observed": True,
        "core_english_observed": True,
        "remaining_edges_not_tested": True,
        "no_full_coverage_claim": True,
    }
    for key, expected in required.items():
        if voice.get(key) != expected:
            return "failed", f"voice_hardware_gate {key} must be {expected!r}"
    if _contains_forbidden_voice_key(voice):
        return "failed", "release decision must not contain audio or transcript data"
    return "passed", None
