from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from .paths import data_file, tmp_dir


AGENT_INTEROP_E2E_SCHEMA = "across-aaa-agent-interop-e2e/1.0"
LATEST_RESULT_FILE = "agent_interop_e2e_latest.json"
REQUIRED_HOST_TARGETS = {"codex", "claude_code", "mcp", "a2a", "across"}
REQUIRED_MCP_SERVERS = {
    "across-context": "remember_context",
    "across-orchestrator": "evaluate_sandbox_policy",
    "across-autopilot": "export_workflow_pack",
}


def run_agent_interop_e2e(
    *,
    env: Mapping[str, str] | None = None,
    projects_root: Path | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Run the host-neutral AAA plugin interop E2E scenario.

    The scenario is intentionally bounded: it builds a tiny generic agent
    plugin repository, runs Autopilot's plugin compatibility Workflow Pack,
    asks Orchestrator to verify sandbox policy and evidence graph shape, stores
    the compact graph through Context, and proves all three plugins can start
    as MCP servers for Codex, Claude Code, and Claude Desktop hosts.
    """

    source_env = dict(os.environ)
    if env:
        source_env.update({str(key): str(value) for key, value in env.items()})
    roots = _resolve_roots(projects_root, source_env)
    run_root = _new_run_root()
    across_home = run_root / "across-home"
    sample_repo = run_root / "sample-agent-plugin"
    _write_sample_plugin_repo(sample_repo)
    spec_path = _write_interop_spec(roots["autopilot"], sample_repo, run_root)
    runtime_env = _runtime_env(source_env, run_root, roots)

    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    artifacts: dict[str, Any] = {
        "run_root": str(run_root),
        "sample_repo": str(sample_repo),
        "loop_spec": str(spec_path),
        "across_home": str(across_home),
    }

    _run_check(
        checks,
        "context_host_plugin_install",
        "Context installs a managed host-plugin wrapper into the isolated Across runtime",
        lambda: _run_command_payload(
            _context_cli(roots["context"], "install", "host-plugin", "--across-home", str(across_home)),
            cwd=roots["context"],
            env=runtime_env,
        ),
        errors,
    )

    workflow_exports = _run_check(
        checks,
        "workflow_pack_export",
        "Autopilot exports one workflow pack for generic hosts",
        lambda: _workflow_pack_export(roots["autopilot"], runtime_env),
        errors,
    )
    host_targets = set(workflow_exports.get("host_targets") or []) if isinstance(workflow_exports, dict) else set()
    _record_boolean_check(
        checks,
        "host_targets_complete",
        REQUIRED_HOST_TARGETS.issubset(host_targets),
        f"host_targets={sorted(host_targets)}",
        errors,
    )
    product_card = workflow_exports.get("product_card") if isinstance(workflow_exports, dict) else {}
    protocol_readiness = workflow_exports.get("protocol_readiness") if isinstance(workflow_exports, dict) else {}
    trust_receipt = workflow_exports.get("trust_receipt") if isinstance(workflow_exports, dict) else {}
    _record_boolean_check(
        checks,
        "workflow_product_card_ready",
        isinstance(product_card, dict)
        and product_card.get("schema_version") == "across-workflow-pack-product-card/1.0"
        and bool(product_card.get("user_problem"))
        and bool(product_card.get("quickstart")),
        f"product_card_schema={product_card.get('schema_version') if isinstance(product_card, dict) else None}",
        errors,
    )
    _record_boolean_check(
        checks,
        "workflow_protocol_readiness_honest",
        isinstance(protocol_readiness, dict)
        and protocol_readiness.get("schema_version") == "across-workflow-pack-protocol-readiness/1.0"
        and _nested(protocol_readiness, "summary", "honest_protocol_claims") is True,
        f"protocol_score={_nested(protocol_readiness, 'summary', 'score')}",
        errors,
    )
    _record_boolean_check(
        checks,
        "workflow_trust_receipt_ready",
        isinstance(trust_receipt, dict)
        and trust_receipt.get("schema_version") == "across-agent-team-trust-receipt/1.0"
        and bool(_nested(trust_receipt, "evidence_contract", "required")),
        f"trust_receipt_schema={trust_receipt.get('schema_version') if isinstance(trust_receipt, dict) else None}",
        errors,
    )
    host_install_contracts = _run_check(
        checks,
        "generic_host_install_contracts",
        "Context, Orchestrator, and Autopilot expose Codex, Claude Code, and Claude Desktop install contracts",
        lambda: _probe_generic_host_install_contracts(roots, runtime_env, run_root),
        errors,
    )

    validation = _run_check(
        checks,
        "loop_spec_validate",
        "Autopilot validates the scenario LoopSpec",
        lambda: _run_json(_autopilot_cli(roots["autopilot"], "loop", "validate", "--spec", str(spec_path), "--json"), cwd=roots["autopilot"], env=runtime_env),
        errors,
    )
    dry_run = _run_check(
        checks,
        "loop_spec_dry_run",
        "Autopilot preflights adapters, policies, and outputs",
        lambda: _run_json(_autopilot_cli(roots["autopilot"], "loop", "dry-run", "--spec", str(spec_path), "--json"), cwd=roots["autopilot"], env=runtime_env),
        errors,
    )
    loop_result = _run_check(
        checks,
        "autopilot_loop_run",
        "Autopilot runs the plugin compatibility lab against a generic plugin repo",
        lambda: _run_json(
            _autopilot_cli(roots["autopilot"], "loop", "run", "--spec", str(spec_path), "--trigger", "agent-interop-e2e", "--json"),
            cwd=roots["autopilot"],
            env=runtime_env,
            timeout=120,
        ),
        errors,
    )

    evidence = loop_result.get("evidence") if isinstance(loop_result, dict) else {}
    run = loop_result.get("run") if isinstance(loop_result, dict) else {}
    run_id = str(run.get("run_id") or evidence.get("run_id") or "")
    graph = evidence.get("evidence_graph") if isinstance(evidence, dict) else {}
    artifacts["run_id"] = run_id
    artifacts["autopilot_outputs_dir"] = run.get("outputs_dir") if isinstance(run, dict) else None
    artifacts["evidence_graph_schema"] = graph.get("schema_version") if isinstance(graph, dict) else None

    _record_boolean_check(
        checks,
        "workflow_pack_gate_passed",
        _gate_status(evidence, "workflow_pack_exports_ready") == "passed",
        "workflow_pack_exports_ready gate must pass",
        errors,
    )
    _record_boolean_check(
        checks,
        "autopilot_evidence_graph_present",
        isinstance(graph, dict) and graph.get("schema_version") == "across-evidence-graph/1.0",
        f"graph_summary={_graph_summary(graph)}",
        errors,
    )

    sandbox = _run_check(
        checks,
        "orchestrator_sandbox_probe",
        "Orchestrator accepts a no-network read-only sandbox policy without executing commands",
        lambda: _orchestrator_sandbox_probe(roots["orchestrator"], runtime_env, sample_repo),
        errors,
    )
    team_readiness = _run_check(
        checks,
        "orchestrator_agent_team_readiness",
        "Orchestrator verifies the Workflow Pack product card, trust receipt, and honest protocol readiness",
        lambda: _orchestrator_agent_team_readiness(roots["orchestrator"], runtime_env, workflow_exports),
        errors,
    )
    orchestrator_graph = _run_check(
        checks,
        "orchestrator_evidence_graph",
        "Orchestrator verifies the Autopilot evidence graph",
        lambda: _orchestrator_evidence_graph(roots["orchestrator"], runtime_env, evidence),
        errors,
    )
    graph_for_memory = orchestrator_graph if isinstance(orchestrator_graph, dict) and orchestrator_graph else graph
    artifacts["sandbox_status"] = sandbox.get("status") if isinstance(sandbox, dict) else None
    artifacts["agent_team_readiness_status"] = team_readiness.get("status") if isinstance(team_readiness, dict) else None
    artifacts["agent_team_readiness_score"] = team_readiness.get("score") if isinstance(team_readiness, dict) else None
    artifacts["orchestrator_graph_schema"] = graph_for_memory.get("schema_version") if isinstance(graph_for_memory, dict) else None

    remote_mcp = _run_check(
        checks,
        "orchestrator_remote_mcp_oauth_template",
        "Orchestrator renders a secret-free Streamable HTTP/OAuth template for remote MCP hosts",
        lambda: _orchestrator_remote_mcp_template(roots["orchestrator"], runtime_env),
        errors,
    )
    a2a_delegation = _run_check(
        checks,
        "orchestrator_a2a_task_delegation",
        "Orchestrator creates an A2A-style task/message/artifact delegation envelope",
        lambda: _orchestrator_a2a_delegation(roots["orchestrator"], runtime_env, workflow_exports),
        errors,
    )
    otel_export = _run_check(
        checks,
        "orchestrator_otel_genai_export",
        "Orchestrator exports evidence as OTel/GenAI-style spans and eval cases",
        lambda: _orchestrator_otel_export(roots["orchestrator"], runtime_env, graph_for_memory),
        errors,
    )
    _record_boolean_check(
        checks,
        "frontier_interop_contracts_ready",
        remote_mcp.get("schema_version") == "across-remote-mcp-oauth-template/1.0"
        and a2a_delegation.get("schema_version") == "across-a2a-task-delegation/1.0"
        and otel_export.get("schema_version") == "across-otel-genai-export/1.0",
        f"remote={remote_mcp.get('status')} a2a={a2a_delegation.get('status')} spans={_nested(otel_export, 'summary', 'span_count')}",
        errors,
    )
    artifacts["remote_mcp_template_status"] = remote_mcp.get("status") if isinstance(remote_mcp, dict) else None
    artifacts["a2a_task_state"] = _nested(a2a_delegation, "task", "state")
    artifacts["otel_span_count"] = _nested(otel_export, "summary", "span_count")
    artifacts["eval_case_count"] = _nested(otel_export, "summary", "eval_case_count")
    artifacts["otlp_file"] = otel_export.get("otlp_file") if isinstance(otel_export, dict) else None
    artifacts["otlp_resource_span_count"] = _nested(otel_export, "summary", "otlp_resource_span_count")
    _record_boolean_check(
        checks,
        "orchestrator_otlp_file_written",
        bool(otel_export.get("otlp_file")) and _otlp_file_ready(Path(str(otel_export.get("otlp_file")))),
        f"otlp_file={otel_export.get('otlp_file') if isinstance(otel_export, dict) else None}",
        errors,
    )

    remembered = _run_check(
        checks,
        "context_evidence_memory",
        "Context stores compact evidence graph memory as pending review",
        lambda: _context_remember_evidence(roots["context"], runtime_env, graph_for_memory),
        errors,
    )
    recalled = _run_check(
        checks,
        "context_evidence_recall",
        "Context recalls the compact evidence graph memory by run id",
        lambda: _context_recall_evidence(roots["context"], runtime_env, run_id),
        errors,
    )
    _record_boolean_check(
        checks,
        "context_evidence_recalled",
        int(recalled.get("result_count") or 0) >= 1,
        f"result_count={recalled.get('result_count') if isinstance(recalled, dict) else 0}",
        errors,
    )
    artifacts["context_memory_id"] = _nested(remembered, "memory", "id")
    artifacts["context_recall_count"] = recalled.get("result_count") if isinstance(recalled, dict) else None

    receipt_memory = _run_check(
        checks,
        "context_agent_team_receipt_memory",
        "Context stores the agent-team trust receipt as pending team memory",
        lambda: _context_remember_agent_team_receipt(roots["context"], runtime_env, workflow_exports),
        errors,
    )
    receipt_recall = _run_check(
        checks,
        "context_agent_team_receipt_recall",
        "Context recalls the agent-team trust receipt by workflow pack",
        lambda: _context_recall_agent_team_receipt(roots["context"], runtime_env, "plugin-compatibility-lab-v2"),
        errors,
    )
    _record_boolean_check(
        checks,
        "context_agent_team_receipt_recalled",
        int(receipt_recall.get("result_count") or 0) >= 1,
        f"result_count={receipt_recall.get('result_count') if isinstance(receipt_recall, dict) else 0}",
        errors,
    )
    artifacts["context_receipt_memory_id"] = _nested(receipt_memory, "memory", "id")
    artifacts["context_receipt_recall_count"] = receipt_recall.get("result_count") if isinstance(receipt_recall, dict) else None

    mcp_results = _run_check(
        checks,
        "three_plugin_mcp_load",
        "Context, Orchestrator, and Autopilot load as MCP servers for generic hosts",
        lambda: _probe_three_plugin_mcp(roots, runtime_env),
        errors,
    )
    _record_boolean_check(
        checks,
        "mcp_tools_exposed",
        _mcp_required_tools_ready(mcp_results),
        f"mcp_servers={sorted((mcp_results or {}).keys()) if isinstance(mcp_results, dict) else []}",
        errors,
    )

    frontier_results = {
        "remote_mcp": remote_mcp,
        "a2a_delegation": a2a_delegation,
        "otel_export": otel_export,
    }
    summary = _summary(checks, workflow_exports, graph_for_memory, mcp_results, frontier_results)
    payload = {
        "schema_version": AGENT_INTEROP_E2E_SCHEMA,
        "status": "passed" if not errors and all(item.get("status") == "passed" for item in checks) else "failed",
        "generated_at": _now(),
        "scenario": {
            "id": "generic-agent-plugin-compatibility-lab",
            "description": "Run a bounded generic agent plugin through Autopilot, Orchestrator, Context, MCP, and host export contracts.",
            "host_products": ["Codex", "Claude Code", "Claude Desktop"],
            "plugins": ["across-context", "across-orchestrator", "across-autopilot"],
        },
        "summary": summary,
        "checks": checks,
        "artifacts": {key: value for key, value in artifacts.items() if value is not None},
        "host_exports": _host_export_summary(workflow_exports),
        "agent_team_readiness": team_readiness,
        "frontier_interop": frontier_results,
        "host_install_contracts": host_install_contracts,
        "mcp": _mcp_summary(mcp_results),
        "errors": errors,
    }
    if persist:
        _write_latest(payload)
    return payload


def load_agent_interop_e2e_latest() -> dict[str, Any]:
    try:
        payload = json.loads(data_file(LATEST_RESULT_FILE).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {
            "schema_version": AGENT_INTEROP_E2E_SCHEMA,
            "status": "not_run",
            "generated_at": None,
            "summary": {
                "passed_count": 0,
                "failed_count": 0,
                "host_target_count": 0,
                "mcp_server_count": 0,
            },
            "checks": [],
            "errors": [],
        }
    except Exception as exc:
        return {
            "schema_version": AGENT_INTEROP_E2E_SCHEMA,
            "status": "failed",
            "generated_at": None,
            "summary": {"passed_count": 0, "failed_count": 1},
            "checks": [],
            "errors": [f"Unable to read latest interop E2E result: {exc}"],
        }
    return payload if isinstance(payload, dict) else {}


def build_agent_interop_workbench_section(payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    latest = dict(payload or load_agent_interop_e2e_latest())
    summary = dict(latest.get("summary") or {})
    status = str(latest.get("status") or "not_run")
    section_status = "attention" if status == "not_run" else status
    return {
        "id": "agent_interop_e2e",
        "title": "Agent Interop E2E Lab",
        "status": section_status,
        "summary": {
            "status": status,
            "passed_count": summary.get("passed_count", 0),
            "failed_count": summary.get("failed_count", 0),
            "host_target_count": summary.get("host_target_count", 0),
            "mcp_server_count": summary.get("mcp_server_count", 0),
            "evidence_node_count": summary.get("evidence_node_count", 0),
            "protocol_readiness_score": summary.get("protocol_readiness_score"),
            "market_readiness_status": summary.get("market_readiness_status"),
            "trust_receipt_status": summary.get("trust_receipt_status"),
            "frontier_interop_status": summary.get("frontier_interop_status"),
            "remote_mcp_template_status": summary.get("remote_mcp_template_status"),
            "a2a_delegation_status": summary.get("a2a_delegation_status"),
            "otel_span_count": summary.get("otel_span_count"),
            "eval_case_count": summary.get("eval_case_count"),
            "otlp_resource_span_count": summary.get("otlp_resource_span_count"),
        },
        "items": _bounded_check_items(latest.get("checks")),
        "endpoint": "/api/autopilot/agent-interop-e2e",
    }


def augment_release_evaluation_with_agent_interop(
    summary: Mapping[str, Any] | None,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Add host-neutral interop E2E as supplemental release evidence."""

    result = dict(summary or {})
    interop = dict(payload or load_agent_interop_e2e_latest())
    interop_summary = dict(interop.get("summary") or {})
    interop_status = str(interop.get("status") or "not_run")
    interop_failed = _safe_int(interop_summary.get("failed_count"))
    interop_passed = _safe_int(interop_summary.get("passed_count"))
    protocol_score = _safe_int(interop_summary.get("protocol_readiness_score"))
    interop_ready = interop_status == "passed" and interop_failed == 0
    interop_blocked = interop_status == "failed" or interop_failed > 0
    evidence = {
        "id": "agent_interop_e2e",
        "kind": "host_interop_e2e",
        "status": "passed" if interop_ready else "failed" if interop_blocked else "not_run",
        "quality_gate": "passed" if interop_ready else "failed" if interop_blocked else "missing",
        "passed_count": interop_passed,
        "failed_count": interop_failed,
        "host_target_count": _safe_int(interop_summary.get("host_target_count")),
        "mcp_server_count": _safe_int(interop_summary.get("mcp_server_count")),
        "protocol_readiness_score": protocol_score,
        "endpoint": "/api/autopilot/agent-interop-e2e",
    }
    supplemental = list(result.get("supplemental_evidence") or [])
    supplemental = [item for item in supplemental if dict(item).get("id") != "agent_interop_e2e"]
    supplemental.append(evidence)
    result["supplemental_evidence"] = supplemental
    result["release_evidence_count"] = _safe_int(result.get("evaluated_task_count")) + sum(
        1 for item in supplemental if dict(item).get("status") in {"passed", "failed"}
    )
    result["passed_evidence_count"] = _safe_int(result.get("passed_task_count")) + sum(
        1 for item in supplemental if dict(item).get("status") == "passed"
    )
    result["agent_interop_e2e_status"] = interop_status

    checks = list(result.get("readiness_checks") or [])
    checks = [item for item in checks if dict(item).get("id") != "agent_interop_e2e"]
    checks.append(
        {
            "id": "agent_interop_e2e",
            "status": "passed" if interop_ready else "failed" if interop_blocked else "warning",
            "label": "Agent interop E2E",
            "title": "Agent interop E2E",
            "message": "Host-neutral plugin interop E2E is passing."
            if interop_ready
            else "Host-neutral plugin interop E2E failed."
            if interop_blocked
            else "Host-neutral plugin interop E2E has not run.",
            "severity": "high" if interop_blocked else "medium",
        }
    )
    result["readiness_checks"] = checks

    readiness = str(result.get("release_readiness") or "unknown")
    if interop_blocked and readiness != "blocked":
        result["release_readiness"] = "blocked"
        top_risks = list(result.get("top_risks") or [])
        top_risks.insert(
            0,
            {
                "kind": "agent_interop_e2e_failed",
                "severity": "high",
                "count": interop_failed or 1,
                "message": "Host-neutral plugin interop E2E must pass before release.",
            },
        )
        result["top_risks"] = top_risks[:5]
        result["recommendation"] = "Host-neutral plugin interop E2E must pass before release."
    elif readiness == "no_evidence" and interop_ready:
        result["release_readiness"] = "attention"
        result["recommendation"] = (
            "Host-neutral plugin interop E2E is passing; add quality-gated release task evidence before release."
        )
    return result


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _resolve_roots(projects_root: Path | None, env: Mapping[str, str]) -> dict[str, Path]:
    explicit = env.get("ACROSS_PROJECTS_ROOT")
    candidates: list[Path] = []
    for value in (explicit, projects_root):
        if value:
            candidates.append(Path(value).expanduser().resolve())
    source_default = Path(__file__).resolve().parents[4]
    if _running_packaged_app():
        candidates.append(Path.home() / ".across" / "plugins")
    candidates.extend(
        [
            source_default,
            source_default.parent if source_default.name == "across-agents-assistant" else source_default,
            Path.cwd(),
            Path.cwd().parent if Path.cwd().name == "across-agents-assistant" else Path.cwd(),
            Path.home() / "Documents" / "projects",
        ]
    )
    root = next((candidate for candidate in _unique_paths(candidates) if _projects_root_ready(candidate, env)), candidates[0] if candidates else source_default)
    return {
        "projects": root,
        "aaa": Path(env.get("ACROSS_AGENTS_ASSISTANT_SOURCE") or root / "across-agents-assistant").expanduser().resolve(),
        "autopilot": Path(env.get("ACROSS_AUTOPILOT_SOURCE") or root / "across-autopilot").expanduser().resolve(),
        "orchestrator": Path(env.get("ACROSS_ORCHESTRATOR_SOURCE") or root / "across-orchestrator").expanduser().resolve(),
        "context": Path(env.get("ACROSS_CONTEXT_SOURCE") or root / "across-context").expanduser().resolve(),
    }


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path.expanduser().resolve())
        if key in seen:
            continue
        seen.add(key)
        result.append(Path(key))
    return result


def _projects_root_ready(root: Path, env: Mapping[str, str]) -> bool:
    autopilot = Path(env.get("ACROSS_AUTOPILOT_SOURCE") or root / "across-autopilot").expanduser()
    orchestrator = Path(env.get("ACROSS_ORCHESTRATOR_SOURCE") or root / "across-orchestrator").expanduser()
    context = Path(env.get("ACROSS_CONTEXT_SOURCE") or root / "across-context").expanduser()
    aaa = Path(env.get("ACROSS_AGENTS_ASSISTANT_SOURCE") or root / "across-agents-assistant").expanduser()
    orchestrator_ready = (orchestrator / "src" / "across_orchestrator" / "cli.py").is_file() or (orchestrator / "venv" / "bin" / "across-orchestrator").is_file()
    aaa_ready = (aaa / "backend" / "src" / "across_agents_assistant" / "api_server.py").is_file() or _running_packaged_app()
    return all(
        [
            (autopilot / "examples" / "plugin-compatibility-lab-v2.loop.json").is_file(),
            orchestrator_ready,
            (context / "src" / "cli.js").is_file(),
            aaa_ready,
        ]
    )


def _running_packaged_app() -> bool:
    return ".app/Contents/Resources/backend" in str(Path(sys.executable))


def _new_run_root() -> Path:
    root = tmp_dir() / "agent-interop-e2e"
    root.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="run-", dir=str(root))).resolve()


def _runtime_env(source_env: Mapping[str, str], run_root: Path, roots: Mapping[str, Path]) -> dict[str, str]:
    env = dict(source_env)
    across_home = run_root / "across-home"
    bin_dir = across_home / "bin"
    env.update(
        {
            "ACROSS_HOME": str(across_home),
            "ACROSS_AGENTS_HOME": str(run_root / "aaa-home"),
            "ACROSS_CONTEXT_HOME": str(across_home / "data" / "across-context"),
            "ACROSS_ORCHESTRATOR_HOME": str(across_home / "data" / "across-orchestrator"),
            "ACROSS_AUTOPILOT_DISABLE_SOURCE_MIRRORS": "1",
            "ACROSS_AGENTS_ASSISTANT_SOURCE": str(roots["aaa"]),
            "ACROSS_AUTOPILOT_SOURCE": str(roots["autopilot"]),
            "ACROSS_ORCHESTRATOR_SOURCE": str(roots["orchestrator"]),
            "ACROSS_CONTEXT_SOURCE": str(roots["context"]),
        }
    )
    existing_path = str(env.get("PATH") or "")
    env["PATH"] = str(bin_dir) if not existing_path else os.pathsep.join([str(bin_dir), existing_path])
    py_paths = [
        str(path)
        for path in [roots["orchestrator"] / "src", roots["aaa"] / "backend" / "src"]
        if path.exists()
    ]
    existing = str(env.get("PYTHONPATH") or "")
    if py_paths or existing:
        env["PYTHONPATH"] = os.pathsep.join([*py_paths, existing]) if existing else os.pathsep.join(py_paths)
    return env


def _write_sample_plugin_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text(
        json.dumps(
            {
                "name": "@across-lab/generic-agent-plugin",
                "version": "1.0.0",
                "license": "MIT",
                "type": "module",
                "description": "Generic MCP-style agent plugin fixture for AAA interop E2E.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (path / "README.md").write_text(
        "# Generic Agent Plugin\n\n"
        "A host-neutral plugin fixture exposing a read-only MCP-style capability "
        "for Codex, Claude Code, Claude Desktop, and AAA compatibility tests.\n",
        encoding="utf-8",
    )
    (path / "LICENSE").write_text(
        "MIT License\n\nCopyright (c) 2026 Across contributors\n\n"
        "Permission is hereby granted, free of charge, to any person obtaining a copy of this software.\n",
        encoding="utf-8",
    )
    (path / "AGENTS.md").write_text(
        "# AGENTS.md\n\nRun read-only compatibility checks. Do not write secrets, merge, tag, or publish.\n",
        encoding="utf-8",
    )
    (path / "llms.txt").write_text(
        "Generic Agent Plugin: use this fixture to test host-neutral MCP and workflow-pack loading.\n",
        encoding="utf-8",
    )


def _write_interop_spec(autopilot_root: Path, sample_repo: Path, run_root: Path) -> Path:
    template_path = autopilot_root / "examples" / "plugin-compatibility-lab-v2.loop.json"
    spec = json.loads(template_path.read_text(encoding="utf-8"))
    spec["id"] = "plugin-compatibility-lab-v2-e2e"
    spec.setdefault("scope", {})["workspace"] = str(sample_repo)
    spec["sources"][0]["path"] = str(sample_repo)
    spec_path = run_root / "plugin-compatibility-lab-v2-e2e.loop.json"
    spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return spec_path


def _workflow_pack_export(autopilot_root: Path, env: Mapping[str, str]) -> dict[str, Any]:
    return _run_json(
        _autopilot_cli(autopilot_root, "workflow-pack", "export", "--pack", "plugin-compatibility-lab-v2", "--json"),
        cwd=autopilot_root,
        env=env,
    )


def _orchestrator_sandbox_probe(orchestrator_root: Path, env: Mapping[str, str], workspace: Path) -> dict[str, Any]:
    policy = {
        "network_policy": "none",
        "filesystem_policy": "read_only",
        "workspace_root": str(workspace),
        "command_allowlist": ["node --version"],
        "budget": {"max_model_calls": 0},
        "promotion": {"human_approval_required": True, "merge_release_signing_blocked": True},
    }
    return _run_json(
        [
            *_orchestrator_cli(orchestrator_root),
            "sandbox-probe",
            "--policy-json",
            json.dumps(policy, sort_keys=True),
            "--command-json",
            json.dumps(["node", "--version"]),
            "--cwd",
            str(workspace),
            "--json",
        ],
        cwd=orchestrator_root,
        env=env,
    )


def _orchestrator_evidence_graph(orchestrator_root: Path, env: Mapping[str, str], evidence: Mapping[str, Any]) -> dict[str, Any]:
    return _run_json(
        [
            *_orchestrator_cli(orchestrator_root),
            "evidence-graph",
            "--payload-json",
            json.dumps(dict(evidence), sort_keys=True),
            "--json",
        ],
        cwd=orchestrator_root,
        env=env,
        timeout=60,
    )


def _orchestrator_agent_team_readiness(orchestrator_root: Path, env: Mapping[str, str], workflow_exports: Mapping[str, Any]) -> dict[str, Any]:
    return _run_json(
        [
            *_orchestrator_cli(orchestrator_root),
            "agent-team-readiness",
            "--payload-json",
            json.dumps(dict(workflow_exports), sort_keys=True),
            "--json",
        ],
        cwd=orchestrator_root,
        env=env,
        timeout=60,
    )


def _orchestrator_remote_mcp_template(orchestrator_root: Path, env: Mapping[str, str]) -> dict[str, Any]:
    return _run_json(
        [
            *_orchestrator_cli(orchestrator_root),
            "remote-mcp-oauth-template",
            "--config-json",
            json.dumps(
                {
                    "base_url": "https://example.test/across/mcp",
                    "issuer": "https://issuer.example.test",
                    "audience": "aaa-agent-interop-e2e",
                    "scopes": ["mcp.tools", "mcp.resources", "across.evidence.read"],
                },
                sort_keys=True,
            ),
            "--json",
        ],
        cwd=orchestrator_root,
        env=env,
        timeout=60,
    )


def _orchestrator_a2a_delegation(orchestrator_root: Path, env: Mapping[str, str], workflow_exports: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "goal": _nested(workflow_exports, "product_card", "quickstart", "host_prompt") or "Validate plugin portability with Across.",
        "pack_id": workflow_exports.get("pack_id") or "plugin-compatibility-lab-v2",
        "artifacts": workflow_exports.get("artifacts") or ["run://plugin-compatibility-lab/report.md", "run://plugin-compatibility-lab/evidence.json"],
    }
    return _run_json(
        [
            *_orchestrator_cli(orchestrator_root),
            "a2a-delegation",
            "--payload-json",
            json.dumps(payload, sort_keys=True),
            "--json",
        ],
        cwd=orchestrator_root,
        env=env,
        timeout=60,
    )


def _orchestrator_otel_export(orchestrator_root: Path, env: Mapping[str, str], graph: Mapping[str, Any]) -> dict[str, Any]:
    otlp_file = Path(str(env.get("ACROSS_HOME") or tempfile.gettempdir())) / "agent-interop-e2e" / "otel-traces.json"
    return _run_json(
        [
            *_orchestrator_cli(orchestrator_root),
            "otel-export",
            "--payload-json",
            json.dumps(dict(graph), sort_keys=True),
            "--otlp-file",
            str(otlp_file),
            "--json",
        ],
        cwd=orchestrator_root,
        env=env,
        timeout=60,
    )


def _otlp_file_ready(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return payload.get("schema_version") == "otlp-traces-json/1.0" and bool(payload.get("resourceSpans"))


def _context_remember_evidence(context_root: Path, env: Mapping[str, str], graph: Mapping[str, Any]) -> dict[str, Any]:
    return _run_json(
        _context_cli(
            context_root,
            "remember-evidence",
            "--graph-json",
            json.dumps(dict(graph), sort_keys=True),
            "--spec-id",
            str(graph.get("spec_id") or "plugin-compatibility-lab-v2-e2e"),
            "--run-id",
            str(graph.get("run_id") or "run-unknown"),
            "--summary",
            "Generic host interop E2E evidence graph for Codex, Claude Code, Claude Desktop, and AAA.",
            "--json",
        ),
        cwd=context_root,
        env=env,
    )


def _context_recall_evidence(context_root: Path, env: Mapping[str, str], run_id: str) -> dict[str, Any]:
    return _run_json(
        _context_cli(context_root, "recall-evidence", "--run-id", run_id or "run-unknown", "--json"),
        cwd=context_root,
        env=env,
    )


def _context_remember_agent_team_receipt(context_root: Path, env: Mapping[str, str], workflow_exports: Mapping[str, Any]) -> dict[str, Any]:
    return _run_json(
        _context_cli(
            context_root,
            "remember-agent-team-receipt",
            "--pack-id",
            str(workflow_exports.get("pack_id") or "plugin-compatibility-lab-v2"),
            "--receipt-json",
            json.dumps(dict(workflow_exports.get("trust_receipt") or {}), sort_keys=True),
            "--product-card-json",
            json.dumps(dict(workflow_exports.get("product_card") or {}), sort_keys=True),
            "--protocol-readiness-json",
            json.dumps(dict(workflow_exports.get("protocol_readiness") or {}), sort_keys=True),
            "--json",
        ),
        cwd=context_root,
        env=env,
    )


def _context_recall_agent_team_receipt(context_root: Path, env: Mapping[str, str], pack_id: str) -> dict[str, Any]:
    return _run_json(
        _context_cli(context_root, "recall-agent-team-receipts", "--pack-id", pack_id, "--json"),
        cwd=context_root,
        env=env,
    )


def _probe_three_plugin_mcp(roots: Mapping[str, Path], env: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    commands = {
        "across-context": _context_cli(roots["context"], "mcp"),
        "across-orchestrator": [*_orchestrator_cli(roots["orchestrator"]), "mcp"],
        "across-autopilot": _autopilot_cli(roots["autopilot"], "mcp"),
    }
    results: dict[str, dict[str, Any]] = {}
    for server_id, command in commands.items():
        results[server_id] = _mcp_initialize_and_list_tools(
            command,
            cwd=roots["context"] if server_id == "across-context" else roots["orchestrator"] if server_id == "across-orchestrator" else roots["autopilot"],
            env=env,
        )
    return results


def _probe_generic_host_install_contracts(roots: Mapping[str, Path], env: Mapping[str, str], run_root: Path) -> dict[str, Any]:
    claude_desktop_config = run_root / "claude_desktop_config.json"
    claude_desktop_config.write_text(json.dumps({"deploymentMode": "e2e"}, sort_keys=True), encoding="utf-8")
    commands = {
        "across-context": {
            "codex": _context_cli(roots["context"], "install", "codex-mcp", "--stdout"),
            "claude_code": _context_cli(roots["context"], "install", "claude-code", "--stdout"),
            "claude_desktop": _context_cli(roots["context"], "install", "claude-desktop", "--config-file", str(claude_desktop_config)),
            "cwd": roots["context"],
        },
        "across-orchestrator": {
            "codex": [*_orchestrator_cli(roots["orchestrator"]), "install", "codex-mcp", "--stdout"],
            "claude_code": [*_orchestrator_cli(roots["orchestrator"]), "install", "claude-code", "--stdout"],
            "claude_desktop": [*_orchestrator_cli(roots["orchestrator"]), "install", "claude-desktop", "--config-file", str(claude_desktop_config), "--json"],
            "cwd": roots["orchestrator"],
        },
        "across-autopilot": {
            "codex": _autopilot_cli(roots["autopilot"], "install", "codex-mcp", "--stdout"),
            "claude_code": _autopilot_cli(roots["autopilot"], "install", "claude-code", "--stdout"),
            "claude_desktop": _autopilot_cli(roots["autopilot"], "install", "claude-desktop", "--config-file", str(claude_desktop_config)),
            "cwd": roots["autopilot"],
        },
    }
    result: dict[str, Any] = {}
    for plugin_id, plugin_commands in commands.items():
        cwd = Path(plugin_commands["cwd"])
        codex = _run_text(list(plugin_commands["codex"]), cwd=cwd, env=env)
        claude_code = _run_text(list(plugin_commands["claude_code"]), cwd=cwd, env=env)
        _run_text(list(plugin_commands["claude_desktop"]), cwd=cwd, env=env)
        result[plugin_id] = {
            "codex_command": codex.strip(),
            "claude_code_command": claude_code.strip(),
            "codex_ready": plugin_id in codex,
            "claude_code_ready": plugin_id in claude_code,
        }
    desktop_payload = json.loads(claude_desktop_config.read_text(encoding="utf-8"))
    servers = dict(desktop_payload.get("mcpServers") or {})
    result["claude_desktop"] = {
        "config_file": str(claude_desktop_config),
        "server_ids": sorted(servers),
        "server_count": len(servers),
        "ready": REQUIRED_MCP_SERVERS.keys() <= servers.keys(),
    }
    result["status"] = "passed" if all(
        item.get("codex_ready") and item.get("claude_code_ready")
        for key, item in result.items()
        if key.startswith("across-")
    ) and result["claude_desktop"]["ready"] else "failed"
    return result


def _mcp_initialize_and_list_tools(command: list[str], *, cwd: Path, env: Mapping[str, str], timeout: float = 10.0) -> dict[str, Any]:
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=dict(env),
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )
    lines: queue.Queue[str] = queue.Queue()

    def reader() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            lines.put(line)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        _write_mcp_message(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "aaa-agent-interop-e2e", "version": "1.0"}}})
        _write_mcp_message(process, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        _write_mcp_message(process, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        deadline = time.time() + timeout
        initialize_result: dict[str, Any] = {}
        tools_result: dict[str, Any] = {}
        while time.time() < deadline and not tools_result:
            try:
                line = lines.get(timeout=0.2)
            except queue.Empty:
                if process.poll() is not None:
                    break
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") == 1:
                initialize_result = message.get("result") or {}
            if message.get("id") == 2:
                tools_result = message.get("result") or {}
        tools = tools_result.get("tools") if isinstance(tools_result, dict) else []
        tool_names = [str(item.get("name")) for item in tools if isinstance(item, dict)]
        return {
            "status": "passed" if tool_names else "failed",
            "tool_count": len(tool_names),
            "tool_names": tool_names[:40],
            "server_info": initialize_result.get("serverInfo") if isinstance(initialize_result, dict) else None,
        }
    finally:
        try:
            process.terminate()
            process.wait(timeout=2)
        except Exception:
            process.kill()


def _write_mcp_message(process: subprocess.Popen[str], message: Mapping[str, Any]) -> None:
    assert process.stdin is not None
    process.stdin.write(json.dumps(dict(message), separators=(",", ":")) + "\n")
    process.stdin.flush()


def _autopilot_cli(root: Path, *args: str) -> list[str]:
    return ["node", str(root / "src" / "cli.js"), *args]


def _context_cli(root: Path, *args: str) -> list[str]:
    return ["node", str(root / "src" / "cli.js"), *args]


def _orchestrator_cli(root: Path) -> list[str]:
    python = root / ".venv" / "bin" / "python"
    managed = root / "venv" / "bin" / "across-orchestrator"
    if managed.exists():
        return [str(managed)]
    return [str(python if python.exists() else Path(sys.executable)), "-m", "across_orchestrator.cli"]


def _run_command_payload(command: list[str], *, cwd: Path, env: Mapping[str, str], timeout: int = 60) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        env=dict(env),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(_command_error(command, completed))
    return {
        "status": "passed",
        "command": _command_label(command),
        "stdout_tail": (completed.stdout or "").strip().splitlines()[-2:],
    }


def _run_text(command: list[str], *, cwd: Path, env: Mapping[str, str], timeout: int = 60) -> str:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        env=dict(env),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(_command_error(command, completed))
    return completed.stdout or ""


def _run_json(command: list[str], *, cwd: Path, env: Mapping[str, str], timeout: int = 60) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        env=dict(env),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(_command_error(command, completed))
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{_command_label(command)} returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{_command_label(command)} returned a non-object JSON payload")
    return payload


def _run_check(
    checks: list[dict[str, Any]],
    check_id: str,
    description: str,
    operation: Any,
    errors: list[str],
) -> dict[str, Any]:
    started = time.time()
    try:
        payload = operation()
        status = _payload_status(payload)
        checks.append(
            {
                "id": check_id,
                "status": "passed" if status in {"passed", "completed", "ready", "valid", "accepted_pending"} else "failed",
                "description": description,
                "duration_ms": int((time.time() - started) * 1000),
                "summary": _payload_summary(payload),
            }
        )
        if checks[-1]["status"] != "passed":
            errors.append(f"{check_id} returned status {status}")
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        message = f"{check_id} failed: {exc}"
        errors.append(message)
        checks.append(
            {
                "id": check_id,
                "status": "failed",
                "description": description,
                "duration_ms": int((time.time() - started) * 1000),
                "summary": message,
            }
        )
        return {}


def _record_boolean_check(
    checks: list[dict[str, Any]],
    check_id: str,
    passed: bool,
    summary: str,
    errors: list[str],
) -> None:
    checks.append(
        {
            "id": check_id,
            "status": "passed" if passed else "failed",
            "description": summary,
            "duration_ms": 0,
            "summary": summary,
        }
    )
    if not passed:
        errors.append(f"{check_id} failed: {summary}")


def _payload_status(payload: Mapping[str, Any]) -> str:
    if payload and all(isinstance(item, Mapping) and item.get("status") == "passed" for item in payload.values()):
        return "passed"
    if payload.get("valid") is True:
        return "valid"
    if payload.get("status"):
        return str(payload.get("status"))
    run = payload.get("run") if isinstance(payload.get("run"), Mapping) else {}
    if run.get("status"):
        return str(run.get("status"))
    if payload.get("schema_version"):
        return "passed"
    return "unknown"


def _payload_summary(payload: Mapping[str, Any]) -> str:
    if "host_targets" in payload:
        return f"host_targets={','.join(str(item) for item in payload.get('host_targets') or [])}"
    if "valid" in payload:
        return f"valid={payload.get('valid')} spec_id={payload.get('spec_id')}"
    if "run" in payload and isinstance(payload.get("run"), Mapping):
        run = payload["run"]
        return f"run_id={run.get('run_id')} status={run.get('status')}"
    if "summary" in payload and isinstance(payload.get("summary"), Mapping):
        return ", ".join(f"{key}={value}" for key, value in list(payload["summary"].items())[:5])
    if "result_count" in payload:
        return f"result_count={payload.get('result_count')}"
    if "tool_count" in payload:
        return f"tool_count={payload.get('tool_count')}"
    return f"schema={payload.get('schema_version') or 'unknown'} status={_payload_status(payload)}"


def _summary(
    checks: list[Mapping[str, Any]],
    workflow_exports: Mapping[str, Any],
    graph: Mapping[str, Any],
    mcp_results: Mapping[str, Mapping[str, Any]] | None,
    frontier_results: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    passed = sum(1 for item in checks if item.get("status") == "passed")
    failed = sum(1 for item in checks if item.get("status") == "failed")
    graph_summary = dict(graph.get("summary") or {})
    return {
        "passed_count": passed,
        "failed_count": failed,
        "host_target_count": len(workflow_exports.get("host_targets") or []),
        "required_host_targets": sorted(REQUIRED_HOST_TARGETS),
        "mcp_server_count": len(mcp_results or {}),
        "evidence_node_count": graph_summary.get("node_count", 0),
        "evidence_edge_count": graph_summary.get("edge_count", 0),
        "protocol_readiness_score": _nested(workflow_exports, "protocol_readiness", "summary", "score"),
        "market_readiness_status": _nested(workflow_exports, "product_card", "market_readiness", "status"),
        "trust_receipt_status": _nested(workflow_exports, "trust_receipt", "status"),
        "frontier_interop_status": _nested(workflow_exports, "frontier_interop", "status"),
        "remote_mcp_template_status": _nested(frontier_results or {}, "remote_mcp", "status"),
        "a2a_delegation_status": _nested(frontier_results or {}, "a2a_delegation", "status"),
        "otel_span_count": _nested(frontier_results or {}, "otel_export", "summary", "span_count"),
        "eval_case_count": _nested(frontier_results or {}, "otel_export", "summary", "eval_case_count"),
        "otlp_resource_span_count": _nested(frontier_results or {}, "otel_export", "summary", "otlp_resource_span_count"),
    }


def _host_export_summary(workflow_exports: Mapping[str, Any]) -> dict[str, Any]:
    hosts = workflow_exports.get("hosts") if isinstance(workflow_exports.get("hosts"), Mapping) else {}
    result: dict[str, Any] = {
        "host_targets": list(workflow_exports.get("host_targets") or []),
        "product_card_schema": _nested(workflow_exports, "product_card", "schema_version"),
        "product_headline": _nested(workflow_exports, "product_card", "headline"),
        "protocol_readiness_score": _nested(workflow_exports, "protocol_readiness", "summary", "score"),
        "trust_receipt_schema": _nested(workflow_exports, "trust_receipt", "schema_version"),
        "frontier_interop_schema": _nested(workflow_exports, "frontier_interop", "schema_version"),
        "remote_mcp_schema": _nested(workflow_exports, "frontier_interop", "remote_mcp", "schema_version"),
        "a2a_delegation_schema": _nested(workflow_exports, "frontier_interop", "a2a", "schema_version"),
        "otel_schema": _nested(workflow_exports, "frontier_interop", "observability", "otel_schema"),
    }
    for host_id in ["codex", "claude_code", "mcp", "a2a", "across"]:
        host = hosts.get(host_id) if isinstance(hosts, Mapping) else {}
        if isinstance(host, Mapping):
            result[host_id] = {
                "type": host.get("type"),
                "invocation": host.get("invocation"),
                "instruction_contract": host.get("instruction_contract"),
                "tools": host.get("tools"),
            }
    return result


def _mcp_summary(results: Mapping[str, Mapping[str, Any]] | None) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for server_id, result in dict(results or {}).items():
        summary[server_id] = {
            "status": result.get("status"),
            "tool_count": result.get("tool_count"),
            "required_tool": REQUIRED_MCP_SERVERS.get(server_id),
            "required_tool_present": REQUIRED_MCP_SERVERS.get(server_id) in set(result.get("tool_names") or []),
        }
    return summary


def _mcp_required_tools_ready(results: Mapping[str, Mapping[str, Any]] | None) -> bool:
    if not isinstance(results, Mapping):
        return False
    for server_id, required_tool in REQUIRED_MCP_SERVERS.items():
        payload = results.get(server_id)
        if not isinstance(payload, Mapping):
            return False
        if payload.get("status") != "passed":
            return False
        if required_tool not in set(payload.get("tool_names") or []):
            return False
    return True


def _gate_status(evidence: Mapping[str, Any], gate_id: str) -> str:
    for gate in evidence.get("gates") or []:
        if isinstance(gate, Mapping) and gate.get("id") == gate_id:
            return str(gate.get("status") or "")
    return ""


def _graph_summary(graph: Any) -> str:
    if not isinstance(graph, Mapping):
        return "missing"
    return json.dumps(graph.get("summary") or {}, sort_keys=True)


def _bounded_check_items(value: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, Mapping):
            continue
        items.append(
            {
                "id": item.get("id"),
                "status": item.get("status"),
                "summary": item.get("summary"),
            }
        )
    return items[:12]


def _write_latest(payload: Mapping[str, Any]) -> None:
    path = data_file(LATEST_RESULT_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _nested(payload: Any, *path: str) -> Any:
    current = payload
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _command_label(command: list[str]) -> str:
    return " ".join(str(item) for item in command[:4])


def _command_error(command: list[str], completed: subprocess.CompletedProcess[str]) -> str:
    stderr = (completed.stderr or "").strip().replace("\n", " ")[:1000]
    stdout = (completed.stdout or "").strip().replace("\n", " ")[:500]
    return f"{_command_label(command)} failed with exit {completed.returncode}: {stderr or stdout}"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
