#!/usr/bin/env python3
"""Reject prohibited third-party product language from Across-owned surfaces."""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


_TERM_PARTS = ("goal", "board")
_PROHIBITED_TERM = re.compile(
    rf"{_TERM_PARTS[0]}[\s_-]*{_TERM_PARTS[1]}",
    re.IGNORECASE,
)
_SKIPPED_DIRECTORIES = {
    ".build",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}
_BINARY_SUFFIXES = {
    ".a",
    ".bin",
    ".db",
    ".dylib",
    ".gif",
    ".gz",
    ".icns",
    ".ico",
    ".jpeg",
    ".jpg",
    ".o",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".webp",
    ".zip",
}


@dataclass(frozen=True, order=True)
class LanguageViolation:
    root_label: str
    path: Path
    kind: str
    line: int | None = None


class LanguageScanError(RuntimeError):
    """Raised when a release-blocking source scan cannot inspect every file."""


def _iter_files(root: Path) -> Iterable[Path]:
    def fail_closed(error: OSError) -> None:
        raise LanguageScanError("could not traverse a source tree") from error

    for current_root, directories, filenames in os.walk(root, onerror=fail_closed):
        directories[:] = sorted(
            directory
            for directory in directories
            if directory not in _SKIPPED_DIRECTORIES
        )
        current = Path(current_root)
        for filename in sorted(filenames):
            yield current / filename


def _content_violation(
    root_label: str,
    relative_path: Path,
    path: Path,
) -> LanguageViolation | None:
    if path.suffix.lower() in _BINARY_SUFFIXES or path.is_symlink():
        return None
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise LanguageScanError("could not inspect a source file") from error
    if b"\x00" in payload:
        return None
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise LanguageScanError("could not decode a source file") from error
    for line_number, line in enumerate(text.splitlines(), start=1):
        if _PROHIBITED_TERM.search(line):
            return LanguageViolation(
                root_label=root_label,
                path=relative_path,
                kind="content",
                line=line_number,
            )
    return None


def find_language_violations(roots: Sequence[Path]) -> list[LanguageViolation]:
    violations: list[LanguageViolation] = []
    for raw_root in roots:
        root = raw_root.resolve()
        if not root.is_dir():
            raise ValueError("scan root is not a directory")
        root_label = root.name
        for path in _iter_files(root):
            relative_path = path.relative_to(root)
            if _PROHIBITED_TERM.search(str(relative_path)):
                violations.append(
                    LanguageViolation(
                        root_label=root_label,
                        path=relative_path,
                        kind="path",
                    )
                )
            content_violation = _content_violation(root_label, relative_path, path)
            if content_violation is not None:
                violations.append(content_violation)
    return sorted(violations)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check Across-owned source trees for prohibited product language."
    )
    parser.add_argument("roots", nargs="+", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        violations = find_language_violations(args.roots)
    except (LanguageScanError, ValueError) as error:
        print(f"Product language check could not complete: {error}.")
        return 2
    if not violations:
        print("Product language check passed.")
        return 0
    for violation in violations:
        location = f":{violation.line}" if violation.line is not None else ""
        print(
            f"{violation.root_label}:{violation.path}{location} "
            f"[{violation.kind}]"
        )
    print("Prohibited third-party product language found.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
