import SwiftUI
import AppKit

extension MainPanelView {
    func openSettings(_ tab: SettingsHubTab) {
        showTaskOrchestration = false
        activeSettingsHubTab = tab
    }

    func refreshHumanReviewQueue() {
        Task {
            async let workspaceLoad: Void = workspaceOperationsViewModel.load(
                activeProjectPath: viewModel.activeProjectPath,
                refreshReadiness: true
            )
            async let lifecycleLoad: Void = pluginLifecycleViewModel.load(probe: true)
            taskOrchestrationViewModel.loadReleaseEvaluation()
            if memorySearchViewModel.hasSearched {
                await memorySearchViewModel.search(projectRoot: viewModel.activeProjectPath)
            }
            _ = await (workspaceLoad, lifecycleLoad)
        }
    }

    func openHumanReviewItem(_ item: HumanReviewSignal) {
        switch item.kind {
        case .pendingMemory:
            selectedOperationsSurface = .memory
        case .pluginRepair:
            openSettings(.plugins)
        case .permission:
            openSettings(.tools)
        case .promotion, .blockingGate, .manualGate, .skippedGate:
            selectedOperationsSurface = .qualityGate
        }
    }

    func humanReviewKind(forGateStatus status: String) -> HumanReviewKind? {
        switch StatusPalette.normalized(status) {
        case "blocked", "error", "failed", "failure", "timeout":
            return .blockingGate
        case "manual", "manual_required", "needs_review":
            return .manualGate
        case "skipped":
            return .skippedGate
        default:
            return nil
        }
    }

    func syncSelectedAgentToAvailability() {
        guard settingsViewModel.availabilityBootstrapState == .ready else { return }
        guard let fallback = settingsViewModel.preferredAgentId(current: viewModel.selectedAgentId) else { return }
        if viewModel.selectedAgentId != fallback {
            viewModel.selectedAgentId = fallback
        }
    }

    func loadInitialDataWhenBackendAvailable() {
        guard settingsViewModel.availabilityBootstrapState != .loading else { return }
        viewModel.loadInitialDataIfNeeded()
    }

    func syncPreferencesToSessionViewModel() {
        viewModel.speechPlaybackSettings = SpeechPlaybackSettings(
            autoReadReplies: appPreferences.autoReadReplies,
            voiceSource: appPreferences.voiceSource,
            chosenVoiceIdentifier: appPreferences.chosenVoiceIdentifier,
            fallbackLanguage: appPreferences.resolvedLocaleIdentifier,
            speechRate: appPreferences.speechRate,
            speechVolume: appPreferences.speechVolume
        )
        viewModel.includeActiveAppContext = appPreferences.includeActiveAppContext
        viewModel.shouldRememberSelectedAgent = appPreferences.rememberLastAgent
        viewModel.screenshotOCRPermissionTip = appPreferences.text("screenshot.permission.ocr")
        viewModel.screenshotAttachmentPermissionTip = appPreferences.text("screenshot.permission.attach")
        viewModel.screenshotClipboardPermissionTip = appPreferences.text("screenshot.permission.copy")
        viewModel.screenshotCopiedNotice = appPreferences.text("screenshot.copied")
        viewModel.screenshotCancelledNotice = appPreferences.text("screenshot.cancelled")
        viewModel.screenshotCopyFailedNotice = appPreferences.text("screenshot.copyFailed")
        if appPreferences.rememberLastAgent {
            UserDefaults.standard.set(viewModel.selectedAgentId, forKey: "lastSelectedAgentId")
        } else {
            UserDefaults.standard.removeObject(forKey: "lastSelectedAgentId")
        }
    }

    func handleChatEnsureFailure(_ message: String) {
        viewModel.showErrorMessage(message)
    }

    func submit() {
        guard !viewModel.isProcessing else { return }
        let text = viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        let attachedFiles = viewModel.attachedFiles
        guard !text.isEmpty || !attachedFiles.isEmpty else { return }
        guard canUseAgentFeatures else { return }

        Task {
            if let errorMessage = await settingsViewModel.ensureChatAgentReady(agentId: viewModel.selectedAgentId) {
                await MainActor.run {
                    handleChatEnsureFailure(errorMessage)
                }
                return
            }

            await MainActor.run {
                viewModel.sendMessage(text, attachedFiles: attachedFiles)
                viewModel.inputText = ""
                viewModel.attachedFiles = []
            }
        }
    }

    func removeAttachedFile(_ file: AttachedFile) {
        viewModel.attachedFiles.removeAll { $0.id == file.id }
    }

    func handleSessionClick(_ session: SessionInfo) {
        let flags = NSApp.currentEvent?.modifierFlags ?? []
        if flags.contains(.command) {
            if selectedSessionIds.contains(session.session_id) {
                selectedSessionIds.remove(session.session_id)
            } else {
                selectedSessionIds.insert(session.session_id)
            }
        } else if flags.contains(.shift), let firstId = selectedSessionIds.first,
                  let firstIdx = viewModel.sessions.firstIndex(where: { $0.session_id == firstId }),
                  let clickedIdx = viewModel.sessions.firstIndex(where: { $0.session_id == session.session_id }) {
            let range = min(firstIdx, clickedIdx)...max(firstIdx, clickedIdx)
            for i in range {
                selectedSessionIds.insert(viewModel.sessions[i].session_id)
            }
        } else {
            selectedSessionIds = [session.session_id]
            viewModel.switchToSession(session.session_id)
        }
    }
}

