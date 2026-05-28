import AppKit

protocol WindowRepresenting {
    var isVisible: Bool { get }
    var isMiniaturized: Bool { get }

    func makeKeyAndOrderFront()
    func deminiaturize()
}

protocol WindowApplicationControlling {
    associatedtype Window: WindowRepresenting

    var isHidden: Bool { get }
    var windows: [Window] { get }

    func hide()
    func unhide()
    func activate()
    func requestNewWindow()
}

enum WindowVisibilityController {
    static func show<App: WindowApplicationControlling>(_ app: App) {
        if app.isHidden {
            app.unhide()
        }
        showOrRequestWindow(app)
        app.activate()
    }

    static func toggle<App: WindowApplicationControlling>(_ app: App) {
        if app.isHidden {
            show(app)
            return
        }

        if app.windows.contains(where: { $0.isVisible && !$0.isMiniaturized }) {
            app.hide()
            return
        }

        show(app)
    }

    static func closeMainWindow() {
        NSApp.hide(nil)
    }

    private static func showOrRequestWindow<App: WindowApplicationControlling>(_ app: App) {
        if let window = app.windows.first {
            if window.isMiniaturized {
                window.deminiaturize()
            }
            window.makeKeyAndOrderFront()
        } else {
            app.requestNewWindow()
        }
    }
}

struct NSApplicationWindowController: WindowApplicationControlling {
    let app: NSApplication

    var isHidden: Bool {
        app.isHidden
    }

    var windows: [NSWindow] {
        app.windows.filter { $0.canBecomeKey || $0.isVisible || $0.isMiniaturized }
    }

    func hide() {
        app.hide(nil)
    }

    func unhide() {
        app.unhide(nil)
    }

    func activate() {
        app.activate(ignoringOtherApps: true)
    }

    func requestNewWindow() {
        app.sendAction(Selector(("newWindow:")), to: nil, from: nil)
    }
}

extension NSWindow: WindowRepresenting {
    func makeKeyAndOrderFront() {
        makeKeyAndOrderFront(nil)
    }

    func deminiaturize() {
        deminiaturize(nil)
    }
}
