#!/usr/bin/env python3
"""Deterministic local Agent used by the isolated packaged Goal acceptance.

The formal packaged backend and installed managed plugins remain the system
under test.  This executable supplies only the bounded Agent output needed to
finish one product Task without network credentials.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path, PurePosixPath


def _required_output_path() -> Path:
    raw = os.environ.get("ACROSS_SUBTASK_JSON", "")
    try:
        subtask = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("ACROSS_SUBTASK_JSON must be valid JSON") from exc
    relative = PurePosixPath(str(subtask.get("path") or ""))
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("packaged Goal fixture requires a safe relative output path")
    root = Path.cwd().resolve()
    target = (root / Path(*relative.parts)).resolve()
    if target == root or root not in target.parents:
        raise ValueError("packaged Goal fixture output escaped the isolated project")
    return target


def main() -> int:
    if "--version" in sys.argv:
        print("codex-cli packaged-goal-fixture")
        return 0
    if os.environ.get("ACROSS_PACKAGED_GOAL_FIXTURE_AGENT") != "1":
        print("packaged Goal fixture Agent is disabled", file=sys.stderr)
        return 2
    try:
        target = _required_output_path()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "# Packaged Goal Contract verification\n\n"
        "The installed AAA host and managed Orchestrator completed this bounded task.\n"
        "The result is ready for criterion-scoped evidence and human review.\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "type": "item.completed",
        "item": {
            "type": "agent_message",
            "text": "Created and checked the packaged Goal Contract verification artifact.",
        },
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
