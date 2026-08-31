from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from copy import deepcopy

import pytest

import across_agents_assistant.plugin_runtime as plugin_runtime


ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "fixtures/goal-contract/cross-process-contracts.json"


def test_goal_contract_cross_process_catalog_is_release_complete():
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    assert catalog["schema_version"] == "across-goal-cross-process-catalog/1.0"
    rows = {row["contract_id"]: row for row in catalog["contracts"]}
    assert set(rows) == {
        "goal-contract",
        "goal-revalidation-plan",
        "goal-revalidation-start",
        "goal-revalidation-complete",
    }
    assert all(row["required_bindings"] for row in rows.values())
    assert all(row["mutation_policy"] == "each_required_binding" for row in rows.values())
    assert rows["goal-revalidation-plan"]["durable_write"] is False
    assert rows["goal-revalidation-start"]["durable_write"] is True
    assert rows["goal-revalidation-complete"]["durable_write"] is True


def test_provider_consumer_runner_uses_the_standard_backend_environment_with_dev_fallback():
    runner = (ROOT / "scripts/run_goal_contract_provider_consumer_e2e.sh").read_text(
        encoding="utf-8"
    )

    assert '"$ROOT_DIR/backend/.venv/bin/python"' in runner
    assert '"$ROOT_DIR/.venv/bin/python"' in runner
    assert "No AAA Python environment is available" in runner


def test_quality_workflow_provisions_the_pinned_real_orchestrator_provider():
    workflow = (ROOT / ".github/workflows/quality.yml").read_text(encoding="utf-8")

    assert "repository: fantasyce/across-orchestrator" in workflow
    assert "ref: v0.12.2" in workflow
    assert "ACROSS_ORCHESTRATOR_PROVIDER_ROOT:" in workflow


@pytest.fixture(scope="module")
def real_orchestrator_runtime(tmp_path_factory):
    root = tmp_path_factory.mktemp("real-orchestrator-provider")
    aaa_root = Path(__file__).resolve().parents[2]
    provider_root = Path(
        os.environ.get(
            "ACROSS_ORCHESTRATOR_PROVIDER_ROOT",
            str(aaa_root.parent / "across-orchestrator"),
        )
    ).resolve()
    assert (provider_root / "pyproject.toml").is_file(), provider_root
    distribution = root / "dist"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(distribution),
            str(provider_root),
        ],
        check=True,
    )
    wheels = list(distribution.glob("across_orchestrator-*.whl"))
    assert len(wheels) == 1, wheels
    environment = root / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
    subprocess.run(
        [str(environment / "bin" / "python"), "-m", "pip", "install", str(wheels[0])],
        check=True,
    )
    across_home = root / "across"
    command = across_home / "bin" / "across-orchestrator"
    command.parent.mkdir(parents=True)
    command.symlink_to(environment / "bin" / "across-orchestrator")
    return {
        "env": {"ACROSS_HOME": str(across_home), "PATH": ""},
        "across_home": across_home,
        "command": command,
    }


def _catalog_rows() -> dict[str, dict]:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return {row["contract_id"]: row for row in catalog["contracts"]}


def _invoke(runtime: dict, row: dict, payload: dict) -> subprocess.CompletedProcess[str]:
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    arguments = [payload_json if item == "{payload_json}" else item for item in row["command"]]
    return subprocess.run(
        [str(runtime["command"]), *arguments],
        env=runtime["env"],
        text=True,
        capture_output=True,
        check=False,
    )


def _require_success(runtime: dict, row: dict, payload: dict) -> dict:
    completed = _invoke(runtime, row, payload)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["schema_version"] == row["output_schema"]
    return result


def _mutate_binding(payload: dict, dotted_path: str) -> dict:
    mutated = deepcopy(payload)
    parts = dotted_path.split(".")
    owner = mutated
    for part in parts[:-1]:
        owner = owner[part]
    current = owner[parts[-1]]
    if isinstance(current, bool):
        owner[parts[-1]] = not current
    elif isinstance(current, int):
        owner[parts[-1]] = 0
    elif isinstance(current, list):
        owner[parts[-1]] = []
    elif isinstance(current, dict):
        owner[parts[-1]] = {}
    else:
        owner[parts[-1]] = ""
    return mutated


def _attempt_files(runtime: dict) -> list[Path]:
    root = (
        runtime["across_home"]
        / "data/across-orchestrator/worker-control/revalidation_attempts"
    )
    return sorted(root.glob("*.json")) if root.is_dir() else []


def _request() -> dict:
    return {
        "schema_version": "across-goal-revalidation-request/1.1",
        "graph": {
            "criteria": {
                "criterion-real": {
                    "input_fingerprints": ["source-real"],
                    "depends_on": [],
                    "evidence_ids": ["evidence-old"],
                }
            }
        },
        "changed_fingerprints": ["source-real"],
        "criterion_ids": ["criterion-real"],
        "prior_attempt_number": 0,
        "goal_id": "goal-real-provider",
        "goal_revision": 2,
        "task_id": "task-real-provider",
        "input_fingerprint": "a" * 64,
    }


def _receipt(attempt: dict) -> dict:
    unsigned = {
        "schema_version": "across-goal-host-validation-evidence/1.1",
        "attempt_id": attempt["attempt_id"],
        "goal_id": attempt["goal_id"],
        "goal_revision": attempt["goal_revision"],
        "task_id": attempt["task_id"],
        "criterion_ids": attempt["criterion_ids"],
        "artifact_digests": {"result.md": "b" * 64},
        "input_fingerprint": attempt["input_fingerprint"],
        "validator_id": "aaa-host-validator",
        "verdict": "verified",
    }
    canonical = json.dumps(unsigned, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return {**unsigned, "receipt_hash": hashlib.sha256(canonical.encode()).hexdigest()}


def test_every_catalog_row_executes_against_the_built_provider(real_orchestrator_runtime):
    rows = _catalog_rows()
    contract = json.loads((ROOT / "fixtures/goal-contract/simple.json").read_text(encoding="utf-8"))
    probe = _require_success(real_orchestrator_runtime, rows["goal-contract"], contract)
    assert probe["goal_id"] == contract["goal_id"]
    assert probe["goal_revision"] == contract["revision"]

    request = _request()
    plan = _require_success(real_orchestrator_runtime, rows["goal-revalidation-plan"], request)
    attempt = _require_success(
        real_orchestrator_runtime,
        rows["goal-revalidation-start"],
        {
            **request,
            "execution_mode": "host_validation",
            "idempotency_key": "catalog-execution-start",
            "plan_hash": plan["plan_hash"],
        },
    )
    completed = _require_success(
        real_orchestrator_runtime,
        rows["goal-revalidation-complete"],
        {"attempt_id": attempt["attempt_id"], "receipt": _receipt(attempt)},
    )
    assert completed["state"] == "completed"


def test_each_required_catalog_binding_fails_stably_without_partial_writes(
    real_orchestrator_runtime,
):
    rows = _catalog_rows()
    contract = json.loads((ROOT / "fixtures/goal-contract/simple.json").read_text(encoding="utf-8"))
    request = _request()
    plan = _require_success(real_orchestrator_runtime, rows["goal-revalidation-plan"], request)

    payloads = {
        "goal-contract": contract,
        "goal-revalidation-plan": request,
        "goal-revalidation-start": {
            **request,
            "execution_mode": "host_validation",
            "idempotency_key": "catalog-mutation-start",
            "plan_hash": plan["plan_hash"],
        },
    }
    for contract_id in ("goal-contract", "goal-revalidation-plan", "goal-revalidation-start"):
        row = rows[contract_id]
        for binding in row["required_bindings"]:
            before = [item.read_bytes() for item in _attempt_files(real_orchestrator_runtime)]
            mutated = _mutate_binding(payloads[contract_id], binding)
            first = _invoke(real_orchestrator_runtime, row, mutated)
            second = _invoke(real_orchestrator_runtime, row, mutated)
            assert first.returncode != 0, (contract_id, binding, first.stdout)
            assert second.returncode == first.returncode
            assert second.stderr == first.stderr
            assert [item.read_bytes() for item in _attempt_files(real_orchestrator_runtime)] == before

    complete_row = rows["goal-revalidation-complete"]
    for index, binding in enumerate(complete_row["required_bindings"]):
        attempt = _require_success(
            real_orchestrator_runtime,
            rows["goal-revalidation-start"],
            {
                **request,
                "execution_mode": "host_validation",
                "idempotency_key": f"catalog-complete-mutation-{index}",
                "plan_hash": plan["plan_hash"],
            },
        )
        stored = next(item for item in _attempt_files(real_orchestrator_runtime) if item.stem == attempt["attempt_id"])
        before = stored.read_bytes()
        valid = {"attempt_id": attempt["attempt_id"], "receipt": _receipt(attempt)}
        mutated = _mutate_binding(valid, binding)
        if binding.startswith("receipt.") and binding != "receipt.receipt_hash":
            unsigned = {key: value for key, value in mutated["receipt"].items() if key != "receipt_hash"}
            canonical = json.dumps(unsigned, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            mutated["receipt"]["receipt_hash"] = hashlib.sha256(canonical.encode()).hexdigest()
        first = _invoke(real_orchestrator_runtime, complete_row, mutated)
        second = _invoke(real_orchestrator_runtime, complete_row, mutated)
        assert first.returncode != 0, (binding, first.stdout)
        assert second.returncode == first.returncode
        assert second.stderr == first.stderr
        assert stored.read_bytes() == before


def test_real_orchestrator_accepts_exact_aaa_host_revalidation_contract(
    monkeypatch, real_orchestrator_runtime
):
    monkeypatch.setattr(plugin_runtime, "_command_integrity_issues", lambda *_args: [])
    request = _request()
    plan = plugin_runtime.run_managed_goal_revalidation_plan(
        request, env=real_orchestrator_runtime["env"]
    )
    attempt = plugin_runtime.run_managed_goal_revalidation_start(
        {
            **request,
            "execution_mode": "host_validation",
            "idempotency_key": "real-provider-start",
            "plan_hash": plan["plan_hash"],
        },
        env=real_orchestrator_runtime["env"],
    )
    completed = plugin_runtime.run_managed_goal_revalidation_complete(
        {"attempt_id": attempt["attempt_id"], "receipt": _receipt(attempt)},
        env=real_orchestrator_runtime["env"],
    )

    assert plan["schema_version"] == "across-goal-revalidation-plan/1.1"
    assert attempt["state"] == "awaiting_host_evidence"
    assert attempt["job_ids"] == []
    assert completed["state"] == "completed"
    stored = (
        real_orchestrator_runtime["across_home"]
        / "data/across-orchestrator/worker-control/revalidation_attempts"
        / f"{attempt['attempt_id']}.json"
    )
    assert json.loads(stored.read_text(encoding="utf-8"))["state"] == "completed"
