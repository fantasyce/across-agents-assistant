from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

from .autopilot_client import AutopilotClient


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="across-agents-assistant-autopilot-workflow-adapter")
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--loop-spec", required=True)
    args = parser.parse_args(argv)

    try:
        task = _json_env("ACROSS_TASK_JSON")
        subtask = _json_env("ACROSS_SUBTASK_JSON")
        project_root = Path(str(task.get("project_root") or os.getcwd())).expanduser().resolve(strict=True)
        if not project_root.is_dir():
            raise ValueError("task project_root must be an existing directory")
        metadata = task.get("metadata") if isinstance(task.get("metadata"), Mapping) else {}
        host_metadata = metadata.get("host_metadata") if isinstance(metadata.get("host_metadata"), Mapping) else {}
        execution_plan_source = host_metadata.get("execution_plan", metadata.get("execution_plan"))
        execution_plan = execution_plan_source if isinstance(execution_plan_source, Mapping) else {}
        deliverables = _safe_deliverables(
            project_root,
            execution_plan.get("deliverables") or [subtask.get("path") or "across-results/report.md"],
        )
        goal = str(task.get("goal") or "").strip()
        if not goal:
            raise ValueError("task goal is required")
        task_id = str(task.get("task_id") or "unknown")
        result = AutopilotClient().run(
            args.loop_spec,
            trigger=f"aaa-task:{task_id}:workflow:{args.workflow_id}",
            project_root=project_root,
        )
        _write_deliverables(
            project_root=project_root,
            deliverables=deliverables,
            workflow_id=args.workflow_id,
            loop_spec=args.loop_spec,
            goal=goal,
            result=result,
        )
        status = _run_status(result)
        payload = {
            "workflow_id": args.workflow_id,
            "loop_spec_id": args.loop_spec,
            "status": status,
            "deliverables": [str(path.relative_to(project_root)) for path in deliverables],
            "run_id": _run_id(result),
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if status == "completed" else 1
    except Exception as exc:
        print(f"Across Autopilot workflow execution failed: {exc}", file=sys.stderr)
        return 1


def _safe_deliverables(project_root: Path, values: Any) -> list[Path]:
    paths: list[Path] = []
    for raw in values if isinstance(values, list) else []:
        relative = Path(str(raw or "").strip())
        if not str(relative) or relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe workflow deliverable path: {raw}")
        resolved = (project_root / relative).resolve()
        if resolved == project_root or project_root not in resolved.parents:
            raise ValueError(f"workflow deliverable escapes project root: {raw}")
        if resolved not in paths:
            paths.append(resolved)
    if not paths:
        raise ValueError("workflow execution plan has no safe deliverables")
    return paths


def _write_deliverables(
    *,
    project_root: Path,
    deliverables: list[Path],
    workflow_id: str,
    loop_spec: str,
    goal: str,
    result: Mapping[str, Any],
) -> None:
    envelope = {
        "schema_version": "across-aaa-workflow-result/1.0",
        "workflow_id": workflow_id,
        "loop_spec_id": loop_spec,
        "goal": goal,
        "status": _run_status(result),
        "run_id": _run_id(result),
        "result": dict(result),
    }
    for path in deliverables:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".md":
            content = _markdown_result(envelope)
        elif "memory" in path.name.lower():
            evidence = result.get("evidence") if isinstance(result.get("evidence"), Mapping) else {}
            content = json.dumps(
                {
                    "schema_version": "across-pending-workflow-memory/1.0",
                    "workflow_id": workflow_id,
                    "run_id": envelope["run_id"],
                    "status": "pending_review",
                    "memory": evidence.get("memory") or result.get("memory") or {},
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ) + "\n"
        else:
            content = json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        path.write_text(content, encoding="utf-8")


def _markdown_result(envelope: Mapping[str, Any]) -> str:
    result = envelope.get("result") if isinstance(envelope.get("result"), Mapping) else {}
    evidence = result.get("evidence") if isinstance(result.get("evidence"), Mapping) else {}
    outputs = evidence.get("outputs") or result.get("outputs") or []
    risks = evidence.get("risks") or result.get("risks") or []
    lines = [
        f"# {envelope.get('workflow_id')} result",
        "",
        f"- Status: {envelope.get('status')}",
        f"- Run: {envelope.get('run_id') or 'not reported'}",
        f"- LoopSpec: {envelope.get('loop_spec_id')}",
        "",
        "## Goal",
        "",
        str(envelope.get("goal") or ""),
        "",
        "## Evidence summary",
        "",
        f"- Outputs: {len(outputs) if isinstance(outputs, list) else 0}",
        f"- Attention items: {len(risks) if isinstance(risks, list) else 0}",
        "- Full structured evidence is included in the adjacent JSON artifact.",
        "",
    ]
    return "\n".join(lines)


def _run_status(result: Mapping[str, Any]) -> str:
    run = result.get("run") if isinstance(result.get("run"), Mapping) else {}
    evidence = result.get("evidence") if isinstance(result.get("evidence"), Mapping) else {}
    return str(run.get("status") or evidence.get("status") or result.get("status") or "unknown").strip().lower()


def _run_id(result: Mapping[str, Any]) -> str | None:
    run = result.get("run") if isinstance(result.get("run"), Mapping) else {}
    evidence = result.get("evidence") if isinstance(result.get("evidence"), Mapping) else {}
    value = run.get("run_id") or evidence.get("run_id") or result.get("run_id")
    return str(value) if value else None


def _json_env(name: str) -> dict[str, Any]:
    raw = os.environ.get(name)
    if not raw:
        raise ValueError(f"{name} is required")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be a JSON object")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
