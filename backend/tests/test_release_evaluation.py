from across_agents_assistant.task_manager.orchestration.release_evaluation import (
    build_release_evaluation_summary,
)


def _task(
    task_id: str,
    *,
    status: str = "completed",
    gate: str = "passed",
    score: int = 90,
    task_types: list[str] | None = None,
    delivery_mode: str = "functional",
    owner_agent: str = "hermes",
    allowed_subtask_agents: list[str] | None = None,
    remediation_count: int = 0,
    required_failed_count: int = 0,
    manual_required_count: int = 0,
    skipped_required_count: int = 0,
):
    return {
        "task_id": task_id,
        "description": f"Task {task_id}",
        "status": status,
        "task_types": task_types or ["functional"],
        "delivery_mode": delivery_mode,
        "owner_agent": owner_agent,
        "allowed_subtask_agents": ["openclaw", "deepseek"] if allowed_subtask_agents is None else allowed_subtask_agents,
        "last_owner_decision": {
            "delivery_quality": {
                "delivery_quality": gate,
                "quality_report": {
                    "quality_gate": gate,
                    "final_quality_score": score,
                    "generated_quality_score": max(score - 8, 0),
                    "remediation_count": remediation_count,
                    "required_failed_count": required_failed_count,
                    "manual_required_count": manual_required_count,
                    "required_skipped_count": skipped_required_count,
                    "score_breakdown": {
                        "contract_coverage": 20,
                        "runtime_smoke": 15,
                        "user_e2e": 15,
                    },
                },
            }
        },
    }


def test_release_evaluation_reports_no_evidence_without_quality_reports():
    summary = build_release_evaluation_summary([
        {
            "task_id": "task-legacy",
            "description": "Legacy task",
            "status": "completed",
            "task_types": ["functional"],
            "delivery_mode": "legacy",
            "last_owner_decision": {},
        }
    ])

    assert summary["release_readiness"] == "no_evidence"
    assert summary["evaluated_task_count"] == 0
    assert summary["recommendation"] == "Run at least three quality-gated E2E tasks before release."


def test_release_evaluation_marks_ready_when_recent_quality_is_clean():
    summary = build_release_evaluation_summary([
        _task("task-a", score=91, owner_agent="hermes", allowed_subtask_agents=["deepseek"]),
        _task("task-b", score=88, owner_agent="openclaw", allowed_subtask_agents=["claude", "minimax"]),
        _task(
            "task-c",
            score=94,
            task_types=["artifact"],
            delivery_mode="artifact",
            owner_agent="minimax",
            allowed_subtask_agents=[],
        ),
    ])

    assert summary["release_readiness"] == "ready"
    assert summary["evaluated_task_count"] == 3
    assert summary["passed_task_count"] == 3
    assert summary["blocked_task_count"] == 0
    assert summary["pass_rate"] == 1.0
    assert summary["average_final_quality_score"] == 91
    assert summary["agent_coverage"]["hermes"] == 1
    assert summary["agent_coverage"]["deepseek"] == 1
    assert summary["stack_coverage"]["functional"] == 2
    assert summary["stack_coverage"]["artifact"] == 1


def test_release_evaluation_blocks_on_required_gate_failure():
    summary = build_release_evaluation_summary([
        _task("task-good", score=90),
        _task(
            "task-bad",
            gate="failed",
            score=52,
            required_failed_count=1,
            remediation_count=2,
        ),
    ])

    assert summary["release_readiness"] == "blocked"
    assert summary["blocked_task_count"] == 1
    assert summary["total_remediation_count"] == 2
    assert summary["gate_breakdown"]["failed"] == 1
    assert summary["top_risks"][0]["kind"] == "required_gate_failure"
    assert summary["recent_evaluations"][0]["task_id"] == "task-good"


def test_release_evaluation_flags_manual_or_skipped_gates_as_attention():
    summary = build_release_evaluation_summary([
        _task("task-a", score=86, manual_required_count=1),
        _task("task-b", score=82, skipped_required_count=1),
        _task("task-c", score=81),
    ])

    assert summary["release_readiness"] == "attention"
    assert summary["manual_task_count"] == 1
    assert summary["skipped_task_count"] == 1
    assert any(risk["kind"] == "manual_or_skipped_gate" for risk in summary["top_risks"])
