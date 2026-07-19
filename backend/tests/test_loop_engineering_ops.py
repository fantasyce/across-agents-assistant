from across_agents_assistant.loop_engineering_ops import build_loop_engineering_ops_dashboard


def test_ops_dashboard_treats_unconfigured_automation_as_optional():
    payload = build_loop_engineering_ops_dashboard(
        telemetry={"run_count": 0, "by_status": {}},
        runs={"runs": []},
        trigger_registry={"triggers": []},
        trigger_scheduler={"running": False},
        capability_pack={"ready_count": 42},
        registry_health={"status": "passed"},
        self_iteration_plan={"status": "not_registered", "ready": False},
    )

    assert payload["status"] == "passed"
    assert payload["next_actions"] == []


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
        self_iteration_plan={
            "status": "active",
            "ready": True,
            "platform_self_repair": {
                "enabled": True,
                "spec": "aaa-platform-self-repair",
                "queued_count": 1,
                "promotion_review_required": True,
            },
        },
    )

    assert payload["status"] == "passed"
    assert payload["summary"]["failed"] == 0
    assert payload["summary"]["historical_failed"] == 1
    assert payload["signals"]["gate_failure_count"] == 0
    assert payload["signals"]["historical_gate_failure_count"] == 1
    assert payload["summary"]["platform_self_repair_queued_count"] == 1
    assert payload["self_iteration_plan"]["platform_self_repair"]["spec"] == "aaa-platform-self-repair"
    assert payload["next_actions"] == []


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


def test_ops_dashboard_resolves_obsolete_platform_self_repair_failure():
    payload = build_loop_engineering_ops_dashboard(
        telemetry={
            "run_count": 3,
            "by_status": {"completed": 2, "failed": 1},
            "gate_failures": {"platform_self_repair": 1},
        },
        runs={
            "runs": [
                {
                    "run_id": "run-self-iteration-new",
                    "spec_id": "aaa-autonomous-self-iteration",
                    "status": "completed",
                    "completed_at": "2026-07-01T20:56:55Z",
                },
                {
                    "run_id": "run-platform-old",
                    "spec_id": "aaa-platform-self-repair",
                    "status": "failed",
                    "completed_at": "2026-07-01T17:11:32Z",
                },
            ]
        },
        trigger_registry={
            "triggers": [
                {
                    "trigger_id": "daily",
                    "spec": "aaa-autonomous-self-iteration",
                    "enabled": True,
                    "paused": False,
                }
            ]
        },
        trigger_scheduler={"running": True},
        capability_pack={"ready_count": 42},
        registry_health={"status": "passed"},
        self_iteration_plan={
            "status": "active",
            "ready": True,
            "platform_self_repair": {
                "enabled": True,
                "spec": "aaa-platform-self-repair",
                "queued_count": 0,
                "latest_trigger": {"trigger_id": "trg-old", "status": "obsolete"},
                "promotion_review_required": True,
            },
        },
    )

    assert payload["status"] == "passed"
    assert payload["summary"]["latest_failed"] == 1
    assert payload["summary"]["resolved_failed"] == 1
    assert payload["summary"]["current_failed"] == 0
    assert payload["signals"]["gate_failure_count"] == 0
    assert payload["next_actions"] == []


def test_ops_dashboard_keeps_unresolved_platform_self_repair_failure_attention():
    payload = build_loop_engineering_ops_dashboard(
        telemetry={
            "run_count": 2,
            "by_status": {"completed": 1, "failed": 1},
            "gate_failures": {"platform_self_repair": 1},
        },
        runs={
            "runs": [
                {
                    "run_id": "run-platform-new",
                    "spec_id": "aaa-platform-self-repair",
                    "status": "failed",
                    "completed_at": "2026-07-01T20:56:55Z",
                }
            ]
        },
        trigger_registry={"triggers": []},
        trigger_scheduler={"running": False},
        capability_pack={"ready_count": 42},
        registry_health={"status": "passed"},
        self_iteration_plan={
            "status": "active",
            "ready": True,
            "platform_self_repair": {
                "enabled": True,
                "spec": "aaa-platform-self-repair",
                "queued_count": 1,
                "latest_trigger": {"trigger_id": "trg-new", "status": "pending"},
                "promotion_review_required": True,
            },
        },
    )

    assert payload["status"] == "attention"
    assert payload["summary"]["latest_failed"] == 1
    assert payload["summary"]["resolved_failed"] == 0
    assert payload["summary"]["current_failed"] == 1
    assert any(action["action"] == "triage_failed_runs" for action in payload["next_actions"])
