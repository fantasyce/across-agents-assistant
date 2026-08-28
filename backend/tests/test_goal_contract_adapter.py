from across_agents_assistant.goal_contract.protocol import criterion_id


def _delivery_contract() -> dict:
    return {
        "contract_version": "2.0",
        "contract_id": "delivery-contract-1",
        "task_id": "task-legacy-1",
        "delivery_mode": "functional",
        "capabilities": [{"id": "cap-1", "description": "User can inspect results"}],
        "deliverables": [{"id": "del-1", "description": "A packaged result"}],
        "constraints": [{"id": "constraint-1", "description": "Do not release automatically"}],
        "acceptance_probes": [
            {
                "id": "probe-user-visible",
                "probe_type": "installed_user_journey",
                "description": "Installed application exposes the result.",
                "required": True,
                "source": "explicit_user_request",
            },
            {
                "id": "probe-tests",
                "probe_type": "test_suite",
                "command": "pytest",
                "required": True,
                "source": "owner_inferred",
            },
        ],
        "created_at": 1787875200.0,
    }


def test_delivery_contract_adapter_is_deterministic_and_preserves_task_identity():
    from across_agents_assistant.goal_contract.adapter import delivery_contract_to_goal_contract

    first = delivery_contract_to_goal_contract(
        _delivery_contract(), statement="Ship the legacy task", confirmed=False
    )
    second = delivery_contract_to_goal_contract(
        _delivery_contract(), statement="Ship the legacy task", confirmed=False
    )
    assert first == second
    assert first["task_id"] == "task-legacy-1"
    assert first["goal_id"] == "goal-task-legacy-1"
    assert first["revision"] == 1
    assert "confirmed_by" not in first
    assert "confirmed_at" not in first
    assert first["source"] == "migration"


def test_delivery_probe_sources_remain_distinguishable_at_criterion_level():
    from across_agents_assistant.goal_contract.adapter import delivery_contract_to_goal_contract

    goal = delivery_contract_to_goal_contract(
        _delivery_contract(), statement="Ship the legacy task", confirmed=False
    )
    criteria = {item["legacy_probe_id"]: item for item in goal["acceptance_criteria"]}
    assert criteria["probe-user-visible"]["source"] == "user_confirmed"
    assert criteria["probe-tests"]["source"] == "legacy_inferred"
    assert criteria["probe-tests"]["criterion_id"] == criterion_id("probe-tests", "legacy_probe")


def test_acceptance_records_project_to_independent_criterion_verdicts():
    from across_agents_assistant.goal_contract.adapter import project_acceptance_records

    criteria = [
        {"criterion_id": "criterion-a", "legacy_probe_id": "probe-a", "required": True},
        {"criterion_id": "criterion-b", "legacy_probe_id": "probe-b", "required": True},
    ]
    records = [
        {"acceptance_id": "acceptance-1", "probe_id": "probe-a", "decision": "accepted"},
        {"acceptance_id": "acceptance-2", "probe_id": "probe-b", "decision": "rejected"},
    ]
    projected = project_acceptance_records(criteria, records)
    assert projected["criterion-a"]["verdict"] == "verified"
    assert projected["criterion-a"]["acceptance_ids"] == ["acceptance-1"]
    assert projected["criterion-b"]["verdict"] == "failed"


def test_delivery_probe_results_use_the_same_stable_criterion_identity():
    from across_agents_assistant.goal_contract.adapter import project_delivery_probe_results

    projected = project_delivery_probe_results(
        _delivery_contract(),
        [
            {"id": "probe-user-visible", "passed": True, "evidence_id": "evidence-ui"},
            {"id": "probe-tests", "passed": False, "evidence_id": "evidence-tests"},
        ],
    )
    by_probe = {item["legacy_probe_id"]: item for item in projected}
    assert by_probe["probe-user-visible"]["verdict"] == "verified"
    assert by_probe["probe-user-visible"]["evidence_ids"] == ["evidence-ui"]
    assert by_probe["probe-tests"]["verdict"] == "failed"
