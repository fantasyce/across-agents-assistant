import json

import across_agents_assistant.autopilot_workflow_adapter as adapter


def test_autopilot_workflow_adapter_runs_pack_and_writes_declared_results(monkeypatch, tmp_path):
    report = "across-results/repo-quality-copilot/report.md"
    evidence = "across-results/repo-quality-copilot/evidence.json"
    memory = "across-results/repo-quality-copilot/pending-memory.json"
    task = {
        "task_id": "task-plan-one",
        "goal": "检查代码仓库质量并输出证据",
        "project_root": str(tmp_path),
        "metadata": {
            "host_metadata": {
                "execution_plan": {
                    "deliverables": [report, evidence, memory],
                }
            }
        },
    }
    subtask = {"path": report}
    monkeypatch.setenv("ACROSS_TASK_JSON", json.dumps(task))
    monkeypatch.setenv("ACROSS_SUBTASK_JSON", json.dumps(subtask))
    captured = {}

    class FakeClient:
        def run(self, spec, *, trigger, project_root):
            captured.update(spec=spec, trigger=trigger, project_root=project_root)
            return {
                "run": {"run_id": "run-plan-one", "status": "completed"},
                "evidence": {
                    "status": "completed",
                    "outputs": [{"id": "report"}],
                    "risks": [],
                    "memory": {"pending": [{"summary": "bounded"}]},
                },
            }

    monkeypatch.setattr(adapter, "AutopilotClient", lambda: FakeClient())

    status = adapter.main([
        "--workflow-id",
        "repo-quality-copilot",
        "--loop-spec",
        "repo-quality-copilot",
    ])

    assert status == 0
    assert captured["spec"] == "repo-quality-copilot"
    assert captured["trigger"] == "aaa-task:task-plan-one:workflow:repo-quality-copilot"
    assert captured["project_root"] == tmp_path
    assert "Status: completed" in (tmp_path / report).read_text(encoding="utf-8")
    assert json.loads((tmp_path / evidence).read_text(encoding="utf-8"))["workflow_id"] == "repo-quality-copilot"
    assert json.loads((tmp_path / memory).read_text(encoding="utf-8"))["status"] == "pending_review"


def test_autopilot_workflow_adapter_rejects_a_deliverable_outside_the_project(monkeypatch, tmp_path):
    monkeypatch.setenv("ACROSS_TASK_JSON", json.dumps({
        "task_id": "task-unsafe",
        "goal": "test",
        "project_root": str(tmp_path),
        "metadata": {"execution_plan": {"deliverables": ["../escape.json"]}},
    }))
    monkeypatch.setenv("ACROSS_SUBTASK_JSON", json.dumps({"path": "report.md"}))

    assert adapter.main([
        "--workflow-id",
        "repo-quality-copilot",
        "--loop-spec",
        "repo-quality-copilot",
    ]) == 1
    assert not (tmp_path.parent / "escape.json").exists()
