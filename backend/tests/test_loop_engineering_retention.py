import json
import os
import time
from pathlib import Path

from across_agents_assistant.loop_engineering_retention import (
    RetentionPolicy,
    build_retention_plan,
    run_retention,
)


def _touch(path: Path, age_days: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    ts = time.time() - age_days * 86400
    os.utime(path, (ts, ts))


def test_retention_plan_keeps_latest_and_protects_promotion_ready(tmp_path):
    across_home = tmp_path / "across"
    workspaces = across_home / "data" / "across-autopilot" / "candidate-workspaces"
    runs = across_home / "data" / "across-autopilot" / "runs"
    runtime_root = tmp_path / "runtime-homes"
    _touch(workspaces / "old-a", 30)
    _touch(workspaces / "new-b", 1)
    _touch(runs / "run-old", 30)
    (runs / "run-old" / "evidence.json").write_text(
        json.dumps({"candidate": {"promotion_ready": True}}),
        encoding="utf-8",
    )
    _touch(runtime_root / "old-runtime", 30)
    _touch(runtime_root / "new-runtime", 1)

    plan = build_retention_plan(
        across_home=across_home,
        runtime_home_root=runtime_root,
        policy=RetentionPolicy(max_age_days=14, keep_latest=1),
    )
    actions = {(item["category"], item["name"]): item for item in plan["items"]}

    assert actions[("candidate_workspaces", "old-a")]["action"] == "delete"
    assert actions[("candidate_workspaces", "new-b")]["action"] == "keep"
    assert actions[("runs", "run-old")]["action"] == "keep"
    assert actions[("runs", "run-old")]["reason"] == "promotion_ready_protected"
    assert actions[("candidate_runtime_homes", "old-runtime")]["action"] == "delete"
    assert actions[("candidate_runtime_homes", "new-runtime")]["action"] == "keep"
    assert plan["summary"]["delete_count"] == 2


def test_retention_apply_deletes_only_planned_paths(tmp_path):
    across_home = tmp_path / "across"
    workspaces = across_home / "data" / "across-autopilot" / "candidate-workspaces"
    runtime_root = tmp_path / "runtime-homes"
    _touch(workspaces / "old-a", 30)
    _touch(workspaces / "new-b", 1)

    result = run_retention(
        across_home=across_home,
        runtime_home_root=runtime_root,
        policy=RetentionPolicy(max_age_days=14, keep_latest=1, apply=True),
    )

    assert result["status"] == "applied"
    assert not (workspaces / "old-a").exists()
    assert (workspaces / "new-b").exists()
    assert result["summary"]["deleted_count"] == 1


def test_retention_can_delete_beyond_keep_latest_without_waiting_for_age(tmp_path):
    across_home = tmp_path / "across"
    workspaces = across_home / "data" / "across-autopilot" / "candidate-workspaces"
    apps = across_home / "data" / "across-autopilot" / "candidate-apps"
    runs = across_home / "data" / "across-autopilot" / "runs"
    runtime_root = tmp_path / "runtime-homes"
    _touch(workspaces / "candidate-old", 2)
    _touch(workspaces / "candidate-new", 1)
    _touch(apps / "app-old", 2)
    _touch(apps / "app-new", 1)
    _touch(runs / "run-promotion-ready", 2)
    (runs / "run-promotion-ready" / "evidence.json").write_text(
        json.dumps({"candidate": {"promotion_ready": True}}),
        encoding="utf-8",
    )
    _touch(runs / "run-promotion-ready", 2)
    _touch(runs / "run-new", 1)
    _touch(runtime_root / "runtime-old", 2)
    _touch(runtime_root / "runtime-new", 1)

    result = run_retention(
        across_home=across_home,
        runtime_home_root=runtime_root,
        policy=RetentionPolicy(
            max_age_days=365,
            keep_latest=1,
            delete_beyond_keep_latest=True,
            apply=True,
        ),
    )

    assert result["status"] == "applied"
    assert not (workspaces / "candidate-old").exists()
    assert (workspaces / "candidate-new").exists()
    assert not (apps / "app-old").exists()
    assert (apps / "app-new").exists()
    assert (runs / "run-promotion-ready").exists()
    assert (runs / "run-new").exists()
    assert not (runtime_root / "runtime-old").exists()
    assert (runtime_root / "runtime-new").exists()
    reasons = {(item["category"], item["name"]): item["reason"] for item in result["items"]}
    assert reasons[("candidate_workspaces", "candidate-old")] == "beyond_keep_latest"
    assert reasons[("candidate_apps", "app-old")] == "beyond_keep_latest"
    assert reasons[("runs", "run-promotion-ready")] == "promotion_ready_protected"
    assert reasons[("candidate_runtime_homes", "runtime-old")] == "beyond_keep_latest"


def test_retention_source_mirrors_are_opt_in(tmp_path):
    across_home = tmp_path / "across"
    mirrors = across_home / "data" / "across-autopilot" / "source-mirrors"
    _touch(mirrors / "across-agents-assistant", 30)

    default_plan = build_retention_plan(
        across_home=across_home,
        runtime_home_root=tmp_path / "runtime-homes",
        policy=RetentionPolicy(max_age_days=14, keep_latest=0),
    )
    assert not any(item["category"] == "source_mirrors" for item in default_plan["items"])

    opt_in_plan = build_retention_plan(
        across_home=across_home,
        runtime_home_root=tmp_path / "runtime-homes",
        policy=RetentionPolicy(max_age_days=14, keep_latest=0, include_source_mirrors=True),
    )
    actions = {(item["category"], item["name"]): item for item in opt_in_plan["items"]}

    assert actions[("source_mirrors", "across-agents-assistant")]["action"] == "delete"
    assert opt_in_plan["policy"]["include_source_mirrors"] is True
