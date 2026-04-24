import Cocoa
import SwiftUI
import HotKey

class CustomWindow: NSWindow {
    override var canBecomeKey: Bool {
        return true
    }
}

class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var panel: CustomWindow!
    lazy var sessionViewModel: SessionViewModel = {
        let vm = SessionViewModel()
        // Bind UI callbacks
        vm.onHidePanel = { [weak self] in self?.hidePanel() }
        vm.onShowPanel = { [weak self] in self?.showPanel() }
        return vm
    }()
    
    private var hotKey: HotKey?
    private var prefsHotKey: HotKey?
    private var backendProcess: Process?
    private var statusItem: NSStatusItem?
    
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Set to regular to show in dock and act as a standard app
        NSApp.setActivationPolicy(.regular)
        
        // Close ALL default windows that SwiftUI spawns (this fixes the blank "dirty" window issue)
        for window in NSApp.windows {
            window.close()
        }
        
        setupMenuBar()
        setupPanel()
        setupGlobalHotkey()
        startBackend()
    }
    
    private func setupMenuBar() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        
        if let button = statusItem?.button {
            button.image = NSImage(systemSymbolName: "sparkles", accessibilityDescription: "Across Agents")
        }
        
        let menu = NSMenu()
        
        menu.addItem(NSMenuItem(title: "Toggle Panel (Option+Space)", action: #selector(togglePanel), keyEquivalent: " "))
        
        menu.addItem(NSMenuItem.separator())
        
        let prefsItem = NSMenuItem(title: "Preferences...", action: #selector(openPreferences), keyEquivalent: "m")
        prefsItem.keyEquivalentModifierMask = [.option]
        menu.addItem(prefsItem)
        
        menu.addItem(NSMenuItem.separator())
        
        menu.addItem(NSMenuItem(title: "Quit", action: #selector(quitApp), keyEquivalent: "q"))
        
        statusItem?.menu = menu
    }
    
    @objc func openPreferences() {
        if sessionViewModel.showMCPPreferences && panel.isVisible {
            // Toggle off if already visible
            sessionViewModel.showMCPPreferences = false
        } else {
            // Toggle on and ensure panel is shown
            sessionViewModel.showMCPPreferences = true
            showPanel()
        }
    }
    
    @objc private func quitApp() {
        NSApplication.shared.terminate(nil)
    }
    
    func applicationWillTerminate(_ notification: Notification) {
        stopBackend()
    }
    
    func startBackend() {
        let bundle = Bundle.main
        // The backend executable will be placed in Contents/Resources/backend
        guard let backendURL = bundle.url(forResource: "backend", withExtension: nil) else {
            print("Backend executable not found in bundle. Assuming development mode (backend runs separately).")
            return
        }
        
        backendProcess = Process()
        backendProcess?.executableURL = backendURL
        backendProcess?.arguments = ["--watch-parent"]
        
        let pipe = Pipe()
        backendProcess?.standardOutput = pipe
        backendProcess?.standardError = pipe
        
        do {
            try backendProcess?.run()
            print("Successfully launched bundled backend (PID: \(backendProcess?.processIdentifier ?? 0)).")
            
            // Read output asynchronously to prevent pipe full and blocking
            pipe.fileHandleForReading.readabilityHandler = { handle in
                let data = handle.availableData
                if let str = String(data: data, encoding: .utf8), !str.isEmpty {
                    print("[Backend] \(str)", terminator: "")
                }
            }
        } catch {
            print("Failed to launch bundled backend: \(error)")
        }
    }
    
    func stopBackend() {
        if let process = backendProcess, process.isRunning {
            process.terminate()
            process.waitUntilExit()
            print("Bundled backend terminated.")
        }
    }
    
    func setupGlobalHotkey() {
        // Register Option + Tab as the global hotkey for main panel
        hotKey = HotKey(key: .tab, modifiers: [.option])
        
        hotKey?.keyDownHandler = { [weak self] in
            DispatchQueue.main.async {
                self?.togglePanel()
            }
        }
        
        // Register Option + M as the global hotkey for MCP preferences
        prefsHotKey = HotKey(key: .m, modifiers: [.option])
        
        prefsHotKey?.keyDownHandler = { [weak self] in
            DispatchQueue.main.async {
                self?.openPreferences()
            }
        }
    }
    
    func setupPanel() {
        let contentView = MainPanelView(viewModel: sessionViewModel)
        
        // 1. Create a borderless window
        panel = CustomWindow(
            contentRect: NSRect(x: 0, y: 0, width: 900, height: 650), // Wider for 3 columns
            styleMask: [
                .titled,              // Required to enable standard resizing and zooming
                .closable,            // Required for standard window behaviors
                .miniaturizable,      // Required for standard window behaviors
                .resizable,           // Enables dragging edges to resize
                .fullSizeContentView  // Extends content into the title bar area
            ],
            backing: .buffered,
            defer: false
        )
        
        // 2. Hide the title and make the titlebar transparent
        panel.titleVisibility = .hidden
        panel.titlebarAppearsTransparent = true
        
        // Let standard window buttons show, or hide them if you prefer a fully custom UI
        // We will keep them shown so it acts like a normal window
        // panel.standardWindowButton(.closeButton)?.isHidden = true
        // panel.standardWindowButton(.miniaturizeButton)?.isHidden = true
        // panel.standardWindowButton(.zoomButton)?.isHidden = true
        
        // 3. Make the background draggable ONLY via designated areas (SwiftUI WindowDragView)
        panel.isMovableByWindowBackground = false
        
        // 4. Custom visual appearance
        panel.isOpaque = false
        panel.backgroundColor = .clear // Let SwiftUI handle the blur
        panel.hasShadow = true
        panel.level = .normal // Normal window level, not floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.delegate = self // Observe window events
        
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
    
    // Auto-hide when the user clicks away (window loses focus)
    // Removed because we want the window to be persistent and act like a normal app
    // func windowDidResignKey(_ notification: Notification) {
    //     if let window = notification.object as? NSWindow, window == panel {
    //         hidePanel()
    //     }
    // }
    
    // Re-open window when clicking dock icon
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag {
            showPanel()
        }
        return true
    }
}
