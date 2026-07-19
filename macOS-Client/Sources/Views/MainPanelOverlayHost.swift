import AppKit
import SwiftUI

struct MainPanelOverlayHost: View {
    @ObservedObject var session: SessionViewModel
    @ObservedObject var settings: SettingsViewModel
    @ObservedObject var preferences: AppPreferences

    let settingsTab: SettingsHubTab?
    let onCloseSettings: () -> Void

    var body: some View {
        Group {
            if let settingsTab {
                SettingsHubView(
                    settingsViewModel: settings,
                    preferences: preferences,
                    selectedTab: settingsTab,
                    onClose: onCloseSettings
                )
            }
            if let request = session.pendingApproval {
                ZStack {
                    Color.black.opacity(0.4).ignoresSafeArea()
                    ApprovalDialogView(request: request) { decision in
                        session.submitDecision(decision: decision)
                    }
                }
            }
            if session.showPermissionAlert {
                permissionAlert
            }
        }
    }

    private var permissionAlert: some View {
        ZStack {
            Color.black.opacity(0.4).ignoresSafeArea()
            VStack(spacing: 20) {
                Image(systemName: "lock.shield.fill")
                    .font(.system(size: 40))
                    .foregroundStyle(StatusPalette.tone(for: "attention").foreground)
                    .accessibilityHidden(true)

                Text(preferences.text("accessibility.title"))
                    .font(.headline)

                Text(preferences.text("accessibility.message"))
                    .font(.subheadline)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)

                HStack(spacing: 16) {
                    Button(preferences.text("system.cancel")) {
                        session.showPermissionAlert = false
                        session.submitDecision(decision: "reject")
                    }
                    .buttonStyle(.bordered)
                    .accessibilityLabel(Text(preferences.text("system.cancel")))

                    Button(preferences.text("system.openSystemSettings")) {
                        session.openAccessibilitySettings()
                    }
                    .buttonStyle(.borderedProminent)
                    .accessibilityLabel(Text(preferences.text("system.openSystemSettings")))
                }
            }
            .padding(30)
            .frame(width: 350)
            .background(VisualEffectView())
            .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.cardCornerRadius))
            .shadow(color: Color.black.opacity(0.2), radius: 20, x: 0, y: 10)
        }
    }
}

final class OverlayCmdWInterceptView: NSView {
    var onClose: (() -> Void)?
    private var monitor: Any?
    var isActive = false {
        didSet {
            guard isActive != oldValue else { return }
            if isActive {
                monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
                    if event.modifierFlags.contains(.command) && event.keyCode == 13 {
                        self?.onClose?()
                        return nil
                    }
                    return event
                }
            } else if let monitor {
                NSEvent.removeMonitor(monitor)
                self.monitor = nil
            }
        }
    }

    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    deinit {
        if let monitor { NSEvent.removeMonitor(monitor) }
    }
}

struct OverlayCmdWInterceptor: NSViewRepresentable {
    let isActive: Bool
    let onClose: () -> Void

    func makeNSView(context: Context) -> OverlayCmdWInterceptView {
        let view = OverlayCmdWInterceptView()
        view.onClose = onClose
        return view
    }

    func updateNSView(_ nsView: OverlayCmdWInterceptView, context: Context) {
        nsView.onClose = onClose
        nsView.isActive = isActive
    }
}
