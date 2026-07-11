import SwiftUI

extension MainPanelView {
    var headerBar: some View {
        HStack {
            Text(currentAgentTitle)
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(textColor)
            Spacer()
            HStack(spacing: 12) {
                InteractiveIconButton(systemName: "mic", help: appPreferences.text("toolbar.voiceInput"), iconSize: MainPanelIconMetrics.glyphSize, frameSize: MainPanelIconMetrics.buttonSize) {}
                InteractiveIconButton(
                    systemName: isContinuousMode ? "waveform.circle.fill" : "waveform",
                    help: isContinuousMode ? appPreferences.text("toolbar.continuous.disable") : appPreferences.text("toolbar.continuous.enable"),
                    iconSize: MainPanelIconMetrics.glyphSize,
                    foregroundColor: isContinuousMode ? .blue : .secondary,
                    frameSize: MainPanelIconMetrics.buttonSize
                ) {
                    isContinuousMode.toggle()
                }
                InteractiveIconButton(
                    systemName: viewModel.isMuted ? "speaker.slash.fill" : "speaker.wave.2",
                    help: viewModel.isMuted ? appPreferences.text("toolbar.unmute") : appPreferences.text("toolbar.mute"),
                    iconSize: MainPanelIconMetrics.glyphSize,
                    foregroundColor: viewModel.isMuted ? .red : .secondary,
                    frameSize: MainPanelIconMetrics.buttonSize
                ) {
                    viewModel.isMuted.toggle()
                }
                InteractiveIconButton(systemName: "doc.on.clipboard", help: appPreferences.text("toolbar.copyConversation"), iconSize: MainPanelIconMetrics.glyphSize, frameSize: MainPanelIconMetrics.buttonSize) {
                    viewModel.copyFullConversation()
                }
                InteractiveIconButton(
                    systemName: "list.bullet.rectangle",
                    help: taskEntryDisabled ? appPreferences.text("toolbar.tasks.disabled") : appPreferences.text("toolbar.tasks"),
                    iconSize: MainPanelIconMetrics.glyphSize,
                    foregroundColor: .gray,
                    frameSize: MainPanelIconMetrics.buttonSize,
                    isDisabled: taskEntryDisabled
                ) {
                    activeSettingsHubTab = nil
                    showTaskOrchestration = true
                }
                InteractiveIconButton(systemName: "point.3.connected.trianglepath.dotted", help: appPreferences.text("toolbar.workbench"), iconSize: MainPanelIconMetrics.glyphSize, foregroundColor: .gray, frameSize: MainPanelIconMetrics.buttonSize) {
                    showTaskOrchestration = false
                    activeSettingsHubTab = nil
                    selectedOperationsSurface = .workspaces
                }
                InteractiveIconButton(systemName: "cpu", help: appPreferences.text("toolbar.models"), iconSize: MainPanelIconMetrics.glyphSize, foregroundColor: .gray, frameSize: MainPanelIconMetrics.buttonSize) {
                    showTaskOrchestration = false
                    activeSettingsHubTab = .models
                }
                InteractiveIconButton(systemName: "sparkles.rectangle.stack", help: appPreferences.text("toolbar.capabilities"), iconSize: MainPanelIconMetrics.glyphSize, foregroundColor: .gray, frameSize: MainPanelIconMetrics.buttonSize) {
                    showTaskOrchestration = false
                    activeSettingsHubTab = .capabilities
                }
                InteractiveIconButton(systemName: "square.grid.2x2", help: appPreferences.text("toolbar.mcp"), iconSize: MainPanelIconMetrics.glyphSize, foregroundColor: .gray, frameSize: MainPanelIconMetrics.buttonSize) {
                    showTaskOrchestration = false
                    activeSettingsHubTab = .mcp
                }
                InteractiveAssetIconButton(assetName: "ui.plugin-center", fallbackSystemName: "puzzlepiece", help: appPreferences.text("toolbar.plugins"), iconSize: MainPanelIconMetrics.glyphSize, foregroundColor: .gray, frameSize: MainPanelIconMetrics.buttonSize) {
                    showTaskOrchestration = false
                    activeSettingsHubTab = .plugins
                }
                InteractiveIconButton(systemName: "wrench.and.screwdriver.fill", help: appPreferences.text("toolbar.tools"), iconSize: MainPanelIconMetrics.glyphSize, foregroundColor: .gray, frameSize: MainPanelIconMetrics.buttonSize) {
                    showTaskOrchestration = false
                    activeSettingsHubTab = .tools
                }
                InteractiveIconButton(systemName: "gearshape", help: appPreferences.text("toolbar.settings"), iconSize: MainPanelIconMetrics.glyphSize, foregroundColor: .gray, frameSize: MainPanelIconMetrics.buttonSize) {
                    showTaskOrchestration = false
                    activeSettingsHubTab = activeSettingsHubTab == .settings ? nil : .settings
                }
            }
            .font(.system(size: 14))
        }
        .padding(.horizontal, 20)
        .frame(height: 56)
        .background(ZStack { bgColor; WindowDragView().contentShape(Rectangle()) })
    }
}
