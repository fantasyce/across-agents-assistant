#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/across-swift-behavior.XXXXXX")"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "== AppPreferencesBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/AppPreferencesBehavior.swift \
  macOS-Client/Sources/Models/AppPreferences.swift \
  macOS-Client/Sources/Models/PluginLifecycleModels.swift \
  macOS-Client/Sources/ViewModels/PluginLifecycleViewModel.swift \
  -o "$TMP_DIR/AppPreferencesBehavior"
"$TMP_DIR/AppPreferencesBehavior"

echo "== PluginLifecycleBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/PluginLifecycleBehavior.swift \
  macOS-Client/Sources/Models/PluginLifecycleModels.swift \
  macOS-Client/Sources/ViewModels/PluginLifecycleViewModel.swift \
  -o "$TMP_DIR/PluginLifecycleBehavior"
"$TMP_DIR/PluginLifecycleBehavior"

echo "Swift behavior checks passed."
