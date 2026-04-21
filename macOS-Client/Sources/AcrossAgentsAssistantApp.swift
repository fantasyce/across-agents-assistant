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
        }
        
        MenuBarExtra("Across Agents", systemImage: "sparkles") {
            Button("Toggle Panel (Cmd+Option+Space)") {
                appDelegate.togglePanel()
            }
            .keyboardShortcut(.space, modifiers: [.command, .option])
            
            Divider()
            
            Button("Quit") {
                NSApplication.shared.terminate(nil)
            }
            .keyboardShortcut("q", modifiers: .command)
        }
    }
}
