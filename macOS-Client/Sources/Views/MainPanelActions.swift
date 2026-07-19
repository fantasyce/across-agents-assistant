import SwiftUI
import AppKit

extension MainPanelView {
    func openSettings(_ tab: SettingsHubTab) {
        activeSettingsHubTab = tab
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
        mcpPluginManager.startAutoConnectAfterCoreReady()
        viewModel.loadInitialDataIfNeeded()
        guard !didLoadProductShell else { return }
        didLoadProductShell = true
        taskOrchestrationViewModel.updateProjectDirectoryFilter(
            viewModel.activeProjectPath,
            reload: false
        )
        taskOrchestrationViewModel.loadTasks()
        Task {
            await pluginLifecycleViewModel.loadForProductShell()
        }
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
            AppUserDefaults.current.set(viewModel.selectedAgentId, forKey: "lastSelectedAgentId")
        } else {
            AppUserDefaults.current.removeObject(forKey: "lastSelectedAgentId")
        }
    }

    func handleChatEnsureFailure(_ message: String) {
        viewModel.showErrorMessage(message)
    }

    func toggleSpeechInput() {
        if speechInput.state.canFinishRecording {
            speechInput.finish(preservingDraft: viewModel.inputText)
            return
        }
        guard !speechInput.state.isActive else { return }

        // Prevent synthesized replies from being captured as fresh user input.
        TTSEngine.shared.stop()
        if speechInput.state.canRetry {
            speechInput.retry(
                existingDraft: viewModel.inputText,
                localeIdentifier: appPreferences.resolvedLocaleIdentifier
            )
        } else {
            speechInput.start(
                existingDraft: viewModel.inputText,
                localeIdentifier: appPreferences.resolvedLocaleIdentifier
            )
        }
    }

    func submit() {
        guard !viewModel.isProcessing, !isProtectedTaskRunning else { return }
        if speechInput.state.isActive {
            speechInput.cancel(preservingDraft: viewModel.inputText)
        }
        let text = viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        let attachedFiles = viewModel.attachedFiles
        guard !text.isEmpty || !attachedFiles.isEmpty else { return }

        if shouldUseInputForBeginnerMission, attachedFiles.isEmpty, !text.isEmpty {
            runBeginnerMission(text)
            return
        }

        if !canUseAgentFeatures {
            guard canUseBeginnerMissionInput, attachedFiles.isEmpty, !text.isEmpty else { return }
            runBeginnerMission(text)
            return
        }

        if workSubmissionMode.usesProtectedDelivery {
            submitProtectedTask(text: text, attachedFiles: attachedFiles)
            return
        }

        submitDirectAgentWork(text: text, attachedFiles: attachedFiles)
    }

    private func submitDirectAgentWork(text: String, attachedFiles: [AttachedFile]) {
        Task {
            if let errorMessage = await settingsViewModel.ensureChatAgentReady(agentId: viewModel.selectedAgentId) {
                await MainActor.run {
                    handleChatEnsureFailure(errorMessage)
                }
                return
            }

            await MainActor.run {
                learningProgressStore.record([
                    AcrossLearningEvent(
                        kind: .agentInteraction,
                        sourceID: "session:\(viewModel.currentSessionId)"
                    )
                ])
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
        let ownerAgent = settingsViewModel.preferredAgentId(current: viewModel.selectedAgentId) ?? "auto"
        let description = protectedTaskDescription(text: text, attachedFiles: attachedFiles)

        Task {
            if let errorMessage = await settingsViewModel.ensureTaskSubmissionReady(ownerAgentId: ownerAgent) {
                await MainActor.run { handleChatEnsureFailure(errorMessage) }
                return
            }

            await MainActor.run {
                learningProgressStore.record([
                    AcrossLearningEvent(
                        kind: .agentInteraction,
                        sourceID: "protected-session:\(viewModel.currentSessionId)"
                    )
                ])
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
