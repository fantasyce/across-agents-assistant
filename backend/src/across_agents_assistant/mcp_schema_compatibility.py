from __future__ import annotations

import hashlib
import json
from typing import Any


SCHEMA_VERSION = "across-mcp-schema-compatibility/1.0"
MCP_CORE_PROFILE = "mcp_core"
CLAUDE_DESKTOP_PORTABLE_PROFILE = "claude_desktop_portable"
SUPPORTED_PROFILES = (MCP_CORE_PROFILE, CLAUDE_DESKTOP_PORTABLE_PROFILE)

MAX_TOOLS = 256
MAX_SCHEMA_BYTES = 256 * 1024
MAX_SCHEMA_NODES = 4096
MAX_SCHEMA_DEPTH = 16

_PORTABLE_DENIED_KEYWORDS = frozenset(
    {
        "anyOf",
        "oneOf",
        "allOf",
        "not",
        "if",
        "then",
        "else",
        "dependentSchemas",
        "patternProperties",
        "unevaluatedProperties",
        "unevaluatedItems",
    }
)
_SCHEMA_MAP_KEYWORDS = frozenset(
    {"properties", "patternProperties", "dependentSchemas", "$defs", "definitions"}
)
_SCHEMA_ARRAY_KEYWORDS = frozenset({"anyOf", "oneOf", "allOf", "prefixItems"})
_SCHEMA_SINGLE_KEYWORDS = frozenset(
    {
        "additionalProperties",
        "items",
        "contains",
        "propertyNames",
        "not",
        "if",
        "then",
        "else",
        "unevaluatedProperties",
        "unevaluatedItems",
        "contentSchema",
    }
)

_PUBLIC_MESSAGES = {
    "tool_list_invalid": "The MCP tool list must be an array.",
    "tool_count_exceeded": "The MCP server exposes more tools than the compatibility limit.",
    "tool_descriptor_invalid": "An MCP tool descriptor must be an object.",
    "tool_name_invalid": "An MCP tool name must be a non-empty string.",
    "tool_name_duplicate": "MCP tool names must be unique within one server.",
    "input_schema_missing": "An MCP tool must declare an inputSchema object.",
    "schema_node_invalid": "A JSON Schema position must contain an object or boolean schema.",
    "schema_root_type_invalid": "An MCP inputSchema must declare object as its root type.",
    "schema_properties_invalid": "JSON Schema properties must be an object keyed by property name.",
    "schema_required_invalid": "JSON Schema required must be an array of property names.",
    "schema_required_duplicate": "JSON Schema required property names must be unique.",
    "schema_required_unknown": "Every required property must exist in properties.",
    "schema_type_invalid": "JSON Schema type must be a supported string or string array.",
    "external_ref_forbidden": "External JSON Schema references are not allowed.",
    "portable_keyword_unsupported": "This JSON Schema keyword is not in the Claude Desktop portable profile.",
    "portable_boolean_schema_unsupported": "Boolean property schemas are not in the Claude Desktop portable profile.",
    "schema_depth_exceeded": "The JSON Schema exceeds the compatibility depth limit.",
    "schema_node_count_exceeded": "The JSON Schema exceeds the compatibility node limit.",
    "schema_size_exceeded": "The MCP tool schemas exceed the compatibility size limit.",
    "profile_invalid": "The requested MCP compatibility profile is unsupported.",
}


def validate_mcp_tools(
    tools: object,
    *,
    profiles: tuple[str, ...] = SUPPORTED_PROFILES,
) -> dict[str, object]:
    """Validate one raw MCP tools/list payload without I/O or input mutation."""

    requested_profiles = _normalize_profiles(profiles)
    findings: list[dict[str, str]] = []
    tool_count = len(tools) if type(tools) is list else 0
    canonical = b"[]"

    if requested_profiles is None:
        findings.append(_finding("<server>", MCP_CORE_PROFILE, "profile_invalid"))
        return _report(tool_count, canonical, SUPPORTED_PROFILES, findings)
    if type(tools) is not list:
        findings.append(_finding("<server>", MCP_CORE_PROFILE, "tool_list_invalid"))
        return _report(tool_count, canonical, requested_profiles, findings)
    if tool_count > MAX_TOOLS:
        findings.append(_finding("<server>", MCP_CORE_PROFILE, "tool_count_exceeded"))
        return _report(tool_count, canonical, requested_profiles, findings)

    seen_names: set[str] = set()
    core_failed_tools: set[int] = set()
    node_counter = [0]
    normalized_tools: list[dict[str, Any]] = []
    for index, descriptor in enumerate(tools):
        if type(descriptor) is not dict:
            findings.append(_finding(_fallback_tool_name(index), MCP_CORE_PROFILE, "tool_descriptor_invalid"))
            core_failed_tools.add(index)
            continue
        name_value = descriptor.get("name")
        if type(name_value) is not str or not name_value.strip() or len(name_value) > 128:
            name = _fallback_tool_name(index)
            findings.append(_finding(name, MCP_CORE_PROFILE, "tool_name_invalid"))
            core_failed_tools.add(index)
        else:
            name = name_value.strip()
            if name in seen_names:
                findings.append(_finding(name, MCP_CORE_PROFILE, "tool_name_duplicate"))
                core_failed_tools.add(index)
            seen_names.add(name)

        input_schema = descriptor.get("inputSchema")
        if input_schema is None:
            findings.append(_finding(name, MCP_CORE_PROFILE, "input_schema_missing"))
            core_failed_tools.add(index)
            continue
        if type(input_schema) is not dict:
            findings.append(_finding(name, MCP_CORE_PROFILE, "schema_node_invalid"))
            core_failed_tools.add(index)
            continue
        if input_schema.get("type") != "object":
            findings.append(_finding(name, MCP_CORE_PROFILE, "schema_root_type_invalid"))
            core_failed_tools.add(index)
            continue

        before_count = len(findings)
        _validate_schema_node(
            input_schema,
            tool_name=name,
            profile=MCP_CORE_PROFILE,
            depth=0,
            node_counter=node_counter,
            findings=findings,
            parent_keyword=None,
        )
        if len(findings) != before_count:
            core_failed_tools.add(index)
        normalized_tools.append(descriptor)

    if MCP_CORE_PROFILE in requested_profiles and not any(
        item["code"] in {"schema_depth_exceeded", "schema_node_count_exceeded"}
        for item in findings
    ):
        try:
            canonical = _canonical_bytes(normalized_tools)
        except (TypeError, ValueError, RecursionError):
            findings.append(_finding("<server>", MCP_CORE_PROFILE, "schema_node_invalid"))
        else:
            if len(canonical) > MAX_SCHEMA_BYTES:
                findings.append(_finding("<server>", MCP_CORE_PROFILE, "schema_size_exceeded"))

    core_has_server_failure = any(item["profile"] == MCP_CORE_PROFILE for item in findings)
    if CLAUDE_DESKTOP_PORTABLE_PROFILE in requested_profiles and not core_has_server_failure:
        for index, descriptor in enumerate(tools):
            if index in core_failed_tools or type(descriptor) is not dict:
                continue
            name_value = descriptor.get("name")
            name = name_value.strip() if type(name_value) is str and name_value.strip() else _fallback_tool_name(index)
            input_schema = descriptor.get("inputSchema")
            if type(input_schema) is dict:
                _validate_schema_node(
                    input_schema,
                    tool_name=name,
                    profile=CLAUDE_DESKTOP_PORTABLE_PROFILE,
                    depth=0,
                    node_counter=[0],
                    findings=findings,
                    parent_keyword=None,
                )

    return _report(tool_count, canonical, requested_profiles, findings)


def public_finding_message(code: object) -> str | None:
    """Return only a validator-owned fixed message for a known public code."""

    if type(code) is not str:
        return None
    return _PUBLIC_MESSAGES.get(code)


def _validate_schema_node(
    node: object,
    *,
    tool_name: str,
    profile: str,
    depth: int,
    node_counter: list[int],
    findings: list[dict[str, str]],
    parent_keyword: str | None,
) -> None:
    if depth > MAX_SCHEMA_DEPTH:
        _append_once(findings, _finding(tool_name, profile, "schema_depth_exceeded"))
        return
    node_counter[0] += 1
    if node_counter[0] > MAX_SCHEMA_NODES:
        _append_once(findings, _finding(tool_name, profile, "schema_node_count_exceeded"))
        return
    if type(node) is bool:
        if profile == CLAUDE_DESKTOP_PORTABLE_PROFILE and parent_keyword != "additionalProperties":
            _append_once(findings, _finding(tool_name, profile, "portable_boolean_schema_unsupported"))
        return
    if type(node) is not dict:
        _append_once(findings, _finding(tool_name, profile, "schema_node_invalid"))
        return

    properties = node.get("properties")
    if properties is not None:
        if type(properties) is not dict or any(type(key) is not str for key in properties):
            _append_once(findings, _finding(tool_name, profile, "schema_properties_invalid"))
        else:
            for child in properties.values():
                _validate_schema_node(
                    child,
                    tool_name=tool_name,
                    profile=profile,
                    depth=depth + 1,
                    node_counter=node_counter,
                    findings=findings,
                    parent_keyword="properties",
                )

    required = node.get("required")
    if required is not None:
        if type(required) is not list or any(type(item) is not str for item in required):
            _append_once(findings, _finding(tool_name, profile, "schema_required_invalid"))
        elif len(required) != len(set(required)):
            _append_once(findings, _finding(tool_name, profile, "schema_required_duplicate"))
        elif type(properties) is not dict or any(item not in properties for item in required):
            _append_once(findings, _finding(tool_name, profile, "schema_required_unknown"))

    type_value = node.get("type")
    if type_value is not None and not _valid_type_value(type_value):
        _append_once(findings, _finding(tool_name, profile, "schema_type_invalid"))

    ref = node.get("$ref")
    if ref is not None and (type(ref) is not str or not ref.startswith("#")):
        _append_once(findings, _finding(tool_name, MCP_CORE_PROFILE, "external_ref_forbidden"))

    for keyword, value in node.items():
        if keyword in {"properties", "required", "type", "$ref"}:
            continue
        if profile == CLAUDE_DESKTOP_PORTABLE_PROFILE and keyword in _PORTABLE_DENIED_KEYWORDS:
            _append_once(findings, _finding(tool_name, profile, "portable_keyword_unsupported"))
            continue
        if keyword in _SCHEMA_MAP_KEYWORDS:
            if type(value) is not dict or any(type(key) is not str for key in value):
                _append_once(findings, _finding(tool_name, profile, "schema_node_invalid"))
                continue
            for child in value.values():
                _validate_schema_node(
                    child,
                    tool_name=tool_name,
                    profile=profile,
                    depth=depth + 1,
                    node_counter=node_counter,
                    findings=findings,
                    parent_keyword=keyword,
                )
        elif keyword in _SCHEMA_ARRAY_KEYWORDS:
            if type(value) is not list:
                _append_once(findings, _finding(tool_name, profile, "schema_node_invalid"))
                continue
            for child in value:
                _validate_schema_node(
                    child,
                    tool_name=tool_name,
                    profile=profile,
                    depth=depth + 1,
                    node_counter=node_counter,
                    findings=findings,
                    parent_keyword=keyword,
                )
        elif keyword in _SCHEMA_SINGLE_KEYWORDS:
            _validate_schema_node(
                value,
                tool_name=tool_name,
                profile=profile,
                depth=depth + 1,
                node_counter=node_counter,
                findings=findings,
                parent_keyword=keyword,
            )


def _valid_type_value(value: object) -> bool:
    allowed = {"null", "boolean", "object", "array", "number", "string", "integer"}
    if type(value) is str:
        return value in allowed
    if type(value) is list:
        return bool(value) and all(type(item) is str and item in allowed for item in value) and len(value) == len(set(value))
    return False


def _normalize_profiles(profiles: object) -> tuple[str, ...] | None:
    if type(profiles) is not tuple or not profiles:
        return None
    if any(type(item) is not str or item not in SUPPORTED_PROFILES for item in profiles):
        return None
    return tuple(dict.fromkeys(profiles))


def _report(
    tool_count: int,
    canonical: bytes,
    profiles: tuple[str, ...],
    findings: list[dict[str, str]],
) -> dict[str, object]:
    core_failed = any(item["profile"] == MCP_CORE_PROFILE for item in findings)
    profile_result: dict[str, dict[str, object]] = {}
    for profile in profiles:
        count = sum(1 for item in findings if item["profile"] == profile)
        incompatible = count > 0 or (profile == CLAUDE_DESKTOP_PORTABLE_PROFILE and core_failed)
        profile_result[profile] = {
            "status": "incompatible" if incompatible else "compatible",
            "finding_count": count,
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "incompatible" if findings else "compatible",
        "tool_count": tool_count,
        "tool_set_digest": hashlib.sha256(canonical).hexdigest(),
        "profiles": profile_result,
        "findings": findings,
    }


def _finding(tool_name: str, profile: str, code: str) -> dict[str, str]:
    return {
        "tool_name": tool_name,
        "profile": profile,
        "code": code,
        "severity": "error",
        "message": _PUBLIC_MESSAGES[code],
    }


def _append_once(findings: list[dict[str, str]], finding: dict[str, str]) -> None:
    key = (finding["tool_name"], finding["profile"], finding["code"])
    if any((item["tool_name"], item["profile"], item["code"]) == key for item in findings):
        return
    findings.append(finding)


def _fallback_tool_name(index: int) -> str:
    return f"<tool-{index + 1}>"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
