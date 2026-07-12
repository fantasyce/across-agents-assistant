import SwiftUI
import AppKit

extension MainPanelView {
    func openSettings(_ tab: SettingsHubTab) {
        showTaskOrchestration = false
        activeSettingsHubTab = tab
    }

    func refreshHumanReviewQueue() {
        Task {
            async let lifecycleLoad: Void = pluginLifecycleViewModel.load(probe: true)
            if memorySearchViewModel.hasSearched {
                await memorySearchViewModel.search(projectRoot: operationalProjectPath)
            }
            _ = await lifecycleLoad
        }
    }

    func openHumanReviewItem(_ item: HumanReviewSignal) {
        let source = item.source.lowercased()
        let identifier = item.id.lowercased()

        switch item.kind {
        case .pendingMemory:
            selectedOperationsSurface = .humanReview
        case .pluginRepair:
            openSettings(.plugins)
        case .permission:
            if source == "assist" || identifier.hasPrefix("permission-") {
                selectedOperationsSurface = .assist
            } else {
                openSettings(.tools)
            }
        case .promotion, .blockingGate, .manualGate, .skippedGate:
            if source.contains("agent loop")
                || (identifier.hasPrefix("promotion-") && !identifier.contains("release"))
            {
                activeSettingsHubTab = nil
                showTaskOrchestration = false
                selectedOperationsSurface = .autopilot
            } else {
                activeSettingsHubTab = nil
                showTaskOrchestration = true
            }
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
        guard !viewModel.isProcessing, !isProtectedTaskRunning else { return }
        let text = viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        let attachedFiles = viewModel.attachedFiles
        guard !text.isEmpty || !attachedFiles.isEmpty else { return }
        guard canUseAgentFeatures else { return }

        if appPreferences.automaticDeliveryProtection {
            submitProtectedTask(text: text, attachedFiles: attachedFiles)
            return
        }

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

    private func submitProtectedTask(text: String, attachedFiles: [AttachedFile]) {
        guard let projectPath = operationalProjectPath, !projectPath.isEmpty else {
            viewModel.showErrorMessage(appPreferences.text("work.projectRequired"))
            return
        }
        guard !taskOrchestrationViewModel.isOrchestratorPluginUnavailable else {
            viewModel.showErrorMessage(appPreferences.text("work.setupRequired"))
            return
        }

        let ownerAgent = settingsViewModel.preferredAgentId(current: viewModel.selectedAgentId) ?? "auto"
        let description = protectedTaskDescription(text: text, attachedFiles: attachedFiles)

        Task {
            if let errorMessage = await settingsViewModel.ensureTaskSubmissionReady(ownerAgentId: ownerAgent) {
                await MainActor.run { handleChatEnsureFailure(errorMessage) }
                return
            }

            await MainActor.run {
                taskOrchestrationViewModel.submitTask(
                    description: description,
                    taskTypes: ["functional", "artifact"],
                    ownerAgent: ownerAgent,
                    projectDir: projectPath,
                    strictDependency: true
                )
                viewModel.inputText = ""
                viewModel.attachedFiles = []
            }
        }
    }

    private func protectedTaskDescription(text: String, attachedFiles: [AttachedFile]) -> String {
        let goal = text.isEmpty ? appPreferences.text("work.attachmentOnlyGoal") : text
        guard !attachedFiles.isEmpty else { return goal }
        let references = attachedFiles.map { "- \($0.name): \($0.path)" }.joined(separator: "\n")
        return "\(goal)\n\n\(appPreferences.text("work.references"))\n\(references)"
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
