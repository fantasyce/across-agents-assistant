#!/usr/bin/env python3
"""Fetch one exact Git commit and publish a verified deterministic archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import subprocess
import sys
import tarfile
import tempfile

from create_deterministic_source_archive import create_archive


_COMMIT = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_ARCHIVE_ROOT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+-]*")
_PUBLIC_ERROR = "ERROR: pinned source archive preparation failed"


class PinnedArchiveError(RuntimeError):
    pass


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _run(arguments: list[str]) -> str:
    try:
        completed = subprocess.run(
            arguments,
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PinnedArchiveError from exc
    return completed.stdout.strip()


def _validated_version_path(version_file: str) -> PurePosixPath:
    candidate = PurePosixPath(version_file)
    if candidate.is_absolute() or not candidate.parts or any(part in {"", ".", ".."} for part in candidate.parts):
        raise PinnedArchiveError
    if candidate.name not in {"package.json", "pyproject.toml"}:
        raise PinnedArchiveError
    return candidate


def _version_from_bytes(payload: bytes, filename: str) -> str:
    try:
        if filename == "package.json":
            parsed = json.loads(payload.decode("utf-8"))
            version = parsed.get("version") if isinstance(parsed, dict) else None
        else:
            text = payload.decode("utf-8")
            project = re.search(r"(?ms)^\[project\][ \t]*$\n(.*?)(?=^\[|\Z)", text)
            match = (
                re.search(r'(?m)^version[ \t]*=[ \t]*"([^"]+)"[ \t]*$', project.group(1))
                if project is not None
                else None
            )
            version = match.group(1) if match is not None else None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PinnedArchiveError from exc
    if type(version) is not str or _VERSION.fullmatch(version) is None:
        raise PinnedArchiveError
    return version


def _checkout_version(checkout: Path, version_file: PurePosixPath) -> str:
    metadata = checkout.joinpath(*version_file.parts)
    try:
        if not metadata.is_file() or metadata.stat().st_size > 1024 * 1024:
            raise PinnedArchiveError
        return _version_from_bytes(metadata.read_bytes(), version_file.name)
    except OSError as exc:
        raise PinnedArchiveError from exc


def _archive_version(archive_path: Path, archive_root: str, version_file: PurePosixPath) -> str:
    member_name = str(PurePosixPath(archive_root) / version_file)
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            member = archive.getmember(member_name)
            if not member.isfile() or member.size > 1024 * 1024:
                raise PinnedArchiveError
            handle = archive.extractfile(member)
            if handle is None:
                raise PinnedArchiveError
            return _version_from_bytes(handle.read(), version_file.name)
    except (OSError, KeyError, tarfile.TarError) as exc:
        raise PinnedArchiveError from exc


def prepare_archive(
    *,
    repository: str,
    commit: str,
    output: Path,
    archive_root: str,
    expected_sha256: str,
    version_file: str,
    expected_version: str,
    excluded_names: set[str],
) -> None:
    if not repository or _COMMIT.fullmatch(commit) is None:
        raise PinnedArchiveError
    if _SHA256.fullmatch(expected_sha256) is None:
        raise PinnedArchiveError
    if _ARCHIVE_ROOT.fullmatch(archive_root) is None:
        raise PinnedArchiveError
    if _VERSION.fullmatch(expected_version) is None:
        raise PinnedArchiveError
    validated_version_file = _validated_version_path(version_file)

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_file() and _digest(output) == expected_sha256:
        if _archive_version(output, archive_root, validated_version_file) != expected_version:
            raise PinnedArchiveError
        return

    with tempfile.TemporaryDirectory(prefix=".pinned-source-", dir=output.parent) as temporary:
        temporary_root = Path(temporary)
        checkout = temporary_root / "checkout"
        checkout.mkdir()
        _run(["git", "init", "-q", str(checkout)])
        _run(
            [
                "git",
                "-C",
                str(checkout),
                "fetch",
                "--quiet",
                "--depth=1",
                "--no-tags",
                repository,
                commit,
            ]
        )
        resolved = _run(["git", "-C", str(checkout), "rev-parse", "FETCH_HEAD"])
        if resolved != commit:
            raise PinnedArchiveError
        _run(["git", "-C", str(checkout), "checkout", "--quiet", "--detach", commit])
        if _checkout_version(checkout, validated_version_file) != expected_version:
            raise PinnedArchiveError

        candidate = temporary_root / "candidate.tar.gz"
        create_archive(checkout, candidate, excluded_names, archive_root)
        if _digest(candidate) != expected_sha256:
            raise PinnedArchiveError
        os.replace(candidate, output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive-root", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--version-file", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args()
    try:
        prepare_archive(
            repository=args.repository,
            commit=args.commit,
            output=args.output,
            archive_root=args.archive_root,
            expected_sha256=args.expected_sha256,
            version_file=args.version_file,
            expected_version=args.expected_version,
            excluded_names=set(args.exclude),
        )
    except (PinnedArchiveError, OSError, ValueError):
        print(_PUBLIC_ERROR, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
