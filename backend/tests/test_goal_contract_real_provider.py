from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

import across_agents_assistant.plugin_runtime as plugin_runtime


@pytest.fixture(scope="module")
def real_orchestrator_runtime(tmp_path_factory):
    root = tmp_path_factory.mktemp("real-orchestrator-provider")
    aaa_root = Path(__file__).resolve().parents[2]
    provider_root = Path(
        os.environ.get(
            "ACROSS_ORCHESTRATOR_PROVIDER_ROOT",
            str(aaa_root.parents[1] / "goal-contract-v2" / "across-orchestrator"),
        )
    ).resolve()
    assert (provider_root / "pyproject.toml").is_file(), provider_root
    uv = shutil.which("uv")
    assert uv, "uv is required to build the real provider contract fixture"
    environment = root / "venv"
    subprocess.run([uv, "venv", str(environment), "--python", "3.11"], check=True)
    subprocess.run(
        [uv, "pip", "install", "--python", str(environment / "bin" / "python"), str(provider_root)],
        check=True,
    )
    across_home = root / "across"
    command = across_home / "bin" / "across-orchestrator"
    command.parent.mkdir(parents=True)
    command.symlink_to(environment / "bin" / "across-orchestrator")
    return {
        "env": {"ACROSS_HOME": str(across_home), "PATH": ""},
        "across_home": across_home,
    }


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
