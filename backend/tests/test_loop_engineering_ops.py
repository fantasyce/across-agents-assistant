from across_agents_assistant.loop_engineering_ops import build_loop_engineering_ops_dashboard


def test_ops_dashboard_latest_success_clears_historical_failure_attention():
    payload = build_loop_engineering_ops_dashboard(
        telemetry={
            "run_count": 2,
            "by_status": {"completed": 1, "failed": 1},
            "gate_failures": {"manifest_readable": 1},
        },
        runs={
            "runs": [
                {"run_id": "run-new", "spec_id": "repo-quality-copilot", "status": "completed"},
                {"run_id": "run-old", "spec_id": "repo-quality-copilot", "status": "failed"},
            ]
        },
        trigger_registry={
            "triggers": [
                {
                    "trigger_id": "daily",
                    "spec": "repo-quality-copilot",
                    "enabled": True,
                    "paused": False,
                }
            ]
        },
        trigger_scheduler={"running": True},
        capability_pack={"ready_count": 42},
        registry_health={"status": "passed"},
        self_iteration_plan={"status": "active", "ready": True},
    )

    assert payload["status"] == "passed"
    assert payload["summary"]["failed"] == 0
    assert payload["summary"]["historical_failed"] == 1
    assert payload["signals"]["gate_failure_count"] == 0
    assert payload["signals"]["historical_gate_failure_count"] == 1
    assert payload["next_actions"][0]["action"] == "continue_scheduled_e2e"


def test_ops_dashboard_latest_failed_run_still_requires_attention():
    payload = build_loop_engineering_ops_dashboard(
        telemetry={
            "run_count": 2,
            "by_status": {"completed": 1, "failed": 1},
            "gate_failures": {"manifest_readable": 1},
        },
        runs={
            "runs": [
                {"run_id": "run-new", "spec_id": "repo-quality-copilot", "status": "failed"},
                {"run_id": "run-old", "spec_id": "repo-quality-copilot", "status": "completed"},
            ]
        },
        trigger_registry={"triggers": []},
        trigger_scheduler={"running": False},
        capability_pack={"ready_count": 42},
        registry_health={"status": "passed"},
        self_iteration_plan={"status": "active", "ready": True},
    )

    assert payload["status"] == "attention"
    assert payload["summary"]["failed"] == 1
    assert payload["signals"]["gate_failure_count"] == 1
    assert any(action["action"] == "triage_failed_runs" for action in payload["next_actions"])
