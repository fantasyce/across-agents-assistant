from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


RETENTION_SCHEMA_VERSION = "across-loop-engineering-retention/1.0"


@dataclass(frozen=True)
class RetentionPolicy:
    max_age_days: int = 14
    keep_latest: int = 5
    apply: bool = False
    include_promotion_ready: bool = False
    include_source_mirrors: bool = False
    prune_trigger_queue: bool = False


def build_retention_plan(
    *,
    across_home: str | Path | None = None,
    runtime_home_root: str | Path | None = None,
    policy: RetentionPolicy | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Plan safe cleanup for Loop Engineering candidate/runtime artifacts."""

    policy = policy or RetentionPolicy()
    now = time.time() if now is None else float(now)
    across_root = _across_home(across_home)
    runtime_root = _runtime_home_root(runtime_home_root)
    autopilot_data = across_root / "data" / "across-autopilot"
    categories = [
        ("candidate_workspaces", autopilot_data / "candidate-workspaces", "dir"),
        ("candidate_apps", autopilot_data / "candidate-apps", "dir"),
        ("runs", autopilot_data / "runs", "dir"),
        ("candidate_runtime_homes", runtime_root, "dir"),
    ]
    if policy.include_source_mirrors:
        categories.append(("source_mirrors", autopilot_data / "source-mirrors", "dir"))

    plan_items: list[dict[str, Any]] = []
    for category, root, kind in categories:
        entries = _entries(root)
        entries.sort(key=lambda item: item["mtime"], reverse=True)
        keep_ids = {item["path"] for item in entries[: max(0, policy.keep_latest)]}
        for item in entries:
            age_days = max(0.0, (now - item["mtime"]) / 86400)
            promotion_ready = _promotion_ready(item["path"]) if category == "runs" else False
            action = "keep"
            if promotion_ready and not policy.include_promotion_ready:
                reason = "promotion_ready_protected"
            elif item["path"] in keep_ids:
                reason = "within_keep_latest"
            elif age_days >= policy.max_age_days:
                action = "delete"
                reason = "expired"
            else:
                reason = "within_max_age"
            plan_items.append(
                {
                    "category": category,
                    "kind": kind,
                    "path": str(item["path"]),
                    "name": item["path"].name,
                    "mtime": item["mtime"],
                    "age_days": round(age_days, 3),
                    "promotion_ready": promotion_ready,
                    "action": action,
                    "reason": reason,
                }
            )

    trigger_queue_plan = _trigger_queue_plan(autopilot_data / "trigger-queue.json", policy=policy, now=now)
    return {
        "schema_version": RETENTION_SCHEMA_VERSION,
        "status": "planned",
        "apply": policy.apply,
        "policy": {
            "max_age_days": policy.max_age_days,
            "keep_latest": policy.keep_latest,
            "include_promotion_ready": policy.include_promotion_ready,
            "include_source_mirrors": policy.include_source_mirrors,
            "prune_trigger_queue": policy.prune_trigger_queue,
        },
        "roots": {
            "across_home": str(across_root),
            "autopilot_data": str(autopilot_data),
            "runtime_home_root": str(runtime_root),
        },
        "items": plan_items,
        "trigger_queue": trigger_queue_plan,
        "summary": _summary(plan_items, trigger_queue_plan),
    }


def apply_retention_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Apply a plan created by build_retention_plan after path safety checks."""

    roots = plan.get("roots") or {}
    allowed_roots = [
        Path(roots.get("autopilot_data") or "").expanduser().resolve(),
        Path(roots.get("runtime_home_root") or "").expanduser().resolve(),
    ]
    deleted: list[str] = []
    errors: list[dict[str, str]] = []
    for item in plan.get("items") or []:
        if item.get("action") != "delete":
            continue
        path = Path(str(item.get("path") or "")).expanduser().resolve()
        if not _within_any(path, allowed_roots):
            errors.append({"path": str(path), "error": "path outside retention roots"})
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
            deleted.append(str(path))
        except Exception as exc:  # pragma: no cover - platform-specific filesystem errors
            errors.append({"path": str(path), "error": str(exc)})

    trigger_result = _apply_trigger_queue_plan(plan.get("trigger_queue") or {})
    status = "applied" if not errors and not trigger_result.get("errors") else "partial"
    applied = dict(plan)
    applied["status"] = status
    applied["deleted"] = deleted
    applied["errors"] = errors
    applied["trigger_queue_result"] = trigger_result
    applied["summary"] = {
        **(plan.get("summary") or {}),
        "deleted_count": len(deleted),
        "error_count": len(errors) + len(trigger_result.get("errors") or []),
    }
    return applied


def run_retention(
    *,
    across_home: str | Path | None = None,
    runtime_home_root: str | Path | None = None,
    policy: RetentionPolicy | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    policy = policy or RetentionPolicy()
    plan = build_retention_plan(
        across_home=across_home,
        runtime_home_root=runtime_home_root,
        policy=policy,
        now=now,
    )
    if not policy.apply:
        return plan
    return apply_retention_plan(plan)


def _summary(items: list[dict[str, Any]], trigger_queue: dict[str, Any]) -> dict[str, Any]:
    delete_count = sum(1 for item in items if item.get("action") == "delete")
    keep_count = sum(1 for item in items if item.get("action") == "keep")
    by_category: dict[str, dict[str, int]] = {}
    for item in items:
        category = str(item.get("category") or "unknown")
        by_category.setdefault(category, {"delete": 0, "keep": 0})
        by_category[category][str(item.get("action") or "keep")] += 1
    return {
        "candidate_count": len(items),
        "delete_count": delete_count,
        "keep_count": keep_count,
        "by_category": by_category,
        "trigger_queue_prunable_count": trigger_queue.get("prunable_count", 0),
    }


def _entries(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir():
        return []
    result = []
    for path in sorted(root.iterdir()):
        if path.name.startswith("."):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        result.append({"path": path.resolve(), "mtime": stat.st_mtime})
    return result


def _promotion_ready(run_dir: Path) -> bool:
    evidence_path = run_dir / "evidence.json"
    if not evidence_path.is_file():
        return False
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    candidate = evidence.get("candidate") if isinstance(evidence, dict) else None
    if not isinstance(candidate, dict):
        return False
    package = candidate.get("promotion_package") if isinstance(candidate.get("promotion_package"), dict) else {}
    return bool(candidate.get("promotion_ready") or package.get("promotion_ready"))


def _trigger_queue_plan(path: Path, *, policy: RetentionPolicy, now: float) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "exists": False, "items": [], "prunable_count": 0}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"path": str(path), "exists": True, "error": str(exc), "items": [], "prunable_count": 0}
    items = payload.get("items") if isinstance(payload, dict) else []
    if not isinstance(items, list):
        items = []
    planned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "")
        completed_at = _parse_epoch(item.get("completed_at") or item.get("updated_at") or item.get("claimed_at"))
        age_days = max(0.0, (now - completed_at) / 86400) if completed_at else 0.0
        prunable = status in {"completed", "failed", "cancelled"} and age_days >= policy.max_age_days
        planned.append(
            {
                "trigger_id": item.get("trigger_id"),
                "status": status,
                "age_days": round(age_days, 3),
                "action": "prune" if prunable else "keep",
            }
        )
    return {
        "path": str(path),
        "exists": True,
        "items": planned,
        "prunable_count": sum(1 for item in planned if item["action"] == "prune"),
        "apply": policy.apply and policy.prune_trigger_queue,
    }


def _apply_trigger_queue_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if not plan.get("apply"):
        return {"applied": False, "pruned_count": 0, "errors": []}
    path = Path(str(plan.get("path") or "")).expanduser().resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("items") if isinstance(payload, dict) else []
        prune_ids = {
            item.get("trigger_id")
            for item in plan.get("items") or []
            if item.get("action") == "prune" and item.get("trigger_id")
        }
        kept = [item for item in items if not isinstance(item, dict) or item.get("trigger_id") not in prune_ids]
        payload["items"] = kept
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"applied": True, "pruned_count": len(items) - len(kept), "errors": []}
    except Exception as exc:  # pragma: no cover - platform-specific filesystem errors
        return {"applied": False, "pruned_count": 0, "errors": [{"path": str(path), "error": str(exc)}]}


def _parse_epoch(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        from datetime import datetime

        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _across_home(value: str | Path | None = None) -> Path:
    raw = value or os.environ.get("ACROSS_HOME") or (Path.home() / ".across")
    return Path(raw).expanduser().resolve()


def _runtime_home_root(value: str | Path | None = None) -> Path:
    raw = value or os.environ.get("ACROSS_CANDIDATE_HOME_ROOT") or (Path.home() / ".across" / "c")
    return Path(raw).expanduser().resolve()


def _within_any(path: Path, roots: Iterable[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="loop-engineering-retention")
    parser.add_argument("--across-home")
    parser.add_argument("--runtime-home-root")
    parser.add_argument("--max-age-days", type=int, default=14)
    parser.add_argument("--keep-latest", type=int, default=5)
    parser.add_argument("--include-promotion-ready", action="store_true")
    parser.add_argument("--include-source-mirrors", action="store_true")
    parser.add_argument("--prune-trigger-queue", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    payload = run_retention(
        across_home=args.across_home,
        runtime_home_root=args.runtime_home_root,
        policy=RetentionPolicy(
            max_age_days=args.max_age_days,
            keep_latest=args.keep_latest,
            apply=args.apply,
            include_promotion_ready=args.include_promotion_ready,
            include_source_mirrors=args.include_source_mirrors,
            prune_trigger_queue=args.prune_trigger_queue,
        ),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload.get("status") in {"planned", "applied"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
