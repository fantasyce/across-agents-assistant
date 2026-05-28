"""Tests for manifest assignment persistence and coverage updates."""

import os
import tempfile

os.environ.setdefault("ACROSS_AGENTS_DB_PATH", os.path.join(tempfile.mkdtemp(), "test.db"))

from across_agents_assistant.task_manager.models import RequirementDeliverable, RequirementManifest
from across_agents_assistant.task_manager.orchestration.coverage import CoverageResult
from across_agents_assistant.task_manager.orchestration.owner_agent import OwnerAgent
from across_agents_assistant.task_manager.state import TaskState


def test_update_manifest_assignments_marks_assigned_without_throwing():
    state = TaskState()
    task = state.create_task("Create main.py and README.md", project_dir="/tmp/project")
    manifest = RequirementManifest.new(task.task_id, project_dir="/tmp/project")
    manifest.deliverables.append(
        RequirementDeliverable(
            requirement_id="req-main",
            artifact_type="api_service_source",
            path_hint="main.py",
        )
    )
    manifest.deliverables.append(
        RequirementDeliverable(
            requirement_id="req-readme",
            artifact_type="documentation",
            path_hint="README.md",
        )
    )
    state.save_requirement_manifest(manifest)

    owner = object.__new__(OwnerAgent)
    owner._state = state

    result = CoverageResult(
        passed=True,
        assigned={"req-main": "st-main", "req-readme": "st-docs"},
        gaps=[],
    )

    owner._update_manifest_assignments(task, result)
    updated = state.get_requirement_manifest(task.task_id)

    by_id = {item["requirement_id"]: item for item in updated["deliverables"]}
    assert by_id["req-main"]["status"] == "assigned"
    assert by_id["req-main"]["assigned_subtask_id"] == "st-main"
    assert by_id["req-main"]["evidence"]["coverage_gate"]["reason"] == "matched_subtask_contract"
    assert by_id["req-readme"]["status"] == "assigned"
    assert by_id["req-readme"]["assigned_subtask_id"] == "st-docs"


def test_unassigned_fallback_for_missing_match():
    state = TaskState()
    task = state.create_task("Create main.py", project_dir="/tmp/project")
    manifest = RequirementManifest.new(task.task_id, project_dir="/tmp/project")
    manifest.deliverables.append(
        RequirementDeliverable(
            requirement_id="req-main",
            artifact_type="api_service_source",
            path_hint="main.py",
            status="unassigned",
        )
    )
    state.save_requirement_manifest(manifest)

    owner = object.__new__(OwnerAgent)
    owner._state = state

    result = CoverageResult(passed=False, assigned={}, gaps=[])
    owner._update_manifest_assignments(task, result)
    updated = state.get_requirement_manifest(task.task_id)

    assert updated["deliverables"][0]["status"] == "unassigned"
