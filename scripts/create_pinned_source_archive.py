#!/usr/bin/env python3
"""Fetch one exact Git commit and publish a verified deterministic archive."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from create_deterministic_source_archive import create_archive


_COMMIT = re.compile(r"[0-9a-f]{40}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_ARCHIVE_ROOT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
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


def prepare_archive(
    *,
    repository: str,
    commit: str,
    output: Path,
    archive_root: str,
    expected_sha256: str,
    excluded_names: set[str],
) -> None:
    if not repository or _COMMIT.fullmatch(commit) is None:
        raise PinnedArchiveError
    if _SHA256.fullmatch(expected_sha256) is None:
        raise PinnedArchiveError
    if _ARCHIVE_ROOT.fullmatch(archive_root) is None:
        raise PinnedArchiveError

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_file() and _digest(output) == expected_sha256:
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
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args()
    try:
        prepare_archive(
            repository=args.repository,
            commit=args.commit,
            output=args.output,
            archive_root=args.archive_root,
            expected_sha256=args.expected_sha256,
            excluded_names=set(args.exclude),
        )
    except PinnedArchiveError:
        print(_PUBLIC_ERROR, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
