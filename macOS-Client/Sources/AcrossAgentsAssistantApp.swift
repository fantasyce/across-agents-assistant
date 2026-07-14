import AppKit
import SwiftUI

@main
struct AcrossAgentsAssistantApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var viewModel: SessionViewModel
    @StateObject private var settingsViewModel: SettingsViewModel
    @StateObject private var appPreferences: AppPreferences

    init() {
        let sessionViewModel = SessionViewModel()
        let settingsViewModel = SettingsViewModel(bootstrapOnInit: false)
        let appPreferences = AppPreferences()

        _viewModel = StateObject(wrappedValue: sessionViewModel)
        _settingsViewModel = StateObject(wrappedValue: settingsViewModel)
        _appPreferences = StateObject(wrappedValue: appPreferences)

        UnixSocketProtocol.register()
        MainWindowRegistry.shared.registerFallbackWindowFactory {
            let rootView = MainPanelRootView(
                viewModel: sessionViewModel,
                settingsViewModel: settingsViewModel,
                appPreferences: appPreferences
            )
            let controller = NSHostingController(rootView: rootView)
            let window = NSWindow(
                contentRect: NSRect(x: 0, y: 0, width: 1280, height: 800),
                styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
                backing: .buffered,
                defer: false
            )
            window.title = "Across Agents Assistant"
            window.titleVisibility = .hidden
            window.titlebarAppearsTransparent = true
            window.contentViewController = controller
            window.center()
            return window
        }
    }

    var body: some Scene {
        WindowGroup("Across Agents Assistant", id: MainWindowScene.id) {
            MainPanelRootView(
                viewModel: viewModel,
                settingsViewModel: settingsViewModel,
                appPreferences: appPreferences
            )
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 1280, height: 800)
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
                onClose: { NSApplication.shared.keyWindow?.performClose(nil) }
            )
            .environmentObject(appPreferences)
            .frame(minWidth: 1024, idealWidth: 1280, minHeight: 640, idealHeight: 800)
            .onAppear { AppAppearanceController.apply(appPreferences.colorSchemeMode) }
            .onChange(of: appPreferences.colorSchemeMode) {
                AppAppearanceController.apply(appPreferences.colorSchemeMode)
            }
            .overlay(
                TrafficLightHider(resetsRestoredZoomedFrame: false)
                    .frame(width: 0, height: 0)
                    .allowsHitTesting(false)
            )
        }
    }

}

private struct MainPanelRootView: View {
    @ObservedObject var viewModel: SessionViewModel
    @ObservedObject var settingsViewModel: SettingsViewModel
    @ObservedObject var appPreferences: AppPreferences

    var body: some View {
        MainPanelView(viewModel: viewModel)
            .environmentObject(settingsViewModel)
            .environmentObject(appPreferences)
            .frame(minWidth: 1024, idealWidth: 1280, minHeight: 640, idealHeight: 800)
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
