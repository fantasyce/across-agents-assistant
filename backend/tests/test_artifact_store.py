import os
import tempfile
import time

import pytest

from across_agents_assistant.task_history.models import Artifact
from across_agents_assistant.task_review.artifact_store import ArtifactStore


class TestArtifactStore:
    def test_store_returns_artifact_id(self):
        store = ArtifactStore()
        artifact = Artifact(
            artifact_id="",
            artifact_type="code",
            produced_by="agent-1",
            task_id="task-1",
            subtask_id="st-1",
            content_ref="ref://code.py",
        )
        aid = store.store(artifact)
        assert aid
        assert aid.startswith("art-")

    def test_store_persists_in_memory(self):
        store = ArtifactStore()
        artifact = Artifact(
            artifact_id="art-001",
            artifact_type="doc",
            produced_by="agent-1",
            task_id="task-1",
            subtask_id="st-1",
            content_ref="ref://doc.md",
        )
        store.store(artifact)
        assert store._artifacts["art-001"] is artifact
        assert "task-1" in store._task_artifacts
        assert "art-001" in store._task_artifacts["task-1"]

    def test_get_latest_returns_latest_by_created_at(self):
        store = ArtifactStore()
        art1 = Artifact(
            artifact_id="art-001",
            artifact_type="code",
            produced_by="agent-1",
            task_id="task-1",
            subtask_id="st-1",
            content_ref="ref://v1.py",
            created_at=time.time() - 10,
        )
        art2 = Artifact(
            artifact_id="art-002",
            artifact_type="code",
            produced_by="agent-1",
            task_id="task-1",
            subtask_id="st-2",
            content_ref="ref://v2.py",
            created_at=time.time(),
        )
        store.store(art1)
        store.store(art2)
        latest = store.get_latest("code", "task-1")
        assert latest is not None
        assert latest.artifact_id == "art-002"

    def test_get_latest_no_match_returns_none(self):
        store = ArtifactStore()
        assert store.get_latest("code", "nonexistent-task") is None

    def test_get_consumers(self):
        store = ArtifactStore()
        artifact = Artifact(
            artifact_id="art-001",
            artifact_type="code",
            produced_by="agent-1",
            task_id="task-1",
            subtask_id="st-1",
            content_ref="ref://code.py",
            consumed_by=["agent-2", "agent-3"],
        )
        store.store(artifact)
        consumers = store.get_consumers("art-001")
        assert consumers == ["agent-2", "agent-3"]

    def test_get_consumers_unknown_artifact(self):
        store = ArtifactStore()
        assert store.get_consumers("nonexistent") == []

    def test_notify_consumers(self):
        store = ArtifactStore()
        artifact = Artifact(
            artifact_id="art-001",
            artifact_type="code",
            produced_by="agent-1",
            task_id="task-1",
            subtask_id="st-1",
            content_ref="ref://code.py",
            consumed_by=["agent-2"],
        )
        store.store(artifact)
        notified = store.notify_consumers("art-001")
        assert notified == ["agent-2"]

    def test_notify_consumers_unknown_artifact(self):
        store = ArtifactStore()
        assert store.notify_consumers("nonexistent") == []

    def test_get_by_task(self):
        store = ArtifactStore()
        art1 = Artifact(
            artifact_id="art-001",
            artifact_type="code",
            produced_by="agent-1",
            task_id="task-1",
            subtask_id="st-1",
            content_ref="ref://code.py",
        )
        art2 = Artifact(
            artifact_id="art-002",
            artifact_type="doc",
            produced_by="agent-2",
            task_id="task-1",
            subtask_id="st-2",
            content_ref="ref://doc.md",
        )
        art3 = Artifact(
            artifact_id="art-003",
            artifact_type="code",
            produced_by="agent-1",
            task_id="task-2",
            subtask_id="st-3",
            content_ref="ref://other.py",
        )
        store.store(art1)
        store.store(art2)
        store.store(art3)
        result = store.get_by_task("task-1")
        assert len(result) == 2
        assert {a.artifact_id for a in result} == {"art-001", "art-002"}

    def test_get_by_task_empty(self):
        store = ArtifactStore()
        assert store.get_by_task("nonexistent-task") == []

    def test_file_based_storage_writes_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(storage_dir=tmpdir)
            artifact = Artifact(
                artifact_id="art-001",
                artifact_type="code",
                produced_by="agent-1",
                task_id="task-1",
                subtask_id="st-1",
                content_ref="ref://code.py",
            )
            store.store(artifact)
            filepath = os.path.join(tmpdir, "art-001.json")
            assert os.path.exists(filepath)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            assert "artifact_id" in content
            assert "art-001" in content
