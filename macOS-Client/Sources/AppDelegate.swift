import Cocoa
import SwiftUI
import HotKey

class CustomPanel: NSPanel {
    override var canBecomeKey: Bool {
        return true
    }
}

class AppDelegate: NSObject, NSApplicationDelegate {
    var panel: CustomPanel!
    lazy var sessionViewModel: SessionViewModel = {
        let vm = SessionViewModel()
        // Bind UI callbacks
        vm.onHidePanel = { [weak self] in self?.hidePanel() }
        vm.onShowPanel = { [weak self] in self?.showPanel() }
        return vm
    }()
    
    private var hotKey: HotKey?
    
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Set to accessory to hide from dock but allow menu bar
        NSApp.setActivationPolicy(.accessory)
        
        // Close the default empty window that SwiftUI might spawn
        if let window = NSApp.windows.first {
            window.close()
        }
        
        setupPanel()
        setupGlobalHotkey()
    }
    
    func setupGlobalHotkey() {
        // Register Option + Space as the global hotkey
        hotKey = HotKey(key: .space, modifiers: [.option])
        
        hotKey?.keyDownHandler = { [weak self] in
            DispatchQueue.main.async {
                self?.togglePanel()
            }
        }
    }
    
    func setupPanel() {
        let contentView = MainPanelView(viewModel: sessionViewModel)
        
        // 1. Create a borderless panel
        panel = CustomPanel(
            contentRect: NSRect(x: 0, y: 0, width: 900, height: 650), // Wider for 3 columns
            styleMask: [
                .borderless,          // Completely frameless, no native title bar at all
                .nonactivatingPanel   // Won't steal focus from other apps
            ],
            backing: .buffered,
            defer: false
        )
        
        // 3. Make the background draggable ONLY via designated areas (SwiftUI WindowDragView)
        panel.isMovableByWindowBackground = false
        
        // 4. Custom visual appearance
        panel.isOpaque = false
        panel.backgroundColor = .clear // Let SwiftUI handle the blur
        panel.hasShadow = true
        panel.isFloatingPanel = true
        panel.level = .floating // Keep on top
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        
        // 5. Set Content View
        panel.contentView = NSHostingView(rootView: contentView)
        
        // 6. Center and Show
        panel.center()
        panel.makeKeyAndOrderFront(nil)
    }
    
    @objc func togglePanel() {
        if panel.isVisible {
            panel.orderOut(nil)
        } else {
            // SNAPSHOT: Before we activate and steal focus, record who the current frontmost app is
            let myPID = ProcessInfo.processInfo.processIdentifier
            if let currentApp = NSWorkspace.shared.frontmostApplication,
               currentApp.processIdentifier != myPID {
                ContextEngine.shared.explicitlySavedPreviousApp = currentApp
            }
            
            panel.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        }
    }
    
    // Add a public method to manually hide the panel from other parts of the app
    func hidePanel() {
        if panel.isVisible {
            panel.orderOut(nil)
        }
    }
    
    // Add a public method to manually show the panel
    func showPanel() {
        if !panel.isVisible {
            panel.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        }
    }
}
