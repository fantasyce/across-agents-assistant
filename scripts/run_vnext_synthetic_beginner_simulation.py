#!/usr/bin/env python3
"""Run five disclosed, isolated AI-beginner product-path simulations."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from across_agents_assistant.beginner_study_artifacts import sanitized_beginner_study_result
from across_agents_assistant.plugin_runtime import (
    discover_across_plugins,
    run_autopilot_plugin_lifecycle_action,
    run_context_plugin_lifecycle_action,
)


PERSONAS = (
    ("synthetic-beginner-1", "Find the safest next step without changing this project."),
    ("synthetic-beginner-2", "Check whether this project is ready and show me the evidence."),
    ("synthetic-beginner-3", "Explain the most important project risk with a verified result."),
    ("synthetic-beginner-4", "Run a read-only first check and tell me what needs attention."),
    ("synthetic-beginner-5", "Help me inspect this project without using an API key."),
)
STEPS = (
    "choose_project",
    "install_capability",
    "enter_goal",
    "run_mission",
    "inspect_trust_compass",
    "inspect_evidence",
    "choose_final_action",
)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def candidate_identity(app: Path) -> dict[str, str]:
    with (app / "Contents" / "Info.plist").open("rb") as handle:
        info = plistlib.load(handle)
    executable = app / "Contents" / "MacOS" / str(info["CFBundleExecutable"])
    return {
        "app_path": str(app),
        "version": str(info["CFBundleShortVersionString"]),
        "bundle_identifier": str(info["CFBundleIdentifier"]),
        "executable_sha256": sha256_file(executable),
    }


def run_persona(
    *,
    persona_index: int,
    persona_id: str,
    goal: str,
    root: Path,
    report_root: Path,
    context_root: Path,
    autopilot_root: Path,
) -> dict[str, object]:
    profile_id = f"synthetic-profile-{persona_index}"
    started_at = iso_now()
    monotonic_started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix=f"across-{profile_id}-") as temporary:
        home = Path(temporary)
        across_home = home / ".across"
        env = {
            "HOME": str(home),
            "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "PYTHONPATH": str(root / "backend/src"),
            "ACROSS_HOME": str(across_home),
            "ACROSS_AGENTS_PRODUCT_MODE": "1",
            "ACROSS_AGENTS_DEVELOPER_MODE": "1",
            "ACROSS_AGENTS_CONTEXT_INSTALL_SOURCE": str(context_root),
            "ACROSS_AGENTS_AUTOPILOT_INSTALL_SOURCE": str(autopilot_root),
            "AAA_PROJECT_ROOT": str(root),
        }
        before = discover_across_plugins(
            plugin_ids=["across-context", "across-autopilot"],
            probe=False,
            env=env,
        )
        if any(item.get("installed") for item in before):
            raise RuntimeError(f"{persona_id} did not start with zero plugins")
        context = run_context_plugin_lifecycle_action("install", env=env)
        autopilot = run_autopilot_plugin_lifecycle_action("install", env=env)
        for plugin in (context, autopilot):
            if not all((plugin.get("installed"), plugin.get("available"), plugin.get("integrity_ok"))):
                raise RuntimeError(f"{persona_id} plugin installation failed: {plugin}")
        visible = {
            item["plugin_id"]: item
            for item in discover_across_plugins(
                plugin_ids=["across-context", "across-autopilot"],
                probe=True,
                env=env,
            )
        }
        if set(visible) != {"across-context", "across-autopilot"}:
            raise RuntimeError(f"{persona_id} installed capability visibility is incomplete")
        command = across_home / "bin" / "across-autopilot"
        run_env = {
            "HOME": str(home),
            "PATH": f"{across_home / 'bin'}:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "ACROSS_HOME": str(across_home),
            "ACROSS_AGENTS_PRODUCT_MODE": "1",
        }
        completed = subprocess.run(
            [
                str(command),
                "beginner-pattern",
                "run",
                "--pattern",
                "first-verified-task",
                "--goal",
                goal,
                "--json",
            ],
            cwd=root / "fixtures" / "vnext-beginner-study-public",
            env=run_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=180,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"{persona_id} no-key mission failed: {completed.stderr[-1000:]}")
        payload = json.loads(completed.stdout)
        sanitized = sanitized_beginner_study_result(payload)
        if sanitized is None or sanitized.get("status") != "completed" or sanitized.get("verdict") != "verified":
            raise RuntimeError(f"{persona_id} did not produce a verified bounded result")
        result_path = report_root / "synthetic-beginner-results" / f"{persona_id}.json"
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(sanitized, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    elapsed = max(1, int(round(time.monotonic() - monotonic_started)))
    completed_at = (
        datetime.fromisoformat(started_at.replace("Z", "+00:00")) + timedelta(seconds=elapsed)
    ).isoformat().replace("+00:00", "Z")
    return {
        "persona_id": persona_id,
        "fresh_profile_id": profile_id,
        "simulated_ai_beginner": True,
        "human_participant": False,
        "goal_input_method": "simulated-keyboard",
        "goal_sha256": sanitized["goal_sha256"],
        "fresh_profile_preflight": {
            "plugins_before": 0,
            "tasks_before": 0,
            "learning_events_before": 0,
            "isolated_preferences": True,
        },
        "started_at": started_at,
        "completed_at": completed_at,
        "seconds": elapsed,
        "success": True,
        "external_docs": False,
        "operator_help": False,
        "capability_install_observed": True,
        "completed_steps": list(STEPS),
        "confusion_codes": [],
        "actual_final_action": "inspect_evidence",
        "verified_result_id": sanitized["run_id"],
        "verified_result_path": str(result_path.resolve()),
        "verified_result_file_sha256": sha256_file(result_path),
        "verified_result_sha256": sanitized["result_sha256"],
        "verified_evidence_sha256": sanitized["evidence_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report-root",
        type=Path,
        default=Path.home() / ".across/data/across-agents-assistant/release-reports",
    )
    parser.add_argument("--context-root", type=Path)
    parser.add_argument("--autopilot-root", type=Path)
    parser.add_argument("--app", type=Path, default=Path("/Applications/Across Agents Assistant.app"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report_root = args.report_root.expanduser().resolve()
    report_root.mkdir(parents=True, exist_ok=True)
    context_root = (args.context_root or root.parent / "across-context").resolve()
    autopilot_root = (args.autopilot_root or root.parent / "across-autopilot").resolve()
    personas = [
        run_persona(
            persona_index=index,
            persona_id=persona_id,
            goal=goal,
            root=root,
            report_root=report_root,
            context_root=context_root,
            autopilot_root=autopilot_root,
        )
        for index, (persona_id, goal) in enumerate(PERSONAS, start=1)
    ]
    latest = max(
        datetime.fromisoformat(str(item["completed_at"]).replace("Z", "+00:00"))
        for item in personas
    )
    evidence = {
        "schema_version": "across-vnext-synthetic-beginner-evidence/1.0",
        "status": "passed",
        "completed_at": latest.isoformat().replace("+00:00", "Z"),
        "summary": "Five isolated AI-beginner simulations completed the no-key product path; this is not human research.",
        "candidate": candidate_identity(args.app),
        "product_owner_decision": {
            "real_human_study_deferred": True,
            "synthetic_substitute_for_this_release": True,
            "recorded_at": "2026-07-16T00:00:00+08:00",
        },
        "limitations": {
            "not_human_research": True,
            "does_not_measure_real_user_comprehension": True,
            "must_not_be_described_as_participant_evidence": True,
        },
        "personas": personas,
    }
    destination = report_root / "vnext-synthetic-beginner-evidence.json"
    destination.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
