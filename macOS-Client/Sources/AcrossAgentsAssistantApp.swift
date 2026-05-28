import SwiftUI

@main
struct AcrossAgentsAssistantApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var viewModel = SessionViewModel()
    @StateObject private var settingsViewModel = SettingsViewModel(bootstrapOnInit: false)
    @StateObject private var appPreferences = AppPreferences()

    init() {
        UnixSocketProtocol.register()
    }

    var body: some Scene {
        WindowGroup("Across Agents Assistant", id: MainWindowScene.id) {
            MainPanelView(viewModel: viewModel)
                .environmentObject(settingsViewModel)
                .environmentObject(appPreferences)
                .frame(minWidth: 900, idealWidth: 1200, minHeight: 600, idealHeight: 800)
                .background(MainWindowLifecycleBridge())
                .onAppear { AppAppearanceController.apply(appPreferences.colorSchemeMode) }
                .onChange(of: appPreferences.colorSchemeMode) {
                    AppAppearanceController.apply(appPreferences.colorSchemeMode)
                }
                .onReceive(NotificationCenter.default.publisher(for: .selectAgentByIndex)) { notification in
                    if let index = notification.userInfo?["index"] as? Int {
                        selectAgentByIndex(index)
                    }
                }
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 1200, height: 800)
        .commands {
            CommandGroup(after: .appSettings) {
                Button(appPreferences.text("menubar.showWindow")) {
                    MainWindowRegistry.shared.showMainWindow()
                }
            }
        }

        Settings {
            SettingsHubView(
                settingsViewModel: settingsViewModel,
                preferences: appPreferences,
                selectedTab: .settings,
                onClose: nil
            )
            .environmentObject(appPreferences)
            .frame(minWidth: 760, idealWidth: 920, minHeight: 560, idealHeight: 700)
            .onAppear { AppAppearanceController.apply(appPreferences.colorSchemeMode) }
            .onChange(of: appPreferences.colorSchemeMode) {
                AppAppearanceController.apply(appPreferences.colorSchemeMode)
            }
        }
    }

    private func selectAgentByIndex(_ index: Int) {
        guard index >= 0 && index < 9 else { return }

        let availableLocalIds = Set(settingsViewModel.availableLocalAgents.map(\.id))
        let availableCloudIds = Set(settingsViewModel.availableCloudLLMs.map(\.id))

        let localAgents = viewModel.agents.filter { $0.type == .local && availableLocalIds.contains($0.id) }
        let cloudLLMs = viewModel.agents.filter { $0.type == .cloudLLM && availableCloudIds.contains($0.id) }

        var targetId: String?
        if index < localAgents.count {
            targetId = localAgents[index].id
        } else if index < localAgents.count + cloudLLMs.count {
            targetId = cloudLLMs[index - localAgents.count].id
        }

        if let id = targetId {
            viewModel.selectedAgentId = id
        }
    }

}
