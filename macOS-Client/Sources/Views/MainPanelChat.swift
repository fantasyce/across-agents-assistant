import SwiftUI

extension MainPanelView {
    @ViewBuilder
    var centerArea: some View {
        if selectedOperationsSurface == .assist {
            assistCenterArea
        } else {
            OperationsWorkbenchShell(
                selection: $selectedOperationsSurface,
                workspaces: workspaceOperationsViewModel,
                qualityGate: qualityGateViewModel,
                memorySearch: memorySearchViewModel,
                lifecycle: pluginLifecycleViewModel,
                tasks: taskOrchestrationViewModel,
                preferences: appPreferences,
                activeProjectPath: viewModel.activeProjectPath,
                reviewSnapshot: humanReviewSnapshot,
                reviewIsLoading: pluginLifecycleViewModel.isLoadingPlugins
                    || pluginLifecycleViewModel.isLoadingMemories
                    || workspaceOperationsViewModel.isLoading,
                reviewErrorMessage: pluginLifecycleViewModel.errorMessage ?? workspaceOperationsViewModel.errorMessage,
                onOpenTaskOrchestration: {
                    activeSettingsHubTab = nil
                    showTaskOrchestration = true
                },
                onOpenPluginCenter: { openSettings(.plugins) },
                onRefreshReviewQueue: refreshHumanReviewQueue,
                onOpenReviewItem: openHumanReviewItem
            )
        }
    }

    var assistCenterArea: some View {
        VStack(spacing: 0) {
            headerBar
                .zIndex(1_000)
            Divider().opacity(0.5)
                .zIndex(900)
            contentArea
                .zIndex(0)
            inputArea
                .zIndex(1_000)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(bgColor)
        .contentShape(Rectangle())
        .onTapGesture { NSApp.keyWindow?.makeFirstResponder(nil) }
    }


    @ViewBuilder
    var contentArea: some View {
        switch settingsViewModel.availabilityBootstrapState {
        case .loading:
            availabilityLoadingView
        case .empty:
            onboardingView
        case .ready:
            messageList
        }
    }

    var messageList: some View {
        ScrollView {
            ScrollViewReader { proxy in
                VStack(alignment: .leading, spacing: 16) {
                    if viewModel.hasMoreHistory {
                        HStack {
                            Spacer()
                            if viewModel.isLoadingMoreHistory {
                                ProgressView().controlSize(.small)
                                    .padding(.vertical, 4)
                            } else {
                                Button(action: { viewModel.loadMoreHistory() }) {
                                    Text(appPreferences.text("chat.loadEarlier"))
                                        .font(.system(size: 11))
                                        .foregroundColor(.accentColor)
                                }
                                .buttonStyle(.plain)
                                .padding(.vertical, 4)
                            }
                            Spacer()
                        }
                        .id("load-more")
                    }
                    ForEach(viewModel.messages) { message in
                        LegacyMessageBubble(
                            message: message, userBgColor: userMsgBgColor,
                            userTextColor: userMsgTextColor, agentTextColor: agentMsgTextColor
                        ).id(message.id)
                    }
                    if viewModel.isProcessing {
                        HStack(spacing: 6) {
                            ProgressView().controlSize(.small)
                            Text(appPreferences.text("chat.thinking")).font(.system(size: 11)).foregroundColor(.secondary)
                            Spacer()
                        }
                        .offset(x: -2).padding(.vertical, 4)
                        .id("processing")
                    }
                }
                .padding(EdgeInsets(top: 8, leading: 24, bottom: 24, trailing: 24))
                .onChange(of: viewModel.messages.count) {
                    if !viewModel.isLoadingMoreHistory {
                        if let lastId = viewModel.messages.last?.id {
                            proxy.scrollTo(lastId, anchor: .bottom)
                        }
                    }
                }
                .onChange(of: viewModel.isProcessing) {
                    if viewModel.isProcessing { proxy.scrollTo("processing", anchor: .bottom) }
                }
            }
        }
    }

    var inputArea: some View {
        HStack(alignment: .center, spacing: 10) {
            InteractiveIconButton(
                systemName: "camera.viewfinder",
                help: appPreferences.text("screenshot.ocr"),
                iconSize: MainPanelIconMetrics.glyphSize,
                foregroundColor: .secondary,
                frameSize: MainPanelIconMetrics.buttonSize,
                isDisabled: !canUseAgentFeatures
            ) {
                viewModel.requestManualScreenshot()
            }

            InteractiveIconButton(
                systemName: "photo.badge.plus",
                help: appPreferences.text("screenshot.attach"),
                iconSize: MainPanelIconMetrics.glyphSize,
                foregroundColor: .secondary,
                frameSize: MainPanelIconMetrics.buttonSize,
                isDisabled: !canUseAgentFeatures
            ) {
                viewModel.requestScreenshotAttachment()
            }

            InteractiveIconButton(
                systemName: "plus",
                help: appPreferences.text("attachment.addFiles"),
                iconSize: MainPanelIconMetrics.glyphSize,
                foregroundColor: .secondary,
                frameSize: MainPanelIconMetrics.buttonSize,
                isDisabled: !canUseAgentFeatures
            ) {
                viewModel.requestFileAttachment()
            }

            VStack(alignment: .leading, spacing: 6) {
                if let notice = viewModel.transientInputNotice {
                    Text(notice)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                        .transition(.opacity)
                }
                if !viewModel.attachedFiles.isEmpty {
                    inputAttachmentShelf
                }
                HStack {
                    ZStack(alignment: .topLeading) {
                        MacEditorView(
                            text: $viewModel.inputText, attachedFiles: $viewModel.attachedFiles,
                            onSubmit: { if viewModel.pendingApproval == nil { submit() } },
                            onNavigateHistory: { up in viewModel.navigateHistory(up: up) },
                            textColor: NSColor(textColor)
                        ).disabled(viewModel.pendingApproval != nil || !canUseAgentFeatures)
                        if viewModel.inputText.isEmpty {
                            Text(inputPlaceholder)
                                .font(.system(size: 13)).foregroundColor(.secondary.opacity(0.5))
                                .padding(.leading, 4).padding(.top, 2).allowsHitTesting(false)
                        }
                    }
                    .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(.vertical, 6).padding(.horizontal, 8)
            .background(Color.black.opacity(0.05)).cornerRadius(14)
            .frame(minHeight: 32, alignment: .center)

            if viewModel.isProcessing {
                Button(action: { viewModel.cancelGeneration() }) {
                    Image(systemName: "stop.circle.fill")
                        .font(.system(size: 14)).foregroundColor(accentColor)
                        .frame(width: 32, height: 32)
                        .background(Color.black.opacity(0.05)).cornerRadius(6)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(Text(appPreferences.text("chat.stop")))
                .help(appPreferences.text("chat.stop"))
            } else {
                Button(action: submit) {
                    Image(systemName: "paperplane.fill")
                        .font(.system(size: 14))
                        .foregroundColor(canSubmitInput ? accentColor : .secondary)
                        .frame(width: 32, height: 32)
                        .background(Color.black.opacity(0.05)).cornerRadius(6)
                }
                .buttonStyle(.plain)
                .disabled(!canSubmitInput)
                .accessibilityLabel(Text(appPreferences.text("chat.send")))
                .help(appPreferences.text("chat.send"))
            }
        }
        .padding(EdgeInsets(top: 12, leading: 24, bottom: 16, trailing: 24))
        .background(bgColor)
    }

    var inputAttachmentShelf: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(viewModel.attachedFiles) { file in
                    InputAttachmentPreview(file: file) {
                        removeAttachedFile(file)
                    }
                }
            }
            .padding(.vertical, 2)
        }
        .frame(height: 62)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

}
