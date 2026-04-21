import Cocoa
import ApplicationServices

struct ContextPack: Codable {
    var frontmost_app: String?
    var window_title: String?
    var clipboard_text: String?
}

class ContextEngine {
    static let shared = ContextEngine()
    
    func collectTier1Context() -> ContextPack {
        var pack = ContextPack()
        
        // 1. Get Frontmost App
        // Because our own app (AcrossAgentsAssistantClient) becomes frontmost when the user clicks the UI or uses the global hotkey,
        // we need to find the FIRST active app that is NOT us.
        let workspace = NSWorkspace.shared
        let runningApps = workspace.runningApplications
        
        // Filter out our own bundle identifier
        let myBundleId = Bundle.main.bundleIdentifier ?? "com.example.AcrossAgentsAssistantClient"
        
        // Find the active app that isn't us
        var activeApp: NSRunningApplication? = nil
        
        // In macOS, the currently active app is usually the one with isActive == true.
        // But if our app just stole focus, we need to look at the z-order or rely on AppleScript/Accessibility.
        // A reliable heuristic without complex Accessibility permissions is to get the frontmost app from NSWorkspace.frontmostApplication
        // If it's us, we might need a workaround. For MVP, let's try to filter by activation policy and find the most recently active normal app.
        
        if let frontApp = workspace.frontmostApplication {
            if frontApp.bundleIdentifier != myBundleId {
                activeApp = frontApp
            } else {
                // If we are frontmost, try to find the next active regular app
                // runningApplications is not strictly z-ordered, but we can look for apps that are unhidden and regular
                activeApp = runningApps.filter { 
                    $0.activationPolicy == .regular && 
                    $0.bundleIdentifier != myBundleId &&
                    !$0.isHidden
                }.first
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
