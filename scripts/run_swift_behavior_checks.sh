#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/across-swift-behavior.XXXXXX")"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "== FrontendDesignAudit =="
python3 scripts/audit_frontend_design.py

echo "== AppPreferencesBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/AppPreferencesBehavior.swift \
  macOS-Client/Sources/Utils/AppUserDefaults.swift \
  macOS-Client/Tests/StandaloneLocalAppPathsStub.swift \
  macOS-Client/Sources/Models/AppPreferences.swift \
  macOS-Client/Sources/Models/OperationsWorkbenchModels.swift \
  macOS-Client/Sources/Models/PluginLifecycleModels.swift \
  macOS-Client/Sources/Models/ProductCapabilityModels.swift \
  macOS-Client/Sources/Models/AcrossLearningProgressModels.swift \
  macOS-Client/Sources/Models/AcrossVisualResultModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationCoreModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationExecutionModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationQualityModels.swift \
  macOS-Client/Sources/ViewModels/PluginLifecycleViewModel.swift \
  -o "$TMP_DIR/AppPreferencesBehavior"
"$TMP_DIR/AppPreferencesBehavior"

echo "== PluginLifecycleBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/PluginLifecycleBehavior.swift \
  macOS-Client/Tests/StandaloneLocalAppPathsStub.swift \
  macOS-Client/Sources/Models/OperationsWorkbenchModels.swift \
  macOS-Client/Sources/Models/PluginLifecycleModels.swift \
  macOS-Client/Sources/Models/ProductCapabilityModels.swift \
  macOS-Client/Sources/Models/AcrossLearningProgressModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationCoreModels.swift \
  macOS-Client/Sources/ViewModels/PluginLifecycleViewModel.swift \
  -o "$TMP_DIR/PluginLifecycleBehavior"
"$TMP_DIR/PluginLifecycleBehavior"

echo "== AutopilotWorkbenchBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/AutopilotWorkbenchBehavior.swift \
  macOS-Client/Sources/Models/AutopilotWorkbenchModels.swift \
  -o "$TMP_DIR/AutopilotWorkbenchBehavior"
"$TMP_DIR/AutopilotWorkbenchBehavior"

echo "== AgentWorkspaceReadinessBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/AgentWorkspaceReadinessBehavior.swift \
  macOS-Client/Sources/Models/AgentWorkspaceModels.swift \
  macOS-Client/Sources/ViewModels/AgentWorkspaceReadinessViewModel.swift \
  macOS-Client/Sources/Views/AcrossDesignSystem.swift \
  -o "$TMP_DIR/AgentWorkspaceReadinessBehavior"
"$TMP_DIR/AgentWorkspaceReadinessBehavior"

echo "== OperationsWorkbenchBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/OperationsWorkbenchBehavior.swift \
  macOS-Client/Sources/Models/OperationsWorkbenchModels.swift \
  -o "$TMP_DIR/OperationsWorkbenchBehavior"
"$TMP_DIR/OperationsWorkbenchBehavior"

echo "== OperationsLifecycleBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/OperationsLifecycleBehavior.swift \
  macOS-Client/Sources/Models/AgentWorkspaceModels.swift \
  macOS-Client/Sources/Models/AgentWorkspaceOperationsModels.swift \
  macOS-Client/Sources/Models/MemorySearchModels.swift \
  macOS-Client/Sources/Models/OperationsWorkbenchModels.swift \
  macOS-Client/Sources/Models/PluginLifecycleModels.swift \
  macOS-Client/Sources/Models/QualityGateModels.swift \
  macOS-Client/Sources/ViewModels/AgentWorkspaceOperationsViewModel.swift \
  macOS-Client/Sources/ViewModels/MemorySearchViewModel.swift \
  macOS-Client/Sources/ViewModels/QualityGateViewModel.swift \
  -o "$TMP_DIR/OperationsLifecycleBehavior"
"$TMP_DIR/OperationsLifecycleBehavior"

echo "== VNextOperationsBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/VNextOperationsBehavior.swift \
  macOS-Client/Sources/Models/OperationsWorkbenchModels.swift \
  macOS-Client/Sources/Models/AgentWorkspaceModels.swift \
  macOS-Client/Sources/Models/AgentWorkspaceOperationsModels.swift \
  macOS-Client/Sources/Models/QualityGateModels.swift \
  macOS-Client/Sources/Models/PluginLifecycleModels.swift \
  macOS-Client/Sources/Models/MemorySearchModels.swift \
  macOS-Client/Sources/ViewModels/AgentWorkspaceOperationsViewModel.swift \
  macOS-Client/Sources/ViewModels/MemorySearchViewModel.swift \
  -o "$TMP_DIR/VNextOperationsBehavior"
"$TMP_DIR/VNextOperationsBehavior"

echo "== QualityGateRemoteBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/QualityGateRemoteBehavior.swift \
  macOS-Client/Sources/Models/OperationsWorkbenchModels.swift \
  macOS-Client/Sources/Models/QualityGateModels.swift \
  macOS-Client/Sources/ViewModels/QualityGateViewModel.swift \
  -o "$TMP_DIR/QualityGateRemoteBehavior"
"$TMP_DIR/QualityGateRemoteBehavior"

echo "== ReleaseVerificationBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/ReleaseVerificationBehavior.swift \
  macOS-Client/Sources/Models/ReleaseVerificationModels.swift \
  macOS-Client/Sources/Models/ReleaseEvaluationModels.swift \
  macOS-Client/Sources/Models/StartupDiagnosticsModels.swift \
  -o "$TMP_DIR/ReleaseVerificationBehavior"
"$TMP_DIR/ReleaseVerificationBehavior"

echo "== UnifiedWorkStateBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/UnifiedWorkStateBehavior.swift \
  macOS-Client/Sources/Models/OperationsWorkbenchModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationCoreModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationExecutionModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationEventsModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationQualityModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationStateReducers.swift \
  -o "$TMP_DIR/UnifiedWorkStateBehavior"
"$TMP_DIR/UnifiedWorkStateBehavior"

echo "== AppleMinimalUIBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/AppleMinimalUIBehavior.swift \
  -o "$TMP_DIR/AppleMinimalUIBehavior"
"$TMP_DIR/AppleMinimalUIBehavior"

echo "== VisualResultBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/VisualResultBehavior.swift \
  macOS-Client/Sources/Models/AcrossVisualResultModels.swift \
  macOS-Client/Sources/Models/OperationsWorkbenchModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationCoreModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationExecutionModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationQualityModels.swift \
  -o "$TMP_DIR/VisualResultBehavior"
"$TMP_DIR/VisualResultBehavior"

echo "== LearningProgressBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/LearningProgressBehavior.swift \
  macOS-Client/Tests/StandaloneLocalAppPathsStub.swift \
  macOS-Client/Sources/Models/AcrossLearningProgressModels.swift \
  macOS-Client/Sources/Models/OperationsWorkbenchModels.swift \
  macOS-Client/Sources/Models/PluginLifecycleModels.swift \
  macOS-Client/Sources/Models/ProductCapabilityModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationCoreModels.swift \
  -o "$TMP_DIR/LearningProgressBehavior"
"$TMP_DIR/LearningProgressBehavior"

echo "== BeginnerMissionBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/BeginnerMissionBehavior.swift \
  macOS-Client/Sources/ViewModels/BeginnerMissionViewModel.swift \
  macOS-Client/Sources/Models/AcrossVisualResultModels.swift \
  macOS-Client/Sources/Models/OperationsWorkbenchModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationCoreModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationExecutionModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationQualityModels.swift \
  -o "$TMP_DIR/BeginnerMissionBehavior"
"$TMP_DIR/BeginnerMissionBehavior"

echo "== RunTrustContractsBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/RunTrustContractsBehavior.swift \
  macOS-Client/Sources/ViewModels/RunTrustContractsViewModel.swift \
  macOS-Client/Sources/Models/AcrossVisualResultModels.swift \
  macOS-Client/Sources/Models/OperationsWorkbenchModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationCoreModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationExecutionModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationQualityModels.swift \
  -o "$TMP_DIR/RunTrustContractsBehavior"
"$TMP_DIR/RunTrustContractsBehavior"

echo "== SpeechRecognitionBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/SpeechRecognitionBehavior.swift \
  macOS-Client/Sources/Utils/SpeechRecognitionService.swift \
  -framework AVFoundation \
  -o "$TMP_DIR/SpeechRecognitionBehavior"
"$TMP_DIR/SpeechRecognitionBehavior"

echo "== TTSEngineVoiceSelectionBehavior =="
swiftc -parse-as-library \
  macOS-Client/Tests/TTSEngineVoiceSelectionBehavior.swift \
  macOS-Client/Sources/Utils/AppUserDefaults.swift \
  macOS-Client/Tests/StandaloneLocalAppPathsStub.swift \
  macOS-Client/Sources/Models/AppPreferences.swift \
  macOS-Client/Sources/Models/OperationsWorkbenchModels.swift \
  macOS-Client/Sources/Models/PluginLifecycleModels.swift \
  macOS-Client/Sources/Models/ProductCapabilityModels.swift \
  macOS-Client/Sources/Models/AcrossLearningProgressModels.swift \
  macOS-Client/Sources/Models/TaskOrchestrationCoreModels.swift \
  macOS-Client/Sources/ViewModels/PluginLifecycleViewModel.swift \
  macOS-Client/Sources/Utils/TTSEngine.swift \
  -o "$TMP_DIR/TTSEngineVoiceSelectionBehavior"
"$TMP_DIR/TTSEngineVoiceSelectionBehavior"

echo "Swift behavior checks passed."
