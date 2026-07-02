from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping

from .paths import component_data_home, ecosystem_home


SOURCE_MIRROR_SCHEMA_VERSION = "across-source-mirrors/1.0"
SOURCE_MIRROR_REFRESH_SCHEMA_VERSION = "across-source-mirror-refresh/1.0"

REQUIRED_SOURCE_REPOS = (
    "across-agents-assistant",
    "across-orchestrator",
    "across-context",
    "across-autopilot",
)

SOURCE_INPUT_ENV = {
    "across-agents-assistant": "ACROSS_AGENTS_ASSISTANT_SOURCE_INPUT",
    "across-orchestrator": "ACROSS_ORCHESTRATOR_SOURCE_INPUT",
    "across-context": "ACROSS_CONTEXT_SOURCE_INPUT",
    "across-autopilot": "ACROSS_AUTOPILOT_SOURCE_INPUT",
}

CANDIDATE_SOURCE_SPECS = {
    "aaa-autonomous-self-iteration",
    "aaa-platform-self-repair",
    "aaa-research-driven-self-iteration",
    "aaa-self-iteration-product",
}


class SourceMirrorRefreshError(RuntimeError):
    """Raised when source mirrors cannot be prepared safely."""

    def __init__(self, message: str, *, payload: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.payload = dict(payload or {})


def source_mirror_refresh_required(spec: Any, env: Mapping[str, str] | None = None) -> bool:
    """Return whether a LoopSpec should refresh source mirrors before running."""

    merged = _merged_env(env)
    mode = str(merged.get("ACROSS_AAA_SOURCE_MIRROR_REFRESH") or "auto").strip().lower()
    if mode in {"0", "false", "no", "off", "disabled"}:
        return False
    if mode in {"1", "true", "yes", "on", "always"}:
        return True
    spec_id = _spec_id(spec)
    if spec_id in CANDIDATE_SOURCE_SPECS:
        return True
    if isinstance(spec, Mapping):
        return _spec_requires_candidate_ecosystem(spec)
    spec_path = _maybe_spec_path(spec)
    if spec_path:
        try:
            payload = json.loads(spec_path.read_text(encoding="utf-8"))
        except Exception:
            return False
        return _spec_id(payload) in CANDIDATE_SOURCE_SPECS or _spec_requires_candidate_ecosystem(payload)
    return False


def refresh_source_mirrors(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Refresh product source mirrors from the local A checkouts.

    The mirror is intentionally a copied snapshot rather than a symlink.  B
    candidate workspaces may mutate their copied snapshot while A stays stable
    and outside the loop runtime.
    """

    merged = _merged_env(env)
    if str(merged.get("ACROSS_AAA_SOURCE_MIRROR_REFRESH") or "").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }:
        return {
            "schema_version": SOURCE_MIRROR_REFRESH_SCHEMA_VERSION,
            "status": "skipped",
            "reason": "disabled_by_env",
            "updated_at": _now(),
        }
    sources = _resolve_source_repos(merged)
    roots = _source_mirror_roots(merged)
    refreshed = [_refresh_root(root, sources, merged) for root in roots]
    status = "passed" if all(item.get("status") == "passed" for item in refreshed) else "failed"
    result = {
        "schema_version": SOURCE_MIRROR_REFRESH_SCHEMA_VERSION,
        "status": status,
        "updated_at": _now(),
        "roots": refreshed,
        "repo_count": len(REQUIRED_SOURCE_REPOS),
    }
    if status != "passed":
        raise SourceMirrorRefreshError("Source mirror refresh failed.", payload=result)
    return result


def source_mirror_status(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Return a bounded status view for the primary source mirror root."""

    merged = _merged_env(env)
    root = _primary_source_mirror_root(merged)
    manifest_path = root / "manifest.json"
    manifest = _read_json(manifest_path)
    sources = _resolve_source_repos(merged, strict=False)
    manifest_by_id = {
        str(item.get("id")): dict(item)
        for item in manifest.get("repos", [])
        if isinstance(item, Mapping) and item.get("id")
    }
    repos: list[dict[str, Any]] = []
    for repo_id in REQUIRED_SOURCE_REPOS:
        source = sources.get(repo_id)
        mirror = root / repo_id
        manifest_repo = manifest_by_id.get(repo_id, {})
        current_head = _git(["rev-parse", "HEAD"], source, check=False).strip() if source else None
        current_status = _git(["status", "--short", "--untracked-files=all"], source, check=False).strip() if source else ""
        origin_main = _git(["rev-parse", "origin/main"], source, check=False).strip() if source else None
        exact_tag = _git(["describe", "--tags", "--exact-match", "HEAD"], source, check=False).strip() if source else None
        require_origin = str(merged.get("ACROSS_AAA_SOURCE_MIRROR_REQUIRE_ORIGIN_MAIN") or "1").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        release_aligned = bool(not require_origin or (origin_main and origin_main == current_head) or exact_tag)
        manifest_head = str(manifest_repo.get("source_head") or "").strip() or None
        mirror_exists = (mirror / ".git").is_dir() or mirror.is_dir()
        fresh = bool(
            current_head
            and manifest_head
            and current_head == manifest_head
            and mirror_exists
            and not current_status
            and release_aligned
        )
        repos.append(
            {
                "id": repo_id,
                "source": str(source) if source else None,
                "mirror": str(mirror),
                "mirror_exists": mirror_exists,
                "source_head": current_head,
                "source_status": current_status,
                "source_origin_main": origin_main,
                "source_exact_tag": exact_tag,
                "source_release_aligned": release_aligned,
                "manifest_source_head": manifest_head,
                "version": manifest_repo.get("version"),
                "fresh": fresh,
            }
        )
    missing = [item["id"] for item in repos if not item["source"] or not item["mirror_exists"]]
    dirty = [item["id"] for item in repos if item.get("source_status")]
    unaligned = [item["id"] for item in repos if item["source"] and not item.get("source_release_aligned")]
    drifted = [
        item["id"]
        for item in repos
        if item["source"]
        and item["mirror_exists"]
        and item.get("source_head")
        and item.get("manifest_source_head")
        and item["source_head"] != item["manifest_source_head"]
    ]
    status = "passed" if manifest and not missing and not dirty and not unaligned and not drifted else "failed"
    return {
        "schema_version": "across-source-mirror-status/1.0",
        "status": status,
        "root": str(root),
        "manifest_path": str(manifest_path),
        "manifest_created_at": manifest.get("created_at"),
        "missing_repos": missing,
        "dirty_repos": dirty,
        "unaligned_repos": unaligned,
        "drifted_repos": drifted,
        "repos": repos,
        "updated_at": _now(),
    }


def _refresh_root(root: Path, sources: Mapping[str, Path], env: Mapping[str, str]) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    repo_records = []
    for repo_id in REQUIRED_SOURCE_REPOS:
        source = sources[repo_id]
        target = root / repo_id
        source_record = _inspect_source(repo_id, source, env)
        _copy_git_snapshot(repo_id, source, target)
        mirror_head = _git(["rev-parse", "HEAD"], target).strip()
        mirror_status = _git(["status", "--short", "--untracked-files=all"], target).strip()
        repo_records.append(
            {
                **source_record,
                "mirror": str(target),
                "mirror_head": mirror_head,
                "mirror_clean": mirror_status == "",
            }
        )
    manifest = {
        "schema_version": SOURCE_MIRROR_SCHEMA_VERSION,
        "status": "passed",
        "created_at": _now(),
        "source_root": str(_source_root(env) or ""),
        "dest_root": str(root),
        "repos": repo_records,
    }
    _write_json(root / "manifest.json", manifest)
    return {
        "schema_version": SOURCE_MIRROR_REFRESH_SCHEMA_VERSION,
        "status": "passed",
        "root": str(root),
        "manifest_path": str(root / "manifest.json"),
        "repos": repo_records,
    }


def _inspect_source(repo_id: str, source: Path, env: Mapping[str, str]) -> dict[str, Any]:
    if not (source / ".git").is_dir():
        raise SourceMirrorRefreshError(
            f"Source repo is missing or not a git checkout: {source}",
            payload={"repo": repo_id, "source": str(source), "reason": "missing_git_checkout"},
        )
    status = _git(["status", "--short", "--untracked-files=all"], source).strip()
    if status:
        raise SourceMirrorRefreshError(
            f"Source repo is dirty: {repo_id}",
            payload={"repo": repo_id, "source": str(source), "reason": "dirty_source", "status": status[:2000]},
        )
    head = _git(["rev-parse", "HEAD"], source).strip()
    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], source, check=False).strip() or None
    origin_main = _git(["rev-parse", "origin/main"], source, check=False).strip() or None
    require_origin = str(env.get("ACROSS_AAA_SOURCE_MIRROR_REQUIRE_ORIGIN_MAIN") or "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    exact_tag = _git(["describe", "--tags", "--exact-match", "HEAD"], source, check=False).strip() or None
    origin_aligned = bool(origin_main and origin_main == head)
    if require_origin and not origin_aligned and not exact_tag:
        raise SourceMirrorRefreshError(
            f"Source repo is not aligned with origin/main or an exact tag: {repo_id}",
            payload={
                "repo": repo_id,
                "source": str(source),
                "reason": "source_not_release_aligned",
                "head": head,
                "branch": branch,
                "origin_main": origin_main,
                "exact_tag": exact_tag,
            },
        )
    return {
        "id": repo_id,
        "source": str(source),
        "source_head": head,
        "source_branch": branch,
        "source_origin_main": origin_main,
        "source_exact_tag": exact_tag,
        "source_clean": True,
        "source_origin_aligned": origin_aligned,
        "version": _read_version(source),
    }


def _copy_git_snapshot(repo_id: str, source: Path, target: Path) -> None:
    tmp = target.with_name(f"{target.name}.tmp-{os.getpid()}-{int(time.time() * 1000)}")
    backup = target.with_name(f"{target.name}.backup-{os.getpid()}-{int(time.time() * 1000)}")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    files = _git(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], source)
    for rel in files.split("\0"):
        rel = rel.strip()
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            continue
        src = source / rel
        if not src.is_file():
            continue
        dst = tmp / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    _git(["init", "-q"], tmp)
    _git(["add", "."], tmp)
    diff = subprocess.run(["git", "-C", str(tmp), "diff", "--cached", "--quiet"], capture_output=True, text=True)
    if diff.returncode not in {0, 1}:
        raise SourceMirrorRefreshError(
            f"Could not inspect source mirror diff: {repo_id}",
            payload={"repo": repo_id, "stderr": diff.stderr[:2000]},
        )
    if diff.returncode == 1:
        _git(
            [
                "-c",
                "user.name=Across Source Mirror",
                "-c",
                "user.email=source-mirror@example.invalid",
                "commit",
                "-q",
                "-m",
                f"source mirror for {repo_id}",
            ],
            tmp,
        )
    if target.exists():
        target.rename(backup)
    try:
        tmp.rename(target)
    except Exception:
        if backup.exists() and not target.exists():
            backup.rename(target)
        raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)


def _resolve_source_repos(env: Mapping[str, str], *, strict: bool = True) -> dict[str, Path]:
    root = _source_root(env)
    result: dict[str, Path] = {}
    for repo_id in REQUIRED_SOURCE_REPOS:
        explicit = str(env.get(SOURCE_INPUT_ENV[repo_id]) or "").strip()
        source = Path(explicit).expanduser().resolve() if explicit else (root / repo_id if root else None)
        if source and source.exists():
            result[repo_id] = source
        elif strict:
            raise SourceMirrorRefreshError(
                f"Source repo is unavailable: {repo_id}",
                payload={"repo": repo_id, "source": str(source) if source else None, "reason": "source_unavailable"},
            )
    return result


def _source_root(env: Mapping[str, str]) -> Path | None:
    explicit = str(env.get("ACROSS_LOOP_SOURCE_ROOT") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    home_projects = Path(str(env.get("HOME") or Path.home())).expanduser() / "Documents" / "projects"
    if all((home_projects / repo_id).exists() for repo_id in REQUIRED_SOURCE_REPOS):
        return home_projects.resolve()
    try:
        package_projects = Path(__file__).resolve().parents[4]
        if all((package_projects / repo_id).exists() for repo_id in REQUIRED_SOURCE_REPOS):
            return package_projects
    except IndexError:
        return None
    return None


def _primary_source_mirror_root(env: Mapping[str, str]) -> Path:
    explicit = str(env.get("ACROSS_AUTOPILOT_SOURCE_MIRRORS_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return component_data_home("across-autopilot", env=env) / "source-mirrors"


def _source_mirror_roots(env: Mapping[str, str]) -> list[Path]:
    roots = [_primary_source_mirror_root(env)]
    if str(env.get("ACROSS_AAA_REFRESH_LEGACY_SOURCE_MIRRORS") or "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }:
        roots.append(ecosystem_home(env) / "source-mirrors")
    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve())
        if key not in seen:
            deduped.append(root.resolve())
            seen.add(key)
    return deduped


def _spec_id(spec: Any) -> str | None:
    if isinstance(spec, Mapping):
        value = spec.get("id") or spec.get("spec_id")
        return str(value).strip() if value else None
    text = str(spec or "").strip()
    if not text:
        return None
    if text in CANDIDATE_SOURCE_SPECS:
        return text
    path = _maybe_spec_path(text)
    if path:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return _spec_id(payload)
    return text


def _spec_requires_candidate_ecosystem(spec: Mapping[str, Any]) -> bool:
    required = spec.get("required_capabilities") or []
    actions = ((spec.get("actions") or {}).get("allowed") or []) if isinstance(spec.get("actions"), Mapping) else []
    return "action.candidate_ecosystem_acquire" in required or "candidate_ecosystem_acquire" in actions


def _maybe_spec_path(spec: Any) -> Path | None:
    text = str(spec or "").strip()
    if not text or len(text) > 1000:
        return None
    path = Path(text).expanduser()
    return path.resolve() if path.is_file() else None


def _read_version(root: Path) -> str | None:
    candidates = [
        root / "backend" / "pyproject.toml",
        root / "pyproject.toml",
        root / "package.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if path.name == "package.json":
            try:
                value = json.loads(text).get("version")
            except json.JSONDecodeError:
                value = None
            return str(value) if value else None
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("version"):
                _, _, value = stripped.partition("=")
                return value.strip().strip('"') or None
    return None


def _git(args: list[str], cwd: Path, *, check: bool = True) -> str:
    proc = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise SourceMirrorRefreshError(
            f"Git command failed: git -C {cwd} {' '.join(args)}",
            payload={"cwd": str(cwd), "args": args, "stderr": proc.stderr[:2000]},
        )
    if proc.returncode != 0:
        return ""
    return proc.stdout


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}-{int(time.time() * 1000)}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _merged_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    merged = dict(os.environ)
    if env:
        merged.update({str(key): str(value) for key, value in env.items()})
    return merged


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
