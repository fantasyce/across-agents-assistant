import AppKit
import SwiftUI

enum MainWindowScene {
    static let id = "main"
}

final class MainWindowRegistry {
    static let shared = MainWindowRegistry()

    private weak var mainWindow: NSWindow?
    private var openMainWindowAction: (() -> Void)?
    private var fallbackWindowFactory: (() -> NSWindow)?
    private var fallbackWindow: NSWindow?
    private let closeDelegate = MainWindowCloseDelegate()

    var isTerminating = false

    private init() {}

    func registerOpenMainWindowAction(_ action: @escaping () -> Void) {
        openMainWindowAction = action
    }

    func registerFallbackWindowFactory(_ factory: @escaping () -> NSWindow) {
        fallbackWindowFactory = factory
    }

    func registerMainWindow(_ window: NSWindow) {
        mainWindow = window
        window.isReleasedWhenClosed = false
        window.delegate = closeDelegate
    }

    func showMainWindow() {
        debugLog("showMainWindow requested windows=\(windowDiagnostics())")
        if NSApp.isHidden {
            NSApp.unhide(nil)
        }

        if let window = reusableMainWindow() {
            debugLog("showMainWindow reusing window title=\(window.title) visible=\(window.isVisible) mini=\(window.isMiniaturized) canKey=\(window.canBecomeKey) hasController=\(window.contentViewController != nil)")
            show(window)
            return
        }

        if let fallbackWindow {
            debugLog("showMainWindow reusing fallback window visible=\(fallbackWindow.isVisible) mini=\(fallbackWindow.isMiniaturized)")
            show(fallbackWindow)
            return
        }

        requestOpenMainWindow()

        DispatchQueue.main.async { [weak self] in
            if let window = self?.reusableMainWindow() {
                self?.debugLog("showMainWindow async reuse title=\(window.title) visible=\(window.isVisible)")
                self?.show(window)
            } else {
                self?.debugLog("showMainWindow async no reusable window; activating app")
                NSApp.activate(ignoringOtherApps: true)
            }
        }
    }

    func toggleMainWindow() {
        if NSApp.isHidden || !hasVisibleMainWindow {
            showMainWindow()
        } else {
            hideMainWindow()
        }
    }

    func hideMainWindow() {
        NSApp.hide(nil)
    }

    func ensureMainWindowIsOnScreen() {
        guard let window = reusableMainWindow(),
              let screen = window.screen ?? NSScreen.main
        else { return }

        let visible = screen.visibleFrame
        let width = min(window.frame.width, visible.width)
        let height = min(window.frame.height, visible.height)
        let x = min(max(window.frame.minX, visible.minX), visible.maxX - width)
        let y = min(max(window.frame.minY, visible.minY), visible.maxY - height)
        let frame = NSRect(x: x, y: y, width: width, height: height)
        if frame != window.frame {
            window.setFrame(frame, display: true, animate: false)
        }
    }

    func requestOpenMainWindow() {
        if let window = reusableMainWindow() {
            debugLog("requestOpenMainWindow reusing window title=\(window.title) visible=\(window.isVisible)")
            show(window)
        } else if let openMainWindowAction {
            debugLog("requestOpenMainWindow using SwiftUI openWindow action")
            openMainWindowAction()
        } else if let fallbackWindow {
            debugLog("requestOpenMainWindow reusing fallback NSWindow")
            show(fallbackWindow)
        } else if let fallbackWindowFactory {
            debugLog("requestOpenMainWindow using fallback NSWindow factory")
            let window = fallbackWindowFactory()
            fallbackWindow = window
            registerMainWindow(window)
            show(window)
        } else {
            debugLog("requestOpenMainWindow sending newWindow action")
            NSApp.sendAction(Selector(("newWindow:")), to: nil, from: nil)
        }
    }

    private func reusableMainWindow() -> NSWindow? {
        if let mainWindow {
            return mainWindow
        }

        return NSApp.windows.first { window in
            isMainWindowCandidate(window)
        }
    }

    private func isMainWindowCandidate(_ window: NSWindow) -> Bool {
        let normalizedTitle = window.title.trimmingCharacters(in: .whitespacesAndNewlines)
        if normalizedTitle == "Across Agents Assistant",
           window.isVisible || window.isMiniaturized || window.contentViewController != nil {
            return true
        }
        guard window.isVisible || window.isMiniaturized else {
            return false
        }
        if window.contentViewController != nil {
            return true
        }
        return normalizedTitle.contains("Across Agents Assistant")
    }

    private var hasVisibleMainWindow: Bool {
        if let mainWindow {
            return mainWindow.isVisible && !mainWindow.isMiniaturized
        }

        return NSApp.windows.contains { window in
            window.isVisible && !window.isMiniaturized
        }
    }

    private func show(_ window: NSWindow) {
        if window.isMiniaturized {
            window.deminiaturize(nil)
        }
        window.collectionBehavior.formUnion([.canJoinAllSpaces, .fullScreenAuxiliary])
        window.level = .normal
        if let screen = NSScreen.main {
            let visible = screen.visibleFrame
            let width = min(max(window.frame.width, 900), visible.width)
            let height = min(max(window.frame.height, 600), visible.height)
            let origin = CGPoint(
                x: visible.midX - width / 2,
                y: visible.midY - height / 2
            )
            window.setFrame(NSRect(origin: origin, size: NSSize(width: width, height: height)), display: true)
        }
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
        window.orderFrontRegardless()
        NSApp.activate(ignoringOtherApps: true)
    }

    private func windowDiagnostics() -> String {
        NSApp.windows.map { window in
            let title = window.title.isEmpty ? "<empty>" : window.title
            return "\(title){visible=\(window.isVisible),mini=\(window.isMiniaturized),canKey=\(window.canBecomeKey),hasController=\(window.contentViewController != nil),frame=\(NSStringFromRect(window.frame))}"
        }.joined(separator: " | ")
    }

    private func debugLog(_ msg: String) {
        let url = LocalAppPaths.logFile("main_window.log")
        if let data = (msg + "\n").data(using: .utf8) {
            if let handle = try? FileHandle(forWritingTo: url) {
                handle.seekToEndOfFile()
                handle.write(data)
                try? handle.close()
            } else {
                try? data.write(to: url)
            }
        }
        print(msg)
    }
}

private final class MainWindowCloseDelegate: NSObject, NSWindowDelegate {
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        if MainWindowRegistry.shared.isTerminating {
            return true
        }

        MainWindowRegistry.shared.hideMainWindow()
        return false
    }
}

struct MainWindowLifecycleBridge: View {
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        MainWindowAccessor { window in
            MainWindowRegistry.shared.registerMainWindow(window)
        }
        .frame(width: 0, height: 0)
        .onAppear {
            let openWindow = openWindow
            MainWindowRegistry.shared.registerOpenMainWindowAction {
                openWindow(id: MainWindowScene.id)
            }
        }
    }
}

private struct MainWindowAccessor: NSViewRepresentable {
    let onResolve: (NSWindow) -> Void

    func makeNSView(context: Context) -> NSView {
        let view = NSView(frame: .zero)
        resolveWindow(from: view)
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        resolveWindow(from: nsView)
    }

    private func resolveWindow(from view: NSView) {
        DispatchQueue.main.async {
            if let window = view.window {
                onResolve(window)
            }
        }
    }
}
