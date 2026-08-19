from __future__ import annotations

import copy

import pytest

from across_agents_assistant.mcp_schema_compatibility import (
    MAX_SCHEMA_BYTES,
    MAX_SCHEMA_DEPTH,
    MAX_SCHEMA_NODES,
    MAX_TOOLS,
    validate_mcp_tools,
)


def _tool(name: str = "read_status", schema: object | None = None) -> dict[str, object]:
    return {
        "name": name,
        "description": "Read bounded public status.",
        "inputSchema": schema
        if schema is not None
        else {
            "type": "object",
            "properties": {"taskId": {"type": "string"}},
            "required": ["taskId"],
            "additionalProperties": False,
        },
    }


def _codes(result: dict[str, object]) -> list[str]:
    return [str(item["code"]) for item in result["findings"]]


def test_valid_portable_tool_set_is_compatible_and_deterministic():
    tools = [_tool()]
    before = copy.deepcopy(tools)

    first = validate_mcp_tools(tools)
    second = validate_mcp_tools(tools)

    assert tools == before
    assert first == second
    assert first["schema_version"] == "across-mcp-schema-compatibility/1.0"
    assert first["status"] == "compatible"
    assert first["tool_count"] == 1
    assert len(first["tool_set_digest"]) == 64
    assert first["profiles"] == {
        "mcp_core": {"status": "compatible", "finding_count": 0},
        "claude_desktop_portable": {"status": "compatible", "finding_count": 0},
    }
    assert first["findings"] == []


def test_prior_redacted_schema_node_fails_with_fixed_public_finding():
    result = validate_mcp_tools([
        _tool(
            "register_external_agent_plugin",
            {
                "type": "object",
                "properties": {"manifest": ["provider-private-schema-marker"]},
            },
        )
    ])

    assert result["status"] == "incompatible"
    assert _codes(result) == ["schema_node_invalid"]
    assert result["findings"][0] == {
        "tool_name": "register_external_agent_plugin",
        "profile": "mcp_core",
        "code": "schema_node_invalid",
        "severity": "error",
        "message": "A JSON Schema position must contain an object or boolean schema.",
    }
    assert "provider-private-schema-marker" not in str(result)


@pytest.mark.parametrize(
    ("tools", "code"),
    [
        ("not-a-list", "tool_list_invalid"),
        ([_tool("dup"), _tool("dup")], "tool_name_duplicate"),
        ([{"name": "", "inputSchema": {"type": "object"}}], "tool_name_invalid"),
        ([_tool(schema={"type": "array"})], "schema_root_type_invalid"),
        ([_tool(schema={"type": "object", "properties": []})], "schema_properties_invalid"),
        ([_tool(schema={"type": "object", "properties": {}, "required": "id"})], "schema_required_invalid"),
        ([_tool(schema={"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id", "id"]})], "schema_required_duplicate"),
        ([_tool(schema={"type": "object", "properties": {}, "required": ["id"]})], "schema_required_unknown"),
    ],
)
def test_core_structural_failures_are_bounded(tools: object, code: str):
    result = validate_mcp_tools(tools)

    assert result["status"] == "incompatible"
    assert code in _codes(result)
    assert all(set(item) == {"tool_name", "profile", "code", "severity", "message"} for item in result["findings"])


@pytest.mark.parametrize("keyword", ["anyOf", "oneOf", "allOf", "not", "if", "then", "else", "dependentSchemas", "patternProperties", "unevaluatedProperties"])
def test_modern_composition_is_core_valid_but_portable_profile_rejects(keyword: str):
    if keyword in {"anyOf", "oneOf", "allOf"}:
        value: object = [{"type": "string"}]
    elif keyword in {"not", "if", "then", "else", "unevaluatedProperties"}:
        value = {"type": "string"} if keyword != "unevaluatedProperties" else False
    else:
        value = {"field": {"type": "string"}}
    schema = {
        "type": "object",
        "properties": {"value": {keyword: value}},
    }

    result = validate_mcp_tools([_tool(schema=schema)])

    assert result["profiles"]["mcp_core"] == {"status": "compatible", "finding_count": 0}
    assert result["profiles"]["claude_desktop_portable"]["status"] == "incompatible"
    assert _codes(result) == ["portable_keyword_unsupported"]


def test_boolean_subschema_is_core_valid_but_portable_profile_rejects():
    result = validate_mcp_tools([_tool(schema={"type": "object", "properties": {"value": True}})])

    assert result["profiles"]["mcp_core"]["status"] == "compatible"
    assert _codes(result) == ["portable_boolean_schema_unsupported"]


def test_external_ref_is_rejected_without_fetching_or_echoing_uri():
    result = validate_mcp_tools([
        _tool(schema={"type": "object", "properties": {"value": {"$ref": "https://private.example/schema"}}})
    ])

    assert _codes(result) == ["external_ref_forbidden"]
    assert "private.example" not in str(result)


def test_same_document_ref_is_allowed_by_both_profiles():
    result = validate_mcp_tools([
        _tool(
            schema={
                "type": "object",
                "$defs": {"Identifier": {"type": "string"}},
                "properties": {"id": {"$ref": "#/$defs/Identifier"}},
            }
        )
    ])

    assert result["status"] == "compatible"


def test_tool_count_limit_fails_closed():
    result = validate_mcp_tools([_tool(f"tool_{index}") for index in range(MAX_TOOLS + 1)])

    assert _codes(result) == ["tool_count_exceeded"]
    assert result["tool_count"] == MAX_TOOLS + 1


def test_serialized_size_limit_fails_closed():
    result = validate_mcp_tools([_tool(schema={"type": "object", "description": "x" * MAX_SCHEMA_BYTES})])

    assert _codes(result) == ["schema_size_exceeded"]
    assert "x" * 100 not in str(result)


def test_schema_depth_limit_fails_closed():
    schema: dict[str, object] = {"type": "string"}
    for index in range(MAX_SCHEMA_DEPTH + 2):
        schema = {"type": "object", "properties": {f"level_{index}": schema}}

    result = validate_mcp_tools([_tool(schema=schema)])

    assert "schema_depth_exceeded" in _codes(result)


def test_schema_node_limit_fails_closed():
    properties = {f"field_{index}": {"type": "string"} for index in range(MAX_SCHEMA_NODES + 1)}

    result = validate_mcp_tools([_tool(schema={"type": "object", "properties": properties})])

    assert "schema_node_count_exceeded" in _codes(result)


def test_invalid_input_objects_never_execute_caller_comparisons():
    class PrivateMapping(dict):
        def items(self):
            raise RuntimeError("provider-private-items-marker")

    result = validate_mcp_tools([_tool(schema=PrivateMapping({"type": "object"}))])

    assert _codes(result) == ["schema_node_invalid"]
    assert "provider-private" not in str(result)
