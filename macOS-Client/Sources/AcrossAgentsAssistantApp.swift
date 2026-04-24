import SwiftUI

@main
struct AcrossAgentsAssistantApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    
    var body: some Scene {
        // Use a hidden WindowGroup to keep SwiftUI happy but prevent default window creation
        WindowGroup {
            EmptyView().frame(width: 0, height: 0)
        }
        .windowStyle(.hiddenTitleBar)
        .commands {
            // Remove standard commands (New Window, etc.)
            CommandGroup(replacing: .newItem) {}
            
            // Add custom settings command to App Menu
            CommandGroup(replacing: .appSettings) {
                Button("Preferences...") {
                    appDelegate.openPreferences()
                }
                // Removed .keyboardShortcut("m", modifiers: .option) to rely on AppDelegate's global HotKey
            }
        }
    }
}
