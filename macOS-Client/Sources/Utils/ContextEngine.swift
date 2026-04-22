import Cocoa
import ApplicationServices
import Vision

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
    
    func performScreenshotAndOCR(completion: @escaping (String?) -> Void) {
        let tempPath = NSTemporaryDirectory() + "temp_screenshot.png"
        
        let process = Process()
        process.launchPath = "/usr/sbin/screencapture"
        process.arguments = ["-i", "-x", tempPath]
        
        process.terminationHandler = { _ in
            let fileURL = URL(fileURLWithPath: tempPath)
            
            // Check if file exists (user might have cancelled)
            if !FileManager.default.fileExists(atPath: tempPath) {
                DispatchQueue.main.async { completion(nil) }
                return
            }
            
            let request = VNRecognizeTextRequest { request, error in
                if let error = error {
                    print("OCR Error: \(error)")
                    DispatchQueue.main.async { completion(nil) }
                    return
                }
                
                guard let observations = request.results as? [VNRecognizedTextObservation] else {
                    DispatchQueue.main.async { completion(nil) }
                    return
                }
                
                let text = observations.compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
                
                // Cleanup
                try? FileManager.default.removeItem(at: fileURL)
                
                DispatchQueue.main.async {
                    completion(text.isEmpty ? nil : text)
                }
            }
            
            request.recognitionLevel = .accurate
            request.recognitionLanguages = ["zh-Hans", "en-US"]
            request.usesLanguageCorrection = true
            
            let handler = VNImageRequestHandler(url: fileURL, options: [:])
            do {
                try handler.perform([request])
            } catch {
                print("Failed to perform OCR: \(error)")
                DispatchQueue.main.async { completion(nil) }
            }
        }
        
        process.launch()
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
