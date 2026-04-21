import Cocoa
import ApplicationServices

struct ContextPack: Codable {
    var frontmost_app: String?
    var window_title: String?
    var clipboard_text: String?
}

class ContextEngine {
    static let shared = ContextEngine()
    
    var explicitlySavedPreviousApp: NSRunningApplication?
    
    private init() {
        // We no longer rely on NSWorkspace deactivation notifications because they are asynchronous
        // and can cause race conditions. We also don't rely on bundleIdentifier which can be nil in SPM builds.
    }
    
    func collectTier1Context() -> ContextPack {
        var pack = ContextPack()
        
        let workspace = NSWorkspace.shared
        var activeApp: NSRunningApplication? = nil
        
        let myPID = ProcessInfo.processInfo.processIdentifier
        
        if let frontApp = workspace.frontmostApplication {
            if frontApp.processIdentifier != myPID {
                activeApp = frontApp
            } else {
                // If we are frontmost, use the app that was active right before we were summoned
                activeApp = explicitlySavedPreviousApp
            }
        }
        
        if let targetApp = activeApp {
            pack.frontmost_app = targetApp.localizedName
            
            // Get window title (Optional Tier 1)
            pack.window_title = getWindowTitle(for: targetApp)
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
