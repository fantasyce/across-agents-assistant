import Cocoa
import SwiftUI
import HotKey

class AppDelegate: NSObject, NSApplicationDelegate {
    var panel: NSPanel!
    var sessionViewModel = SessionViewModel()
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
        
        panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 420, height: 650),
            styleMask: [.titled, .closable, .resizable, .nonactivatingPanel, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        
        panel.center()
        panel.titleVisibility = .hidden
        panel.titlebarAppearsTransparent = true
        panel.isMovableByWindowBackground = true
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.contentView = NSHostingView(rootView: contentView)
        
        // Custom visual effect background
        panel.backgroundColor = .clear
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
}
