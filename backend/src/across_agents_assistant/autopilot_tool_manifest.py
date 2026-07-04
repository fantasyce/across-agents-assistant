from __future__ import annotations

from typing import Any, Iterable, Mapping


TOOL_MANIFEST_SCHEMA = "across-aaa-mcp-tool-manifest/1.0"


def build_autopilot_tool_manifest(
    *,
    tool_schemas: Iterable[Mapping[str, Any]],
    capability_pack: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a bounded MCP-style view of AAA's loop-engineering tools."""

    tools = [_normalize_tool_schema(item) for item in tool_schemas]
    resources = [_capability_resource(item) for item in capability_pack.get("ready", []) if isinstance(item, Mapping)]
    prompts = [
        {
            "name": "aaa_autonomous_self_iteration",
            "description": "Research, implement, validate, and stop with human-review promotion evidence.",
            "arguments": [
                {"name": "spec", "required": False, "description": "LoopSpec id, defaults to aaa-autonomous-self-iteration."},
                {"name": "trigger", "required": False, "description": "Manual, cron, or replay trigger metadata."},
            ],
        }
    ]
    return {
        "schema_version": TOOL_MANIFEST_SCHEMA,
        "owner": "across-agents-assistant",
        "surface": "autopilot_loop_engineering",
        "tools": tools,
        "prompts": prompts,
        "resources": resources,
        "summary": {
            "tool_count": len(tools),
            "prompt_count": len(prompts),
            "resource_count": len(resources),
            "capability_ready_count": int(capability_pack.get("ready_count") or len(resources)),
        },
        "policy": {
            "read_only_manifest": True,
            "candidate_only_mutation": True,
            "human_promotion_required": True,
            "raw_secrets_excluded": True,
        },
    }


def _normalize_tool_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    name = str(schema.get("name") or "").strip()
    description = str(schema.get("description") or "").strip()
    input_schema = (
        schema.get("inputSchema")
        or schema.get("input_schema")
        or schema.get("parameters")
        or {"type": "object", "properties": {}}
    )
    annotations = schema.get("annotations") if isinstance(schema.get("annotations"), Mapping) else {}
    return {
        "name": name,
        "description": description,
        "inputSchema": input_schema if isinstance(input_schema, Mapping) else {"type": "object", "properties": {}},
        "annotations": {
            "title": str(annotations.get("title") or _title_from_name(name)),
            "readOnlyHint": bool(annotations.get("readOnlyHint", False)),
            "destructiveHint": bool(annotations.get("destructiveHint", False)),
        },
    }


def _capability_resource(capability: Mapping[str, Any]) -> dict[str, Any]:
    capability_id = str(capability.get("id") or "").strip()
    return {
        "uri": f"across://capabilities/{capability_id}",
        "name": capability_id,
        "description": f"{capability.get('layer', 'Capability')} capability exposed by {capability.get('entrypoint', 'AAA')}.",
        "mimeType": "application/json",
        "metadata": {
            "layer": capability.get("layer"),
            "form": capability.get("form"),
            "entrypoint": capability.get("entrypoint"),
            "reusable_by": list(capability.get("reusable_by") or []),
        },
    }


def _title_from_name(name: str) -> str:
    return " ".join(part.capitalize() for part in name.replace("-", "_").split("_") if part) or "Tool"
