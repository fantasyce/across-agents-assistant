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
        if let frontApp = NSWorkspace.shared.frontmostApplication {
            pack.frontmost_app = frontApp.localizedName
            
            // 2. Try to get Window Title using Accessibility API
            let appElement = AXUIElementCreateApplication(frontApp.processIdentifier)
            var focusedWindow: CFTypeRef?
            if AXUIElementCopyAttributeValue(appElement, kAXFocusedWindowAttribute as CFString, &focusedWindow) == .success {
                let windowElement = focusedWindow as! AXUIElement
                var title: CFTypeRef?
                if AXUIElementCopyAttributeValue(windowElement, kAXTitleAttribute as CFString, &title) == .success {
                    pack.window_title = title as? String
                }
            }
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
}
