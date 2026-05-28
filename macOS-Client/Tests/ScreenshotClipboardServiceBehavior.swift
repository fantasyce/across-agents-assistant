import AppKit

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

@main
struct ScreenshotClipboardServiceBehavior {
    static func main() {
        let shortcutFlags = ScreenshotClipboardShortcut.modifiers
        assert(shortcutFlags.contains(.command), "screenshot shortcut should include Command")
        assert(shortcutFlags.contains(.shift), "screenshot shortcut should include Shift")
        assert(!shortcutFlags.contains(.control), "screenshot shortcut should not include Control")
        assert(ScreenshotClipboardShortcut.keyDescription == "S", "screenshot shortcut key should be S")

        let process = ScreenshotClipboardService.makeInteractiveSelectionClipboardProcess()
        assert(process.executableURL?.path == ScreenshotClipboardService.screencapturePath, "screenshot should use system screencapture")
        assert(process.arguments == ["-i", "-J", "selection", "-c", "-x"], "screenshot should start in area selection mode and copy to clipboard")

        print("ScreenshotClipboardServiceBehavior passed")
    }
}
