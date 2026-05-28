import AppKit
import SwiftUI

enum MainWindowScene {
    static let id = "main"
}

final class MainWindowRegistry {
    static let shared = MainWindowRegistry()

    private weak var mainWindow: NSWindow?
    private var openMainWindowAction: (() -> Void)?
    private let closeDelegate = MainWindowCloseDelegate()

    var isTerminating = false

    private init() {}

    func registerOpenMainWindowAction(_ action: @escaping () -> Void) {
        openMainWindowAction = action
    }

    func registerMainWindow(_ window: NSWindow) {
        mainWindow = window
        window.isReleasedWhenClosed = false
        window.delegate = closeDelegate
    }

    func showMainWindow() {
        if NSApp.isHidden {
            NSApp.unhide(nil)
        }

        if let window = reusableMainWindow() {
            show(window)
            return
        }

        requestOpenMainWindow()

        DispatchQueue.main.async { [weak self] in
            if let window = self?.reusableMainWindow() {
                self?.show(window)
            } else {
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

    func requestOpenMainWindow() {
        if let openMainWindowAction {
            openMainWindowAction()
        } else {
            NSApp.sendAction(Selector(("newWindow:")), to: nil, from: nil)
        }
    }

    private func reusableMainWindow() -> NSWindow? {
        if let mainWindow {
            return mainWindow
        }

        return NSApp.windows.first { window in
            window.canBecomeKey || window.isVisible || window.isMiniaturized
        }
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
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
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
