#!/usr/bin/env python3
"""Validate explicitly synthetic beginner walkthrough evidence.

This gate is deliberately separate from the real-human study schema. It proves
five isolated, no-key product-path simulations and records the product owner's
temporary waiver, but it never claims consent, facilitation, or human usability.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from across_agents_assistant.release_evidence import (
    BEGINNER_CONFUSION_CODES,
    BEGINNER_REQUIRED_STEPS,
    _contains_forbidden_beginner_key,
    _is_iso8601,
    _validate_base,
    _validate_beginner_result,
    _validate_candidate,
)


SYNTHETIC_BEGINNER_SCHEMA = "across-vnext-synthetic-beginner-evidence/1.0"
PERSONA_ID = re.compile(r"^synthetic-beginner-[1-5]$")
REQUIRED_LIMITATIONS = {
    "not_human_research": True,
    "does_not_measure_real_user_comprehension": True,
    "must_not_be_described_as_participant_evidence": True,
}


def validate_synthetic_beginner_evidence(
    candidate: Mapping[str, Any],
    *,
    report_root: Path,
    expected_version: str | None = None,
    verify_installed_candidate: bool = False,
) -> tuple[str, str | None]:
    if not isinstance(candidate, Mapping):
        return "failed", "synthetic beginner evidence must be a JSON object"
    if error := _validate_base(candidate):
        return "failed", error
    if candidate.get("schema_version") != SYNTHETIC_BEGINNER_SCHEMA:
        return "failed", f"schema_version must be {SYNTHETIC_BEGINNER_SCHEMA}"
    if error := _validate_candidate(
        candidate,
        expected_version=expected_version,
        verify_installed_candidate=verify_installed_candidate,
    ):
        return "failed", error
    if _contains_forbidden_beginner_key(candidate):
        return "failed", "synthetic evidence must not contain identity, path, audio, or transcript fields"
    if candidate.get("limitations") != REQUIRED_LIMITATIONS:
        return "failed", "synthetic evidence must preserve all non-human limitations"
    decision = candidate.get("product_owner_decision")
    if not isinstance(decision, Mapping) or any((
        decision.get("real_human_study_deferred") is not True,
        decision.get("synthetic_substitute_for_this_release") is not True,
        not _is_iso8601(decision.get("recorded_at")),
    )):
        return "failed", "an explicit timestamped product-owner deferral is required"

    personas = candidate.get("personas")
    if not isinstance(personas, list) or len(personas) != 5:
        return "failed", "exactly five synthetic beginner personas are required"
    persona_ids: set[str] = set()
    profile_ids: set[str] = set()
    result_ids: set[str] = set()
    result_hashes: set[str] = set()
    durations: list[float] = []
    confusion_counts: Counter[str] = Counter()
    latest_completed_at: datetime | None = None
    for index, persona in enumerate(personas):
        if not isinstance(persona, Mapping):
            return "failed", f"persona {index} must be an object"
        persona_id = str(persona.get("persona_id") or "")
        profile_id = str(persona.get("fresh_profile_id") or "")
        if not PERSONA_ID.fullmatch(persona_id) or persona_id in persona_ids:
            return "failed", f"persona {index} needs a unique bounded persona_id"
        if not profile_id or profile_id in profile_ids or "/" in profile_id:
            return "failed", f"persona {index} needs a unique non-path fresh_profile_id"
        persona_ids.add(persona_id)
        profile_ids.add(profile_id)
        if persona.get("simulated_ai_beginner") is not True:
            return "failed", f"persona {index} must be explicitly synthetic"
        if persona.get("human_participant") is not False:
            return "failed", f"persona {index} must not claim to be human"
        if persona.get("goal_input_method") != "simulated-keyboard":
            return "failed", f"persona {index} must use the bounded simulated input path"
        preflight = persona.get("fresh_profile_preflight")
        if not isinstance(preflight, Mapping) or any((
            preflight.get("plugins_before") != 0,
            preflight.get("tasks_before") != 0,
            preflight.get("learning_events_before") != 0,
            preflight.get("isolated_preferences") is not True,
        )):
            return "failed", f"persona {index} did not start from an isolated fresh profile"
        if persona.get("success") is not True:
            return "failed", f"persona {index} did not complete the synthetic walkthrough"
        if persona.get("external_docs") is not False or persona.get("operator_help") is not False:
            return "failed", f"persona {index} depended on outside guidance"
        if persona.get("capability_install_observed") is not True:
            return "failed", f"persona {index} did not prove in-product capability installation"
        completed_steps = {str(item) for item in persona.get("completed_steps", [])}
        if completed_steps != BEGINNER_REQUIRED_STEPS:
            return "failed", f"persona {index} did not complete every fixed walkthrough step"
        confusion_codes = [str(item) for item in persona.get("confusion_codes", [])]
        if len(confusion_codes) != len(set(confusion_codes)) or not set(confusion_codes).issubset(
            BEGINNER_CONFUSION_CODES
        ):
            return "failed", f"persona {index} has invalid confusion codes"
        confusion_counts.update(confusion_codes)
        if not _is_iso8601(persona.get("started_at")) or not _is_iso8601(persona.get("completed_at")):
            return "failed", f"persona {index} needs independent timestamps"
        started_at = datetime.fromisoformat(str(persona["started_at"]).replace("Z", "+00:00"))
        completed_at = datetime.fromisoformat(str(persona["completed_at"]).replace("Z", "+00:00"))
        seconds = persona.get("seconds")
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or seconds <= 0:
            return "failed", f"persona {index} has an invalid duration"
        if completed_at <= started_at or abs((completed_at - started_at).total_seconds() - float(seconds)) > 5:
            return "failed", f"persona {index} duration does not match its timestamps"
        latest_completed_at = max(latest_completed_at or completed_at, completed_at)
        durations.append(float(seconds))
        result_error, result_id, result_hash = _validate_beginner_result(
            persona,
            report_root=report_root,
        )
        if result_error:
            return "failed", f"persona {index} {result_error}"
        if result_id in result_ids or result_hash in result_hashes:
            return "failed", f"persona {index} must use a unique verified run and result"
        result_ids.add(str(result_id))
        result_hashes.add(str(result_hash))

    if statistics.median(durations) > 480:
        return "failed", "median synthetic walkthrough time exceeds eight minutes"
    repeated_confusion = sorted(code for code, count in confusion_counts.items() if count >= 2)
    if repeated_confusion:
        return "failed", "repeated synthetic beginner confusion is release-blocking: " + ", ".join(repeated_confusion)
    evidence_completed_at = datetime.fromisoformat(str(candidate["completed_at"]).replace("Z", "+00:00"))
    if latest_completed_at is not None and evidence_completed_at < latest_completed_at:
        return "failed", "synthetic evidence completed_at cannot precede a walkthrough"
    return "passed", None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--report-root", type=Path, required=True)
    parser.add_argument("--expected-version")
    parser.add_argument("--verify-installed-candidate", action="store_true")
    args = parser.parse_args()
    payload = json.loads(args.evidence.read_text(encoding="utf-8"))
    status, error = validate_synthetic_beginner_evidence(
        payload,
        report_root=args.report_root,
        expected_version=args.expected_version,
        verify_installed_candidate=args.verify_installed_candidate,
    )
    print(json.dumps({"status": status, "error": error}, sort_keys=True))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
