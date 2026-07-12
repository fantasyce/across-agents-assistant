import SwiftUI
import AppKit

class TrafficLightHiderView: NSView {
    private var didSetupWindow = false
    var resetsRestoredZoomedFrame = true

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        guard let window = self.window, !didSetupWindow else { return }
        didSetupWindow = true

        window.styleMask.insert(.fullSizeContentView)
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true

        window.standardWindowButton(.closeButton)?.isHidden = true
        window.standardWindowButton(.miniaturizeButton)?.isHidden = true
        window.standardWindowButton(.zoomButton)?.isHidden = true

        // SwiftUI WindowGroup auto-restores saved window frames via UserDefaults.
        // When a previously-zoomed frame is restored, the window opens visually
        // maximized but NSWindow.isZoomed returns false (frame was set directly,
        // not via zoom(_:)). This breaks the zoom toggle because calling zoom(nil)
        // saves the already-maxed frame as the "user state" and then zooms to a
        // standard state that is also maxed — toggling between identical frames.
        // Detect this and reset to default size so zoom(nil) works correctly.
        guard resetsRestoredZoomedFrame,
              let screen = window.screen ?? NSScreen.main
        else { return }
        let screenFrame = screen.visibleFrame
        let isRestoredZoomed = window.frame.width >= screenFrame.width * 0.95
            && window.frame.height >= screenFrame.height * 0.95
        if isRestoredZoomed {
            DispatchQueue.main.async {
                let size = NSSize(
                    width: min(1280, screenFrame.width),
                    height: min(820, screenFrame.height)
                )
                let origin = NSPoint(
                    x: screenFrame.midX - size.width / 2,
                    y: screenFrame.midY - size.height / 2
                )
                window.setFrame(NSRect(origin: origin, size: size), display: true, animate: false)
            }
        }
    }
}

struct TrafficLightHider: NSViewRepresentable {
    var resetsRestoredZoomedFrame = true

    func makeNSView(context: Context) -> TrafficLightHiderView {
        let view = TrafficLightHiderView()
        view.resetsRestoredZoomedFrame = resetsRestoredZoomedFrame
        return view
    }

    func updateNSView(_ nsView: TrafficLightHiderView, context: Context) {
        nsView.resetsRestoredZoomedFrame = resetsRestoredZoomedFrame
    }
}
