import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path

import across_agents_assistant.agent_interop_e2e as interop
from across_agents_assistant.agent_interop_e2e import (
    AgentInteropE2ERunCoordinator,
    _probe_installed_plugin_compatibility,
    build_agent_interop_workbench_section,
    plugin_provenance_digest,
    public_agent_interop_e2e_result,
)


def test_source_only_interop_defers_installed_compatibility_to_packaged_acceptance(monkeypatch):
    monkeypatch.setattr(interop, "plugin_payload", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        interop,
        "discover_across_plugins",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("source-only probe must not inspect installed plugins")),
    )

    result = interop._probe_current_installed_plugin_compatibility({})

    assert result == {
        "schema_version": "across-first-party-mcp-compatibility/1.0",
        "status": "not_run",
        "reason": "packaged_payload_provenance_unavailable",
        "compatible_plugin_count": 0,
        "incompatible_plugin_count": 0,
        "portable_tool_count": 0,
        "plugins": {},
    }


def test_agent_interop_run_coordinator_returns_immediately_and_deduplicates_active_run():
    coordinator = AgentInteropE2ERunCoordinator()
    release = threading.Event()
    started = threading.Event()
    calls = []

    def runner():
        calls.append("run")
        started.set()
        release.wait(timeout=2)
        return {"status": "passed", "summary": {"failed_count": 0}}

    first = coordinator.start(runner)
    assert started.wait(timeout=1)
    second = coordinator.start(runner)

    assert first["status"] == "running"
    assert second["status"] == "running"
    assert calls == ["run"]

    release.set()
    deadline = time.monotonic() + 2
    while coordinator.status()["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)

    assert coordinator.status()["status"] == "passed"
    assert coordinator.status()["failed_count"] == 0


def test_agent_interop_run_coordinator_exposes_bounded_failure_state():
    coordinator = AgentInteropE2ERunCoordinator()

    def runner():
        raise RuntimeError("private local failure details")

    coordinator.start(runner)
    deadline = time.monotonic() + 2
    while coordinator.status()["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)

    assert coordinator.status()["status"] == "failed"
    assert coordinator.status()["failed_count"] == 1
    assert "private local failure details" not in str(coordinator.status())


def _write_mcp_fixture(
    root: Path,
    plugin_id: str,
    tools: list[dict[str, object]],
    *,
    respond: bool = True,
) -> tuple[dict[str, object], dict[str, object]]:
    plugin_root = root / "plugins" / plugin_id
    plugin_bin = plugin_root / "bin"
    plugin_bin.mkdir(parents=True)
    command = plugin_bin / plugin_id
    command.write_text(
        f"""#!{sys.executable}
import json
import os
from pathlib import Path

pid_dir = Path(os.environ["FAKE_MCP_PID_DIR"])
pid_dir.mkdir(parents=True, exist_ok=True)
(pid_dir / "{plugin_id}.pid").write_text(str(os.getpid()), encoding="utf-8")
tools = json.loads({json.dumps(json.dumps(tools))})
for line in __import__("sys").stdin:
    message = json.loads(line)
    if {respond!r} and message.get("id") == 1:
        print(json.dumps({{"jsonrpc": "2.0", "id": 1, "result": {{"protocolVersion": "2024-11-05", "serverInfo": {{"name": "{plugin_id}", "version": "1.0.0"}}}}}}), flush=True)
    elif {respond!r} and message.get("id") == 2:
        print(json.dumps({{"jsonrpc": "2.0", "id": 2, "result": {{"tools": tools}}}}), flush=True)
""",
        encoding="utf-8",
    )
    command.chmod(0o755)
    row = {
        "plugin_id": plugin_id,
        "version": "1.0.0",
        "installed": True,
        "available": True,
        "integrity_ok": True,
        "command": str(command),
        "paths": {"plugin": str(plugin_root), "bin": str(root / "bin")},
    }
    payload = {
        "version": "1.0.0",
        "commit": "a" * 40,
        "source_sha256": ("b" if plugin_id == "across-orchestrator" else "c") * 64,
        "sha256": "d" * 64,
    }
    return row, payload


def test_public_plugin_provenance_digest_preserves_compatibility_canonicalization():
    row = {
        "plugin_id": "across-context",
        "version": "1.2.3",
        "private_path": "/private/plugin",
    }
    descriptor = {
        "version": "1.2.3",
        "commit": "a" * 40,
        "source_sha256": "b" * 64,
        "sha256": "c" * 64,
        "private_archive": "/private/payload.tar.gz",
    }
    expected_subject = {
        "plugin_id": "across-context",
        "version": "1.2.3",
        "payload_version": "1.2.3",
        "commit": "a" * 40,
        "source_sha256": "b" * 64,
        "sha256": "c" * 64,
    }
    expected = hashlib.sha256(
        json.dumps(expected_subject, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    assert plugin_provenance_digest(row, descriptor) == expected


def test_plugin_provenance_uses_payload_sha_as_node_plugin_source_identity():
    row = {"plugin_id": "across-context", "version": "1.2.3"}
    descriptor = {
        "version": "1.2.3",
        "commit": "a" * 40,
        "sha256": "c" * 64,
    }
    expected_subject = {
        "plugin_id": "across-context",
        "version": "1.2.3",
        "payload_version": "1.2.3",
        "commit": "a" * 40,
        "source_sha256": "c" * 64,
        "sha256": "c" * 64,
    }
    expected = hashlib.sha256(
        json.dumps(expected_subject, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    assert plugin_provenance_digest(row, descriptor) == expected


def test_installed_plugin_compatibility_probes_real_processes_and_exposes_only_bounded_evidence(tmp_path):
    required_tools = {
        "across-context": "remember_context",
        "across-orchestrator": "evaluate_sandbox_policy",
        "across-autopilot": "export_workflow_pack",
    }
    rows = []
    payloads = {}
    for plugin_id, tool_name in required_tools.items():
        row, payload = _write_mcp_fixture(
            tmp_path,
            plugin_id,
            [{"name": tool_name, "description": "Read public status", "inputSchema": {"type": "object", "properties": {}}}],
        )
        rows.append(row)
        payloads[plugin_id] = payload

    pid_dir = tmp_path / "pids"
    result = _probe_installed_plugin_compatibility(
        rows,
        payload_descriptors=payloads,
        env={**os.environ, "FAKE_MCP_PID_DIR": str(pid_dir)},
    )

    assert result["schema_version"] == "across-first-party-mcp-compatibility/1.0"
    assert result["status"] == "compatible"
    assert result["compatible_plugin_count"] == 3
    assert result["incompatible_plugin_count"] == 0
    assert result["portable_tool_count"] == 3
    assert set(result["plugins"]) == set(required_tools)
    for plugin_id, plugin in result["plugins"].items():
        assert plugin["status"] == "compatible"
        assert plugin["version"] == "1.0.0"
        assert len(plugin["provenance_digest"]) == 64
        assert len(plugin["tool_set_digest"]) == 64
        assert plugin["tool_count"] == 1
        assert plugin["findings"] == []
        assert "_raw_tools" not in plugin
        pid = int((pid_dir / f"{plugin_id}.pid").read_text(encoding="utf-8"))
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.01)
        else:
            raise AssertionError(f"probe process {pid} did not exit")
    serialized = json.dumps(result, sort_keys=True)
    assert str(tmp_path) not in serialized
    assert "Read public status" not in serialized
    assert "inputSchema" not in serialized


def test_installed_plugin_compatibility_rejects_unmanaged_command_without_launching_it(tmp_path):
    marker = tmp_path / "launched"
    command = tmp_path / "outside-command"
    command.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
    command.chmod(0o755)
    row = {
        "plugin_id": "across-context",
        "version": "1.0.0",
        "installed": True,
        "available": True,
        "integrity_ok": True,
        "command": str(command),
        "paths": {"plugin": str(tmp_path / "plugins" / "across-context"), "bin": str(tmp_path / "bin")},
    }

    result = _probe_installed_plugin_compatibility(
        [row],
        payload_descriptors={"across-context": {
            "version": "1.0.0",
            "commit": "b" * 40,
            "sha256": "a" * 64,
        }},
        env=os.environ,
    )

    assert result["status"] == "incompatible"
    assert result["plugins"]["across-context"]["findings"] == [{
        "code": "managed_command_invalid",
        "severity": "error",
        "message": "The installed plugin command is outside its managed runtime boundary.",
    }]
    assert not marker.exists()
    assert str(tmp_path) not in str(result)


def test_installed_plugin_compatibility_maps_private_probe_failure_to_fixed_finding(tmp_path):
    plugin_root = tmp_path / "plugins" / "across-context"
    plugin_root.mkdir(parents=True)
    row = {
        "plugin_id": "across-context",
        "version": "1.0.0",
        "installed": True,
        "available": True,
        "integrity_ok": True,
        "command": str(plugin_root / "private-missing-command"),
        "paths": {"plugin": str(plugin_root), "bin": str(tmp_path / "bin")},
    }

    result = _probe_installed_plugin_compatibility(
        [row],
        payload_descriptors={"across-context": {
            "version": "1.0.0",
            "commit": "b" * 40,
            "sha256": "a" * 64,
        }},
        env=os.environ,
    )

    assert result["plugins"]["across-context"]["findings"] == [{
        "code": "mcp_probe_failed",
        "severity": "error",
        "message": "The installed MCP server could not provide a bounded tool list.",
    }]
    assert "private-missing-command" not in str(result)


def test_installed_plugin_compatibility_requires_all_three_first_party_plugins():
    result = _probe_installed_plugin_compatibility(
        [],
        payload_descriptors={},
        env=os.environ,
    )

    assert result["status"] == "incompatible"
    assert result["compatible_plugin_count"] == 0
    assert result["incompatible_plugin_count"] == 3
    assert set(result["plugins"]) == {
        "across-context",
        "across-orchestrator",
        "across-autopilot",
    }
    assert all(
        plugin["findings"] == [{
            "code": "plugin_unavailable",
            "severity": "error",
            "message": "The managed plugin is not installed, healthy, and integrity-valid.",
        }]
        for plugin in result["plugins"].values()
    )


def test_installed_plugin_compatibility_terminates_timed_out_process_and_sanitizes_failure(
    tmp_path,
    monkeypatch,
):
    row, payload = _write_mcp_fixture(
        tmp_path,
        "across-context",
        [],
        respond=False,
    )
    pid_dir = tmp_path / "pids"
    observed_pids = []
    real_popen = interop.subprocess.Popen

    def recording_popen(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        observed_pids.append(process.pid)
        return process

    monkeypatch.setattr(interop.subprocess, "Popen", recording_popen)

    result = _probe_installed_plugin_compatibility(
        [row],
        payload_descriptors={"across-context": payload},
        env={**os.environ, "FAKE_MCP_PID_DIR": str(pid_dir)},
        probe_timeout=0.5,
    )

    assert result["plugins"]["across-context"]["findings"] == [{
        "code": "mcp_probe_failed",
        "severity": "error",
        "message": "The installed MCP server could not provide a bounded tool list.",
    }]
    assert len(observed_pids) == 1
    pid = observed_pids[0]
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.01)
    else:
        raise AssertionError(f"timed-out probe process {pid} did not exit")
    assert str(tmp_path) not in str(result)


def test_installed_plugin_compatibility_requires_host_managed_payload_provenance(tmp_path):
    plugin_root = tmp_path / "plugins" / "across-context"
    plugin_root.mkdir(parents=True)
    marker = tmp_path / "launched"
    command = plugin_root / "across-context"
    command.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
    command.chmod(0o755)
    row = {
        "plugin_id": "across-context",
        "version": "1.0.0",
        "installed": True,
        "available": True,
        "integrity_ok": True,
        "command": str(command),
        "paths": {"plugin": str(plugin_root), "bin": str(tmp_path / "bin")},
    }

    result = _probe_installed_plugin_compatibility(
        [row],
        payload_descriptors={"across-context": {}},
        env=os.environ,
    )

    assert result["plugins"]["across-context"]["findings"] == [{
        "code": "payload_provenance_missing",
        "severity": "error",
        "message": "The managed payload does not provide complete immutable provenance.",
    }]
    assert not marker.exists()


def test_public_interop_result_includes_compatibility_summary_without_private_plugin_details():
    result = public_agent_interop_e2e_result({
        "status": "failed",
        "summary": {
            "passed_count": 4,
            "failed_count": 1,
            "schema_compatibility_status": "incompatible",
            "compatible_plugin_count": 2,
            "incompatible_plugin_count": 1,
            "portable_tool_count": 47,
            "private_schema": {"token": "provider-private-marker"},
        },
        "mcp_schema_compatibility": {
            "schema_version": "across-first-party-mcp-compatibility/1.0",
            "status": "incompatible",
            "compatible_plugin_count": 2,
            "incompatible_plugin_count": 1,
            "portable_tool_count": 47,
            "private_command": "/private/provider-command",
            "plugins": {
                "across-orchestrator": {
                    "status": "incompatible",
                    "version": "0.10.5",
                    "provenance_digest": "a" * 64,
                    "tool_count": 18,
                    "tool_set_digest": "b" * 64,
                    "profiles": {
                        "mcp_core": {"status": "compatible", "finding_count": 0},
                        "claude_desktop_portable": {"status": "incompatible", "finding_count": 1},
                    },
                    "findings": [{
                        "tool_name": "register_external_agent_plugin",
                        "profile": "claude_desktop_portable",
                        "code": "portable_keyword_unsupported",
                        "severity": "error",
                        "message": "provider-private-message",
                        "private_schema": {"anyOf": ["provider-private-marker"]},
                    }],
                    "raw_schema": {"provider-private-marker": True},
                },
            },
        },
        "checks": [],
        "errors": [],
    })

    assert result["summary"]["schema_compatibility_status"] == "incompatible"
    assert result["summary"]["compatible_plugin_count"] == 2
    assert result["summary"]["incompatible_plugin_count"] == 1
    assert result["summary"]["portable_tool_count"] == 47
    compatibility = result["mcp_schema_compatibility"]
    plugin = compatibility["plugins"]["across-orchestrator"]
    assert plugin == {
        "status": "incompatible",
        "version": "0.10.5",
        "provenance_digest": "a" * 64,
        "tool_count": 18,
        "tool_set_digest": "b" * 64,
        "profiles": {
            "mcp_core": {"status": "compatible", "finding_count": 0},
            "claude_desktop_portable": {"status": "incompatible", "finding_count": 1},
        },
        "findings": [{
            "tool_name": "register_external_agent_plugin",
            "profile": "claude_desktop_portable",
            "code": "portable_keyword_unsupported",
            "severity": "error",
            "message": "This JSON Schema keyword is not in the Claude Desktop portable profile.",
        }],
    }
    assert "provider-private-marker" not in str(result)
    assert "provider-private-message" not in str(result)
    assert "/private/provider-command" not in str(result)


def test_workbench_section_flattens_only_safe_compatibility_findings():
    section = build_agent_interop_workbench_section({
        "status": "failed",
        "summary": {
            "schema_compatibility_status": "incompatible",
            "compatible_plugin_count": 2,
            "incompatible_plugin_count": 1,
            "portable_tool_count": 47,
        },
        "mcp_schema_compatibility": {
            "status": "incompatible",
            "compatible_plugin_count": 2,
            "incompatible_plugin_count": 1,
            "portable_tool_count": 47,
            "plugins": {
                "across-orchestrator": {
                    "status": "incompatible",
                    "version": "0.10.5",
                    "provenance_digest": "a" * 64,
                    "tool_count": 18,
                    "tool_set_digest": "b" * 64,
                    "profiles": {},
                    "findings": [{
                        "tool_name": "register_external_agent_plugin",
                        "profile": "claude_desktop_portable",
                        "code": "portable_keyword_unsupported",
                        "severity": "error",
                        "message": "provider-private-message",
                    }],
                },
            },
        },
        "checks": [],
    })

    assert section["summary"]["schema_compatibility_status"] == "incompatible"
    assert section["items"][0]["plugin_id"] == "across-orchestrator"
    assert section["items"][0]["code"] == "portable_keyword_unsupported"
    assert section["items"][0]["message"] == "This JSON Schema keyword is not in the Claude Desktop portable profile."
    assert "provider-private-message" not in str(section)
