from __future__ import annotations

import json
import os
import signal
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

from . import __version__
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

RELEASE_SOURCE_ENV = {
    "across-agents-assistant": (
        "ACROSS_AGENTS_ASSISTANT_RELEASE_SOURCE_URL",
        "ACROSS_AGENTS_ASSISTANT_RELEASE_SOURCE_REF",
    ),
    "across-orchestrator": (
        "ACROSS_ORCHESTRATOR_RELEASE_SOURCE_URL",
        "ACROSS_ORCHESTRATOR_RELEASE_SOURCE_REF",
    ),
    "across-context": (
        "ACROSS_CONTEXT_RELEASE_SOURCE_URL",
        "ACROSS_CONTEXT_RELEASE_SOURCE_REF",
    ),
    "across-autopilot": (
        "ACROSS_AUTOPILOT_RELEASE_SOURCE_URL",
        "ACROSS_AUTOPILOT_RELEASE_SOURCE_REF",
    ),
}

DEFAULT_RELEASE_SOURCES = {
    "across-agents-assistant": {
        "url": "https://github.com/fantasyce/across-agents-assistant.git",
        "ref": f"v{__version__}",
    },
    "across-orchestrator": {
        "url": "https://github.com/fantasyce/across-orchestrator.git",
        "ref": "v0.7.13",
    },
    "across-context": {
        "url": "https://github.com/fantasyce/across-context.git",
        "ref": "v0.8.8",
    },
    "across-autopilot": {
        "url": "https://github.com/fantasyce/across-autopilot.git",
        "ref": "v0.2.30",
    },
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
    sources = _resolve_source_repos(merged, strict=False)
    source_metadata: dict[str, dict[str, Any]] = {}
    missing = [repo_id for repo_id in REQUIRED_SOURCE_REPOS if repo_id not in sources]
    if missing and not _has_configured_source_input(merged):
        existing = source_mirror_status(merged)
        if existing.get("status") == "passed":
            return {
                "schema_version": SOURCE_MIRROR_REFRESH_SCHEMA_VERSION,
                "status": "passed",
                "reason": "existing_release_mirrors_current",
                "updated_at": _now(),
                "roots": [
                    {
                        "schema_version": SOURCE_MIRROR_REFRESH_SCHEMA_VERSION,
                        "status": "passed",
                        "root": existing.get("root"),
                        "manifest_path": existing.get("manifest_path"),
                        "repos": existing.get("repos", []),
                    }
                ],
                "repo_count": len(REQUIRED_SOURCE_REPOS),
            }
        cached_sources, cached_metadata = _fresh_release_mirror_cache(existing, merged)
        if cached_sources:
            sources = {**cached_sources, **sources}
            source_metadata.update(cached_metadata)
            missing = [repo_id for repo_id in REQUIRED_SOURCE_REPOS if repo_id not in sources]
    if missing:
        with tempfile.TemporaryDirectory(prefix="across-source-mirror-") as tmp_dir:
            cloned, cloned_metadata = _clone_release_sources(missing, merged, Path(tmp_dir))
            sources = {**sources, **cloned}
            source_metadata.update(cloned_metadata)
            roots = _source_mirror_roots(merged)
            refreshed = [_refresh_root(root, sources, merged, source_metadata) for root in roots]
            return _refresh_result(refreshed)
    roots = _source_mirror_roots(merged)
    refreshed = [_refresh_root(root, sources, merged, source_metadata) for root in roots]
    return _refresh_result(refreshed)


def _refresh_result(refreshed: list[dict[str, Any]]) -> dict[str, Any]:
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
        release_source = _release_source_spec(repo_id, merged)
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
        manifest_ref = str(manifest_repo.get("source_ref") or "").strip() or None
        release_ref = str(release_source.get("ref") or "").strip() or None
        mirror_exists = (mirror / ".git").is_dir() or mirror.is_dir()
        if source:
            fresh = bool(
                current_head
                and manifest_head
                and current_head == manifest_head
                and mirror_exists
                and not current_status
                and release_aligned
            )
        else:
            fresh = bool(
                manifest
                and mirror_exists
                and manifest_head
                and manifest_repo.get("source_mode") == "release_source"
                and manifest_ref
                and manifest_ref == release_ref
            )
        repos.append(
            {
                "id": repo_id,
                "source": str(source) if source else None,
                "source_mode": "local_checkout" if source else "release_source",
                "release_source_url": release_source.get("url"),
                "release_source_ref": release_ref,
                "mirror": str(mirror),
                "mirror_exists": mirror_exists,
                "source_head": current_head,
                "source_status": current_status,
                "source_origin_main": origin_main,
                "source_exact_tag": exact_tag,
                "source_release_aligned": release_aligned,
                "manifest_source_head": manifest_head,
                "manifest_source_ref": manifest_ref,
                "version": manifest_repo.get("version"),
                "fresh": fresh,
            }
        )
    missing = [item["id"] for item in repos if not item["mirror_exists"]]
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
    stale = [item["id"] for item in repos if item["mirror_exists"] and not item.get("source") and not item.get("fresh")]
    status = "passed" if manifest and not missing and not dirty and not unaligned and not drifted and not stale else "failed"
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
        "stale_repos": stale,
        "repos": repos,
        "updated_at": _now(),
    }


def _refresh_root(
    root: Path,
    sources: Mapping[str, Path],
    env: Mapping[str, str],
    source_metadata: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    repo_records = []
    metadata = dict(source_metadata or {})
    for repo_id in REQUIRED_SOURCE_REPOS:
        source = sources[repo_id]
        target = root / repo_id
        source_record = _inspect_source(repo_id, source, env, metadata.get(repo_id))
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


def _inspect_source(
    repo_id: str,
    source: Path,
    env: Mapping[str, str],
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = dict(metadata or {})
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
    trusted_release_mirror_cache = _truthy(metadata.get("trusted_release_mirror_cache"))
    if require_origin and not origin_aligned and not exact_tag and not trusted_release_mirror_cache:
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
    source_mode = str(metadata.get("source_mode") or "local_checkout")
    source_value = str(metadata.get("source_url") or source)
    record = {
        "id": repo_id,
        "source": source_value,
        "source_mode": source_mode,
        "source_head": head,
        "source_branch": branch,
        "source_origin_main": origin_main,
        "source_exact_tag": exact_tag,
        "source_ref": str(metadata.get("source_ref") or exact_tag or branch or head),
        "source_clean": True,
        "source_origin_aligned": origin_aligned,
        "version": _read_version(source),
    }
    if metadata.get("source_url"):
        record["source_checkout"] = str(metadata.get("source_checkout") or source)
    return record


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
    if not _allow_implicit_source_root(env):
        return None
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


def _allow_implicit_source_root(env: Mapping[str, str]) -> bool:
    return _truthy(env.get("ACROSS_AAA_ALLOW_IMPLICIT_SOURCE_ROOT")) or _truthy(env.get("ACROSS_AGENTS_DEVELOPER_MODE"))


def _has_configured_source_input(env: Mapping[str, str]) -> bool:
    if str(env.get("ACROSS_LOOP_SOURCE_ROOT") or "").strip():
        return True
    return any(str(env.get(env_key) or "").strip() for env_key in SOURCE_INPUT_ENV.values())


def _clone_release_sources(
    repo_ids: list[str],
    env: Mapping[str, str],
    tmp_root: Path,
) -> tuple[dict[str, Path], dict[str, dict[str, Any]]]:
    sources: dict[str, Path] = {}
    metadata: dict[str, dict[str, Any]] = {}
    for repo_id in repo_ids:
        spec = _release_source_spec(repo_id, env)
        url = str(spec.get("url") or "").strip()
        ref = str(spec.get("ref") or "").strip()
        if not url or not ref:
            raise SourceMirrorRefreshError(
                f"Release source is unavailable: {repo_id}",
                payload={"repo": repo_id, "reason": "release_source_unavailable", "url": url, "ref": ref},
            )
        target = tmp_root / repo_id
        _git_clone(url, ref, target, repo_id, env)
        sources[repo_id] = target
        metadata[repo_id] = {
            "source_mode": "release_source",
            "source_url": url,
            "source_ref": ref,
        }
    return sources, metadata


def _release_source_spec(repo_id: str, env: Mapping[str, str]) -> dict[str, str]:
    default = DEFAULT_RELEASE_SOURCES[repo_id]
    url_env, ref_env = RELEASE_SOURCE_ENV[repo_id]
    return {
        "url": str(env.get(url_env) or default["url"]).strip(),
        "ref": str(env.get(ref_env) or default["ref"]).strip(),
    }


def _fresh_release_mirror_cache(
    status: Mapping[str, Any],
    env: Mapping[str, str],
) -> tuple[dict[str, Path], dict[str, dict[str, Any]]]:
    sources: dict[str, Path] = {}
    metadata: dict[str, dict[str, Any]] = {}
    repos = status.get("repos") if isinstance(status, Mapping) else []
    if not isinstance(repos, list):
        return sources, metadata
    for item in repos:
        if not isinstance(item, Mapping):
            continue
        repo_id = str(item.get("id") or "").strip()
        if repo_id not in REQUIRED_SOURCE_REPOS:
            continue
        release_source = _release_source_spec(repo_id, env)
        release_ref = str(release_source.get("ref") or "").strip()
        mirror = Path(str(item.get("mirror") or "")).expanduser()
        if not (
            item.get("fresh")
            and not item.get("source")
            and item.get("source_mode") == "release_source"
            and item.get("manifest_source_ref") == release_ref
            and mirror.exists()
        ):
            continue
        sources[repo_id] = mirror
        metadata[repo_id] = {
            "source_mode": "release_source",
            "source_url": str(release_source.get("url") or ""),
            "source_ref": release_ref,
            "source_checkout": str(mirror),
            "trusted_release_mirror_cache": "1",
        }
    return sources, metadata


def _git_clone(url: str, ref: str, target: Path, repo_id: str, env: Mapping[str, str]) -> None:
    timeout = _git_clone_timeout_seconds(env)
    base_args = ["clone", "--depth", "1", "--branch", ref, url, str(target)]
    attempts = [
        ("default", base_args),
        ("retry", base_args),
        ("http1_fallback", ["-c", "http.version=HTTP/1.1", *base_args]),
    ]
    failures: list[dict[str, Any]] = []
    for index, (strategy, args) in enumerate(attempts):
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        proc = _run_git(args, Path("/"), timeout=timeout, include_cwd=False)
        if proc.returncode == 0:
            return
        failures.append(
            {
                "strategy": strategy,
                "returncode": proc.returncode,
                "stderr": proc.stderr[:2000],
            }
        )
        if index + 1 < len(attempts):
            time.sleep(min(index + 1, 2))
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    raise SourceMirrorRefreshError(
        f"Could not bootstrap release source: {repo_id}",
        payload={
            "repo": repo_id,
            "reason": "release_source_clone_failed",
            "url": url,
            "ref": ref,
            "stderr": failures[-1]["stderr"] if failures else "",
            "attempts": failures,
        },
    )


def _git_clone_timeout_seconds(env: Mapping[str, str]) -> int:
    raw = str(env.get("ACROSS_AAA_SOURCE_MIRROR_CLONE_TIMEOUT_SECONDS") or "").strip()
    if raw:
        try:
            return max(30, min(int(raw), 900))
        except ValueError:
            pass
    return 180


def _primary_source_mirror_root(env: Mapping[str, str]) -> Path:
    explicit = str(env.get("ACROSS_AUTOPILOT_SOURCE_MIRRORS_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()
    return component_data_home("across-autopilot", env=env) / "source-mirrors"


def _source_mirror_roots(env: Mapping[str, str]) -> list[Path]:
    roots = [_primary_source_mirror_root(env)]
    if str(env.get("ACROSS_AAA_REFRESH_LEGACY_SOURCE_MIRRORS") or "0").strip().lower() not in {
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


def _git(args: list[str], cwd: Path, *, check: bool = True, timeout: int = 30) -> str:
    proc = _run_git(args, cwd, timeout=timeout)
    if check and proc.returncode != 0:
        raise SourceMirrorRefreshError(
            f"Git command failed: git -C {cwd} {' '.join(args)}",
            payload={"cwd": str(cwd), "args": args, "stderr": proc.stderr[:2000]},
        )
    if proc.returncode != 0:
        return ""
    return proc.stdout


def _run_git(args: list[str], cwd: Path, *, timeout: int, include_cwd: bool = True) -> subprocess.CompletedProcess[str]:
    command = ["git", "-C", str(cwd), *args] if include_cwd else ["git", *args]
    proc: subprocess.Popen[str] | None = None
    try:
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_git_env(),
            start_new_session=True,
        )
        stdout, stderr = proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(command, proc.returncode, stdout=stdout, stderr=stderr)
    except subprocess.TimeoutExpired as exc:
        if proc is not None:
            _terminate_process_group(proc, signal.SIGTERM)
            try:
                stdout, stderr = proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                _terminate_process_group(proc, signal.SIGKILL)
                stdout, stderr = proc.communicate()
        else:
            stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return subprocess.CompletedProcess(
            command,
            124,
            stdout=stdout or "",
            stderr=(stderr or "") or f"git command timed out after {timeout}s",
        )


def _terminate_process_group(proc: subprocess.Popen[str], sig: int) -> None:
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        return
    except PermissionError:
        if sig == signal.SIGKILL:
            proc.kill()
        else:
            proc.terminate()


def _git_env() -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", ""),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }
    for key in ("LANG", "LC_ALL", "LC_CTYPE"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    return env


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


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
