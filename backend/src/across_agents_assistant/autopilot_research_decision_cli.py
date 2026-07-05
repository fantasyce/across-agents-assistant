from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import sys
from typing import Any


def _research_cli_log(event: str, **fields: Any) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": event,
        **fields,
    }
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    print(line, file=sys.stderr, flush=True)
    try:
        from .paths import log_dir

        path = log_dir() / "autopilot-research-decision.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


async def _run(payload: dict[str, Any]) -> dict[str, Any]:
    from fastapi import HTTPException

    from .api_server import AutopilotResearchDecisionRequest, create_autopilot_research_decision

    model_policy = payload.get("model_policy") if isinstance(payload.get("model_policy"), dict) else {}
    _research_cli_log(
        "research_decision.start",
        run_id=payload.get("run_id"),
        candidate_id=payload.get("candidate_id"),
        source_count=len(payload.get("sources") or []),
        target_catalog_count=len(payload.get("target_catalog") or []),
        generated_targets_allowed=bool((payload.get("target_generation") or {}).get("allow_model_generated_targets")),
        provider=model_policy.get("provider") or model_policy.get("provider_id"),
        model=model_policy.get("model") or model_policy.get("model_id"),
        agent_id=model_policy.get("agent_id") or model_policy.get("agent"),
    )
    try:
        result = await create_autopilot_research_decision(AutopilotResearchDecisionRequest(**payload))
        if not isinstance(result, dict):
            _research_cli_log("research_decision.failed", error="unexpected_result")
            return {"schema_version": "across-host-research-decision/1.0", "status": "failed", "error": "unexpected_result"}
        _research_cli_log(
            "research_decision.complete",
            run_id=payload.get("run_id"),
            status=result.get("status"),
            selected_target_id=result.get("selected_target_id"),
            model_backed=result.get("model_backed"),
            fallback_reason=result.get("fallback_reason"),
        )
        return result
    except HTTPException as exc:
        _research_cli_log(
            "research_decision.failed",
            run_id=payload.get("run_id"),
            status_code=exc.status_code,
            error=str(exc.detail)[:1000],
        )
        return {
            "schema_version": "across-host-research-decision/1.0",
            "status": "failed",
            "error": str(exc.detail),
            "status_code": exc.status_code,
        }
    except Exception as exc:
        _research_cli_log(
            "research_decision.failed",
            run_id=payload.get("run_id"),
            exception_type=type(exc).__name__,
            error=str(exc)[:1000],
        )
        return {
            "schema_version": "across-host-research-decision/1.0",
            "status": "failed",
            "error": f"Unhandled research decision error: {type(exc).__name__}",
            "status_code": 500,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="across-agents-assistant autopilot-research-decision")
    parser.add_argument("--request-json", help="Inline research decision request JSON. Defaults to stdin.")
    args = parser.parse_args(argv)

    raw = args.request_json if args.request_json is not None else sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        _research_cli_log("research_decision.failed", error=f"Invalid request JSON: {exc}")
        print(json.dumps({
            "schema_version": "across-host-research-decision/1.0",
            "status": "failed",
            "error": f"Invalid request JSON: {exc}",
        }), file=sys.stdout)
        return 2

    result = asyncio.run(_run(payload))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
