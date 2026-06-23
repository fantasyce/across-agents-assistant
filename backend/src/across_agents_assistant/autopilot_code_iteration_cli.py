from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any


async def _run(payload: dict[str, Any]) -> dict[str, Any]:
    from fastapi import HTTPException

    from .api_server import AutopilotCodeIterationRequest, create_autopilot_code_iteration

    try:
        result = await create_autopilot_code_iteration(AutopilotCodeIterationRequest(**payload))
        if not isinstance(result, dict):
            return {"schema_version": "across-host-code-iteration/1.0", "status": "failed", "error": "unexpected_result"}
        return result
    except HTTPException as exc:
        return {
            "schema_version": "across-host-code-iteration/1.0",
            "status": "failed",
            "error": str(exc.detail),
            "status_code": exc.status_code,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="across-agents-assistant autopilot-code-iteration")
    parser.add_argument("--request-json", help="Inline code iteration request JSON. Defaults to stdin.")
    args = parser.parse_args(argv)

    raw = args.request_json if args.request_json is not None else sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({
            "schema_version": "across-host-code-iteration/1.0",
            "status": "failed",
            "error": f"Invalid request JSON: {exc}",
        }), file=sys.stdout)
        return 2

    result = asyncio.run(_run(payload))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
