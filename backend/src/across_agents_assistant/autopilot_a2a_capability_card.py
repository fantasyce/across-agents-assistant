from __future__ import annotations

from typing import Any, Mapping


A2A_CAPABILITY_CARD_SCHEMA = "across-aaa-a2a-capability-card/1.0"


def build_autopilot_a2a_capability_card(*, capability_pack: Mapping[str, Any]) -> dict[str, Any]:
    """Project AAA supervised self-iteration as an A2A-style agent card."""

    capabilities = [
        _capability_summary(item)
        for item in capability_pack.get("ready", [])
        if isinstance(item, Mapping)
        and str(item.get("id") or "") in _CARD_CAPABILITY_IDS
    ]
    return {
        "schema_version": A2A_CAPABILITY_CARD_SCHEMA,
        "agent": {
            "id": "aaa-autonomous-self-iteration",
            "name": "AAA Autonomous Self Iteration",
            "owner": "across-agents-assistant",
            "description": "Supervised engineering loop that researches, patches B candidates, validates, and stops for human promotion review.",
        },
        "protocol_projection": {
            "style": "a2a-agent-card",
            "transport": "aaa-local-api",
            "endpoints": {
                "self_iteration_plan": "/api/autopilot/self-iteration-plan",
                "tool_manifest": "/api/autopilot/tool-manifest",
                "capability_card": "/api/autopilot/a2a/capability-card",
                "promotion_review": "/api/autopilot/runs/{run_id}/promotion-review",
            },
        },
        "skills": [
            {
                "id": "supervised_self_iteration",
                "name": "Supervised self iteration",
                "description": "Select one bounded product improvement, mutate only B, validate, and produce review evidence.",
                "input_modes": ["manual", "cron", "webhook", "replay"],
                "output_modes": ["markdown_report", "json_evidence", "promotion_package"],
                "requires_human_approval": True,
            }
        ],
        "capabilities": capabilities,
        "safety": {
            "candidate_only_mutation": True,
            "source_a_read_only": True,
            "merge_release_signing_blocked": True,
            "raw_secrets_excluded": True,
        },
        "summary": {
            "capability_count": len(capabilities),
            "human_review_required": True,
        },
    }


_CARD_CAPABILITY_IDS = {
    "continuous_self_iteration_plan",
    "trigger_ingestion",
    "candidate_workspace",
    "validation_harness",
    "independent_review",
    "promotion_package",
    "promotion_review_packet",
    "promotion_attestation",
}


def _capability_summary(capability: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(capability.get("id") or ""),
        "layer": capability.get("layer"),
        "form": capability.get("form"),
        "entrypoint": capability.get("entrypoint"),
        "reusable_by": list(capability.get("reusable_by") or []),
    }
