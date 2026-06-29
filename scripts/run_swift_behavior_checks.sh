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

echo "== AutopilotWorkbenchBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/AutopilotWorkbenchBehavior.swift \
  macOS-Client/Sources/Models/AutopilotWorkbenchModels.swift \
  -o "$TMP_DIR/AutopilotWorkbenchBehavior"
"$TMP_DIR/AutopilotWorkbenchBehavior"

echo "== SimpleStartWorkflowBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/SimpleStartWorkflowBehavior.swift \
  macOS-Client/Sources/Models/SimpleStartWorkflowModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationCoreModels.swift \
  -o "$TMP_DIR/SimpleStartWorkflowBehavior"
"$TMP_DIR/SimpleStartWorkflowBehavior"

echo "== ReleaseVerificationBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/ReleaseVerificationBehavior.swift \
  macOS-Client/Sources/Models/ReleaseVerificationModels.swift \
  macOS-Client/Sources/Models/ReleaseEvaluationModels.swift \
  macOS-Client/Sources/Models/StartupDiagnosticsModels.swift \
  -o "$TMP_DIR/ReleaseVerificationBehavior"
"$TMP_DIR/ReleaseVerificationBehavior"

echo "Swift behavior checks passed."
