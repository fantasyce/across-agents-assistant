import json
from pathlib import Path
import sys

import pytest

import across_agents_assistant.plugin_runtime as plugin_runtime


def _contract() -> dict:
    fixture = Path(__file__).resolve().parents[2] / "fixtures" / "goal-contract" / "simple.json"
    return json.loads(fixture.read_text(encoding="utf-8"))


def _write_probe_command(root: Path, command: str, response: dict) -> Path:
    path = root / "bin" / command
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "assert sys.argv[1] == 'goal-contract'\n"
        "assert sys.argv[2] == '--contract-json'\n"
        "contract = json.loads(sys.argv[3])\n"
        "assert contract['schema_version'] == 'across-goal-contract/1.0'\n"
        f"print(json.dumps({response!r}))\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _expected(contract: dict) -> dict:
    return {
        "schema_version": "across-goal-contract-probe/1.0",
        "goal_id": contract["goal_id"],
        "goal_revision": contract["revision"],
        "criterion_ids": sorted(item["criterion_id"] for item in contract["acceptance_criteria"]),
        "evidence_hash": plugin_runtime.stable_goal_hash(contract),
    }


def test_goal_contract_probe_uses_only_isolated_installed_commands(monkeypatch, tmp_path):
    across_home = tmp_path / "across"
    contract = _contract()
    expected = _expected(contract)
    installed_paths = {
        _write_probe_command(across_home, command, expected)
        for command in ("across-context", "across-orchestrator", "across-autopilot")
    }
    monkeypatch.setattr(plugin_runtime, "_command_integrity_issues", lambda *_args: [])
    result = plugin_runtime.run_managed_goal_contract_probe(
        contract,
        env={"ACROSS_HOME": str(across_home), "PATH": ""},
    )
    assert result["status"] == "passed"
    assert result["goal_contract"] == expected
    assert set(result["plugins"]) == {"across-context", "across-orchestrator", "across-autopilot"}
    assert all(path.is_relative_to(across_home / "bin") for path in installed_paths)


def test_goal_contract_probe_distinguishes_zero_missing_and_all_plugin_modes(monkeypatch, tmp_path):
    across_home = tmp_path / "across"
    contract = _contract()
    expected = _expected(contract)
    monkeypatch.setattr(plugin_runtime, "_command_integrity_issues", lambda *_args: [])

    zero = plugin_runtime.run_managed_goal_contract_probe(
        contract,
        env={"ACROSS_HOME": str(across_home), "PATH": ""},
        allow_missing=True,
    )
    assert zero["status"] == "degraded"
    assert len(zero["missing_plugins"]) == 3

    _write_probe_command(across_home, "across-context", expected)
    one = plugin_runtime.run_managed_goal_contract_probe(
        contract,
        env={"ACROSS_HOME": str(across_home), "PATH": ""},
        allow_missing=True,
    )
    assert one["status"] == "degraded"
    assert one["missing_plugins"] == ["across-orchestrator", "across-autopilot"]

    for command in ("across-orchestrator", "across-autopilot"):
        _write_probe_command(across_home, command, expected)
    all_plugins = plugin_runtime.run_managed_goal_contract_probe(
        contract,
        env={"ACROSS_HOME": str(across_home), "PATH": ""},
    )
    assert all_plugins["status"] == "passed"


def test_goal_contract_probe_handles_legacy_and_rejects_future_schema(tmp_path):
    legacy = plugin_runtime.run_managed_goal_contract_probe(None, env={"ACROSS_HOME": str(tmp_path), "PATH": ""})
    assert legacy["status"] == "legacy_without_goal"
    future = _contract()
    future["schema_version"] = "across-goal-contract/2.0"
    with pytest.raises(ValueError, match="schema_version"):
        plugin_runtime.run_managed_goal_contract_probe(future, env={"ACROSS_HOME": str(tmp_path), "PATH": ""})


def test_goal_revalidation_uses_isolated_installed_orchestrator(monkeypatch, tmp_path):
    across_home = tmp_path / "across"
    command = across_home / "bin" / "across-orchestrator"
    command.parent.mkdir(parents=True)
    command.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "assert sys.argv[1:3] == ['goal-revalidation', '--payload-json']\n"
        "payload = json.loads(sys.argv[3])\n"
        "print(json.dumps({\n"
        " 'schema_version': 'across-goal-revalidation-attempt/1.0',\n"
        " 'attempt_id': 'revalidation-attempt-installed',\n"
        " 'attempt_number': 1,\n"
        " 'criterion_ids': payload['criterion_ids'],\n"
        " 'changed_fingerprints': payload['changed_fingerprints'],\n"
        " 'supersedes_evidence_ids': ['evidence-old'],\n"
        " 'preserved_evidence_ids': ['evidence-kept'],\n"
        " 'state': 'queued'\n"
        "}))\n",
        encoding="utf-8",
    )
    command.chmod(0o755)
    monkeypatch.setattr(plugin_runtime, "_command_integrity_issues", lambda *_args: [])
    payload = {
        "graph": {"criteria": {}},
        "changed_fingerprints": ["source-a"],
        "criterion_ids": ["criterion-a"],
        "prior_attempt_number": 0,
    }

    result = plugin_runtime.run_managed_goal_revalidation_attempt(
        payload, env={"ACROSS_HOME": str(across_home), "PATH": ""}
    )

    assert result["attempt_id"] == "revalidation-attempt-installed"
    assert result["criterion_ids"] == ["criterion-a"]


def test_direct_goal_revalidation_preserves_unaffected_evidence_without_orchestrator():
    result = plugin_runtime.build_direct_goal_revalidation_attempt({
        "graph": {
            "criteria": {
                "criterion-a": {"evidence_ids": ["evidence-a"]},
                "criterion-b": {"evidence_ids": ["evidence-b"]},
            }
        },
        "changed_fingerprints": ["source-a"],
        "criterion_ids": ["criterion-a"],
        "prior_attempt_number": 2,
    })

    assert result["attempt_id"].startswith("direct-revalidation-attempt-")
    assert result["attempt_number"] == 3
    assert result["supersedes_evidence_ids"] == ["evidence-a"]
    assert result["preserved_evidence_ids"] == ["evidence-b"]
