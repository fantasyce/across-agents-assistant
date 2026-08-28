#!/usr/bin/env python3
"""Verify Goal Contract fixtures through each repository's public adapter.

The verifier starts an isolated interpreter for every repository. It does not
import another checkout into the AAA process, so accidental development-tree
coupling cannot make the matrix pass.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any


PYTHON_ADAPTER = """
import json, sys
from {module} import normalize_goal_contract, stable_goal_hash
value = json.load(sys.stdin)
normalized = normalize_goal_contract(value)
json.dump({{"normalized": normalized, "hash": stable_goal_hash(normalized)}}, sys.stdout,
          ensure_ascii=False, sort_keys=True, separators=(",", ":"))
"""

NODE_ADAPTER = """
import fs from 'node:fs';
const adapter = await import(process.argv[1]);
const value = JSON.parse(fs.readFileSync(0, 'utf8'));
const normalized = adapter.{normalize}(value);
process.stdout.write(JSON.stringify({{ normalized, hash: adapter.{stable_hash}(normalized) }}));
"""


def _run(command: list[str], *, cwd: Path, payload: dict[str, Any], env: dict[str, str] | None = None) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"adapter failed in {cwd}: {completed.stderr.strip()}")
    return json.loads(completed.stdout)


def _python_adapter(root: Path, *, module: str, source_dir: str, payload: dict[str, Any]) -> dict[str, Any]:
    interpreter = root / ".venv" / "bin" / "python"
    if not interpreter.is_file():
        raise RuntimeError(f"missing isolated interpreter: {interpreter}")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root / source_dir)
    return _run(
        [str(interpreter), "-c", PYTHON_ADAPTER.format(module=module)],
        cwd=root,
        payload=payload,
        env=env,
    )


def _node_adapter(root: Path, *, module_file: str, normalize: str, stable_hash: str, payload: dict[str, Any]) -> dict[str, Any]:
    module_url = (root / module_file).resolve().as_uri()
    return _run(
        [
            "node",
            "--input-type=module",
            "-e",
            NODE_ADAPTER.format(normalize=normalize, stable_hash=stable_hash),
            module_url,
        ],
        cwd=root,
        payload=payload,
    )


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--aaa-root", type=Path, default=repo_root)
    parser.add_argument("--orchestrator-root", type=Path, default=workspace_root / "across-orchestrator")
    parser.add_argument("--autopilot-root", type=Path, default=workspace_root / "across-autopilot")
    parser.add_argument("--context-root", type=Path, default=workspace_root / "across-context")
    args = parser.parse_args()

    fixture_path = args.aaa_root / "fixtures" / "goal-contract" / "simple.json"
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    results = {
        "aaa": _python_adapter(
            args.aaa_root,
            module="across_agents_assistant.goal_contract.protocol",
            source_dir="backend/src",
            payload=payload,
        ),
        "orchestrator": _python_adapter(
            args.orchestrator_root,
            module="across_orchestrator.goal_contracts",
            source_dir="src",
            payload=payload,
        ),
        "autopilot": _node_adapter(
            args.autopilot_root,
            module_file="src/goal-contract.js",
            normalize="normalizeGoalContract",
            stable_hash="stableGoalHash",
            payload=payload,
        ),
        "context": _node_adapter(
            args.context_root,
            module_file="src/goal-memory.js",
            normalize="normalizeGoalContract",
            stable_hash="stableGoalHash",
            payload=payload,
        ),
    }
    reference = results["aaa"]
    mismatches = {name: result for name, result in results.items() if result != reference}
    if mismatches:
        print(json.dumps({"status": "mismatch", "results": results}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"status": "ok", "implementations": sorted(results), **reference}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
