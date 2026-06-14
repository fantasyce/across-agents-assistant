#!/usr/bin/env bash

set -euo pipefail

PACKAGE_DIR="${1:-macOS-Client}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PACKAGE_PATH="$PROJECT_ROOT/$PACKAGE_DIR"

if ! command -v swift >/dev/null; then
  echo "Swift toolchain is not available in PATH." >&2
  exit 1
fi

if [[ ! -f "$PACKAGE_PATH/Package.swift" || ! -f "$PACKAGE_PATH/Package.resolved" ]]; then
  echo "Package.swift and Package.resolved are both required under $PACKAGE_PATH." >&2
  exit 1
fi

echo "Verifying Swift lockfile consistency in $PACKAGE_PATH"
(cd "$PACKAGE_PATH" && swift package resolve)

if ! git -C "$PACKAGE_PATH" diff --quiet -- Package.resolved; then
  echo "Package.resolved is not aligned with Package.swift."
  echo "Please run 'swift package resolve --package-path macOS-Client' and commit updated Package.resolved."
  git -C "$PACKAGE_PATH" diff -- Package.resolved
  exit 1
fi

echo "Package.resolved matches Package.swift."
