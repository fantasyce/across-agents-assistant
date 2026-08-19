#!/usr/bin/env python3
"""Create a reproducible source tarball from a local working tree."""

from __future__ import annotations

import argparse
import gzip
import os
from pathlib import Path
import tarfile


def _paths(source: Path, excluded_names: set[str]):
    yield source
    for current, directories, files in os.walk(source, topdown=True, followlinks=False):
        directories[:] = sorted(name for name in directories if name not in excluded_names)
        current_path = Path(current)
        for name in directories:
            yield current_path / name
        for name in sorted(files):
            if name not in excluded_names:
                yield current_path / name


def create_archive(
    source: Path,
    output: Path,
    excluded_names: set[str],
    archive_root: str | None = None,
) -> None:
    source = source.resolve(strict=True)
    root_name = archive_root or source.name
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.unlink(missing_ok=True)

    with temporary.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.GNU_FORMAT) as archive:
                for path in _paths(source, excluded_names):
                    relative = path.relative_to(source)
                    archive_name = root_name if relative == Path(".") else str(Path(root_name) / relative)
                    info = archive.gettarinfo(str(path), arcname=archive_name)
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = 0
                    if info.isfile():
                        with path.open("rb") as handle:
                            archive.addfile(info, handle)
                    else:
                        archive.addfile(info)

    temporary.replace(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive-root")
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args()
    create_archive(args.source, args.output, set(args.exclude), args.archive_root)


if __name__ == "__main__":
    main()
