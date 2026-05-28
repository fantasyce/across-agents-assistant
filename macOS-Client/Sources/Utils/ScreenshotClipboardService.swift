import AppKit
import Foundation

enum ScreenshotClipboardShortcut {
    static let keyDescription = "S"
    static let modifiers: NSEvent.ModifierFlags = [.command, .shift]
}

enum ScreenshotClipboardStartResult: Equatable {
    case started
    case alreadyRunning
    case permissionRequired
    case launchFailed
}

final class ScreenshotClipboardService {
    static let shared = ScreenshotClipboardService()
    static let screencapturePath = "/usr/sbin/screencapture"
    static let interactiveSelectionClipboardArguments = ["-i", "-J", "selection", "-c", "-x"]

    private var activeProcess: Process?

    private init() {}

    static func makeInteractiveSelectionClipboardProcess() -> Process {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: screencapturePath)
        process.arguments = interactiveSelectionClipboardArguments
        return process
    }

    @discardableResult
    func copyInteractiveWindowSelectionToClipboard() -> ScreenshotClipboardStartResult {
        guard activeProcess == nil else {
            return .alreadyRunning
        }

        guard ContextEngine.shared.hasScreenRecordingPermission() else {
            ContextEngine.shared.triggerScreenRecordingPrompt()
            return .permissionRequired
        }

        NSApp.hide(nil)

        let process = Self.makeInteractiveSelectionClipboardProcess()
        activeProcess = process
        process.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                self?.activeProcess = nil
            }
        }

        do {
            try process.run()
            return .started
        } catch {
            activeProcess = nil
            return .launchFailed
        }
    }
}
