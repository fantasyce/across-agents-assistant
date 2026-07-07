from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from .autopilot_host_cli_progress import host_cli_heartbeat, host_cli_log, host_cli_progress_scope

LOG_FILE = "autopilot-research-decision.jsonl"


async def _run(payload: dict[str, Any]) -> dict[str, Any]:
    from fastapi import HTTPException

    from .api_server import AutopilotResearchDecisionRequest, create_autopilot_research_decision

    model_policy = payload.get("model_policy") if isinstance(payload.get("model_policy"), dict) else {}
    host_cli_log(
        LOG_FILE,
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
        with host_cli_progress_scope(
            LOG_FILE,
            run_id=payload.get("run_id"),
            candidate_id=payload.get("candidate_id"),
            phase="research_decision.model_call",
        ):
            with host_cli_heartbeat(
                LOG_FILE,
                "research_decision.heartbeat",
                run_id=payload.get("run_id"),
                candidate_id=payload.get("candidate_id"),
                phase="research_decision.model_call",
            ):
                result = await create_autopilot_research_decision(AutopilotResearchDecisionRequest(**payload))
        if not isinstance(result, dict):
            host_cli_log(LOG_FILE, "research_decision.failed", error="unexpected_result")
            return {"schema_version": "across-host-research-decision/1.0", "status": "failed", "error": "unexpected_result"}
        host_cli_log(
            LOG_FILE,
            "research_decision.complete",
            run_id=payload.get("run_id"),
            status=result.get("status"),
            selected_target_id=result.get("selected_target_id"),
            model_backed=result.get("model_backed"),
            fallback_reason=result.get("fallback_reason"),
        )
        return result
    except HTTPException as exc:
        host_cli_log(
            LOG_FILE,
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
        host_cli_log(
            LOG_FILE,
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
        host_cli_log(LOG_FILE, "research_decision.failed", error=f"Invalid request JSON: {exc}")
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
