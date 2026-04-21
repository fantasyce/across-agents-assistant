import Cocoa
import ApplicationServices

struct ContextPack: Codable {
    var frontmost_app: String?
    var window_title: String?
    var clipboard_text: String?
}

class ContextEngine {
    static let shared = ContextEngine()
    
    private var lastActiveApp: NSRunningApplication?
    private let myBundleId = Bundle.main.bundleIdentifier ?? "com.example.AcrossAgentsAssistantClient"
    
    private init() {
        // Start listening to app deactivation events to keep track of what was active before us
        NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didDeactivateApplicationNotification,
            object: nil,
            queue: .main
        ) { [weak self] notification in
            guard let self = self else { return }
            if let deactivatedApp = notification.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication {
                if deactivatedApp.bundleIdentifier != self.myBundleId {
                    self.lastActiveApp = deactivatedApp
                }
            }
        }
    }
    
    func collectTier1Context() -> ContextPack {
        var pack = ContextPack()
        
        // 1. Get Frontmost App
        let workspace = NSWorkspace.shared
        var activeApp: NSRunningApplication? = nil
        
        if let frontApp = workspace.frontmostApplication {
            if frontApp.bundleIdentifier != myBundleId {
                activeApp = frontApp
            } else {
                // If we are frontmost, use the app that was active right before us
                activeApp = lastActiveApp
            }
        }
        
        if let frontApp = activeApp {
            pack.frontmost_app = frontApp.localizedName
            
            // Get window title (Optional Tier 1)
            pack.window_title = getWindowTitle(for: frontApp)
        }
        
        // 3. Get Clipboard Text
        if let pasteboardString = NSPasteboard.general.string(forType: .string) {
            // Truncate if too long to prevent massive payloads
            if pasteboardString.count > 2000 {
                pack.clipboard_text = String(pasteboardString.prefix(2000)) + "...\n(截断)"
            } else {
                pack.clipboard_text = pasteboardString
            }
        }
        
        return pack
    }

    private func getWindowTitle(for app: NSRunningApplication) -> String? {
        let appElement = AXUIElementCreateApplication(app.processIdentifier)
        var focusedWindow: CFTypeRef?
        if AXUIElementCopyAttributeValue(appElement, kAXFocusedWindowAttribute as CFString, &focusedWindow) == .success {
            let windowElement = focusedWindow as! AXUIElement
            var title: CFTypeRef?
            if AXUIElementCopyAttributeValue(windowElement, kAXTitleAttribute as CFString, &title) == .success {
                return title as? String
            }
        }
        return nil
    }
}
