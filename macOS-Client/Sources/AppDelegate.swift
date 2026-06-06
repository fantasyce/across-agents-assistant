import Cocoa
import HotKey

extension Notification.Name {
    static let selectAgentByIndex = Notification.Name("selectAgentByIndex")
}

class AppDelegate: NSObject, NSApplicationDelegate {
    private var hotKey: HotKey?
    private var backendProcess: Process?
    private var backendRestartAttempts = 0
    private var backendLaunchDate: Date?
    private var intentionalBackendStop = false
    private let maxBackendRestartAttempts = 5
    private let backendRestartDelays: [TimeInterval] = [0.5, 1.0, 2.0, 5.0, 10.0]
    private let backendStableRunThreshold: TimeInterval = 30.0
    private var statusItem: NSStatusItem?
    private var statusShowWindowMenuItem: NSMenuItem?
    private var togglePanelMenuItem: NSMenuItem?
    private var quitMenuItem: NSMenuItem?
    private var agentHotKeys: [HotKey] = []
    private var screenshotHotKey: HotKey?

    static var resolvedBackendPath: String?

    /// Returns the path to the bundled backend executable if it exists (production mode), otherwise nil (development mode).
    static var backendExecutablePath: String? {
        let bundle = Bundle.main
        var backendURL: URL?
        if let url = bundle.url(forResource: "backend", withExtension: nil) {
            backendURL = url
        } else if let resourcesURL = bundle.resourceURL {
            backendURL = resourcesURL.appendingPathComponent("backend")
        }
        guard let url = backendURL else { return nil }
        var isDirectory: ObjCBool = false
        if FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory),
           isDirectory.boolValue {
            backendURL = url.appendingPathComponent("backend")
        }
        if let finalURL = backendURL,
           FileManager.default.fileExists(atPath: finalURL.path) {
            return finalURL.path
        }
        return nil
    }

    override init() {
        super.init()
        UserDefaults.standard.set(false, forKey: "NSQuitAlwaysKeepsWindows")
        debugLog("AppDelegate.init()")
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        debugLog("applicationDidFinishLaunching called")

        NSApp.setActivationPolicy(.regular)
        debugLog("activation policy set")

        NotificationCenter.default.addObserver(
            self,
            selector: #selector(appLanguageDidChange),
            name: .appPreferencesLanguageDidChange,
            object: nil
        )

        setupStatusMenu()
        debugLog("status menu set up")
        startBackend()
        debugLog("startBackend done (sync)")

        DispatchQueue.main.async { [weak self] in
            self?.setupGlobalHotkey()
            self?.debugLog("hotkey setup done")
            self?.showMainWindowIfNeeded()

            NSApp.activate(ignoringOtherApps: true)
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return false
    }

    func application(_ application: NSApplication, shouldSaveApplicationState coder: NSCoder) -> Bool {
        false
    }

    func application(_ application: NSApplication, shouldRestoreApplicationState coder: NSCoder) -> Bool {
        false
    }

    func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
        true
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showMainWindowIfNeeded()
        return true
    }

    private func setupStatusMenu() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)

        configureStatusButton()

        let menu = NSMenu()

        let showItem = NSMenuItem(title: "", action: #selector(showMainWindow), keyEquivalent: "")
        showItem.target = self
        statusShowWindowMenuItem = showItem
        menu.addItem(showItem)

        let toggleItem = NSMenuItem(title: "", action: #selector(toggleAppVisibility), keyEquivalent: "")
        toggleItem.target = self
        togglePanelMenuItem = toggleItem
        menu.addItem(toggleItem)

        menu.addItem(NSMenuItem.separator())

        let quitItem = NSMenuItem(title: "", action: #selector(quitApp), keyEquivalent: "q")
        quitItem.target = self
        quitMenuItem = quitItem
        menu.addItem(quitItem)

        statusItem?.menu = menu
        updateMenuBarText()
    }

    private func configureStatusButton() {
        guard let button = statusItem?.button else { return }
        let tooltip = localizedMenuText("menubar.tooltip")
        button.title = ""
        button.image = statusBarImage(accessibilityDescription: tooltip)
        button.imagePosition = .imageOnly
        button.contentTintColor = nil
        button.toolTip = tooltip
        button.setAccessibilityLabel(tooltip)
    }

    private func statusBarImage(accessibilityDescription: String) -> NSImage? {
        let image = NSImage(size: NSSize(width: 22, height: 18))
        image.lockFocus()

        NSColor.white.withAlphaComponent(0.96).setFill()
        drawSparkle(center: CGPoint(x: 11, y: 9), radius: 6.8)
        drawSparkle(center: CGPoint(x: 17, y: 13.5), radius: 2.5)
        drawSparkle(center: CGPoint(x: 5.5, y: 4.5), radius: 2.0)

        image.unlockFocus()
        image.isTemplate = false
        image.accessibilityDescription = accessibilityDescription
        return image
    }

    private func drawSparkle(center: CGPoint, radius: CGFloat) {
        let inset = radius * 0.28
        let path = NSBezierPath()
        path.move(to: CGPoint(x: center.x, y: center.y + radius))
        path.line(to: CGPoint(x: center.x + inset, y: center.y + inset))
        path.line(to: CGPoint(x: center.x + radius, y: center.y))
        path.line(to: CGPoint(x: center.x + inset, y: center.y - inset))
        path.line(to: CGPoint(x: center.x, y: center.y - radius))
        path.line(to: CGPoint(x: center.x - inset, y: center.y - inset))
        path.line(to: CGPoint(x: center.x - radius, y: center.y))
        path.line(to: CGPoint(x: center.x - inset, y: center.y + inset))
        path.close()
        path.fill()
    }

    @objc private func appLanguageDidChange() {
        updateMenuBarText()
    }

    private func updateMenuBarText() {
        configureStatusButton()
        statusShowWindowMenuItem?.title = localizedMenuText("menubar.showWindow")
        togglePanelMenuItem?.title = localizedMenuText("menubar.togglePanel")
        quitMenuItem?.title = localizedMenuText("menubar.quit")
    }

    private func localizedMenuText(_ key: String) -> String {
        let rawMode = UserDefaults.standard.string(forKey: "preferences.languageMode")
        let mode = rawMode.flatMap(AppLanguageMode.init(rawValue:)) ?? .followSystem
        let localeIdentifier = AppPreferences.resolveLocaleIdentifier(
            mode: mode,
            preferredLanguages: Locale.preferredLanguages
        )
        return AppPreferences.localizedString(key, localeIdentifier: localeIdentifier)
    }

    @MainActor
    @objc private func showMainWindow() {
        MainWindowRegistry.shared.showMainWindow()
    }

    @MainActor
    @objc private func toggleAppVisibility() {
        MainWindowRegistry.shared.toggleMainWindow()
    }

    @objc private func quitApp() {
        NSApplication.shared.terminate(nil)
    }

    func applicationWillTerminate(_ notification: Notification) {
        MainWindowRegistry.shared.isTerminating = true
        stopBackend()
    }

    func debugLog(_ msg: String) {
        let url = LocalAppPaths.logFile("app_delegate.log")
        if let data = (msg + "\n").data(using: .utf8) {
            if let handle = try? FileHandle(forWritingTo: url) {
                handle.seekToEndOfFile()
                handle.write(data)
                handle.closeFile()
            } else {
                try? data.write(to: url)
            }
        }
        print(msg)
    }

    @MainActor
    private func showMainWindowIfNeeded() {
        MainWindowRegistry.shared.showMainWindow()
        debugLog("main window requested windows=\(NSApp.windows.count)")
    }

    static func findBackendProjectDir() -> URL? {
        let fm = FileManager.default

        // 1. Check environment variable
        if let envPath = ProcessInfo.processInfo.environment["ACROSS_AGENTS_BACKEND_DIR"],
           !envPath.isEmpty {
            let url = URL(fileURLWithPath: envPath)
            if fm.fileExists(atPath: url.appendingPathComponent("main.py").path) {
                return url
            }
        }

        // 2. Try to find relative to the executable (development mode)
        // Typical paths:
        //   Build: .../Build/Products/Debug/macOS-Client.app/Contents/MacOS/macOS-Client
        //   Xcode: .../DerivedData/.../Build/Products/Debug/macOS-Client.app/Contents/MacOS/macOS-Client
        if let executablePath = Bundle.main.executableURL {
            var url = executablePath
            // Walk up to find project root (look for macOS-Client or across-agents-assistant)
            for _ in 0..<10 {
                url = url.deletingLastPathComponent()
                let candidate = url.appendingPathComponent("backend")
                if fm.fileExists(atPath: candidate.appendingPathComponent("main.py").path) {
                    return candidate
                }
                // Also check if current dir name indicates project root and backend is sibling
                if url.lastPathComponent == "macOS-Client" || url.lastPathComponent == "across-agents-assistant" {
                    let siblingBackend = url.appendingPathComponent("backend")
                    if fm.fileExists(atPath: siblingBackend.appendingPathComponent("main.py").path) {
                        return siblingBackend
                    }
                }
            }
        }

        // 3. Check if there's a backend directory next to the app bundle
        let bundleURL = Bundle.main.bundleURL
        let siblingBackend = bundleURL.deletingLastPathComponent().appendingPathComponent("backend")
        if fm.fileExists(atPath: siblingBackend.appendingPathComponent("main.py").path) {
            return siblingBackend
        }

        return nil
    }

    private static func pythonEnvironment(for backendProjectDir: URL) -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        let srcPath = backendProjectDir.appendingPathComponent("src").path
        if let existingPath = env["PYTHONPATH"], !existingPath.isEmpty {
            env["PYTHONPATH"] = "\(srcPath):\(existingPath)"
        } else {
            env["PYTHONPATH"] = srcPath
        }
        return env
    }

    private static func backendPythonCanImportRuntime(_ pythonURL: URL, backendProjectDir: URL) -> Bool {
        let process = Process()
        process.executableURL = pythonURL
        process.arguments = ["-c", "import fastapi, uvicorn"]
        process.currentDirectoryURL = backendProjectDir
        process.environment = pythonEnvironment(for: backendProjectDir)
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice

        do {
            try process.run()
            process.waitUntilExit()
            return process.terminationStatus == 0
        } catch {
            return false
        }
    }

    private func configurePythonBackendProcess(_ process: Process, backendProjectDir: URL, label: String) -> Bool {
        let fm = FileManager.default
        let candidates = [
            backendProjectDir.appendingPathComponent(".venv/bin/python3"),
            URL(fileURLWithPath: "/opt/homebrew/bin/python3"),
            URL(fileURLWithPath: "/usr/local/bin/python3"),
            URL(fileURLWithPath: "/usr/bin/python3")
        ]
        guard let pythonURL = candidates.first(where: { candidate in
            fm.fileExists(atPath: candidate.path)
                && Self.backendPythonCanImportRuntime(candidate, backendProjectDir: backendProjectDir)
        }) else {
            debugLog("No Python runtime with FastAPI/Uvicorn found for backend at \(backendProjectDir.path)")
            return false
        }

        let mainPyURL = backendProjectDir.appendingPathComponent("main.py")
        process.executableURL = pythonURL
        process.arguments = ["-u", mainPyURL.path, "--watch-parent"]
        process.currentDirectoryURL = backendProjectDir
        process.environment = Self.pythonEnvironment(for: backendProjectDir)
        Self.resolvedBackendPath = backendProjectDir.path
        debugLog("Launching Python \(label): \(pythonURL.path) from \(backendProjectDir.path)")
        return true
    }

    func startBackend(isRestart: Bool = false) {
        if let process = backendProcess, process.isRunning {
            debugLog("startBackend() skipped; backend already running PID: \(process.processIdentifier)")
            return
        }
        if !isRestart {
            backendRestartAttempts = 0
        }
        intentionalBackendStop = false
        debugLog("startBackend() called restart=\(isRestart)")
        let bundle = Bundle.main
        debugLog("Bundle path: \(bundle.bundlePath)")

        backendProcess = Process()

        if let envDir = ProcessInfo.processInfo.environment["ACROSS_AGENTS_BACKEND_DIR"],
           !envDir.isEmpty {
            let backendProjectDir = URL(fileURLWithPath: envDir)
            if let process = backendProcess,
               !configurePythonBackendProcess(process, backendProjectDir: backendProjectDir, label: "via ENV") {
                return
            }
        } else {
            var backendURL: URL
            if let url = bundle.url(forResource: "backend", withExtension: nil) {
                backendURL = url
            } else if let resourcesURL = bundle.resourceURL {
                backendURL = resourcesURL.appendingPathComponent("backend")
            } else {
                debugLog("Backend not found in bundle. Assuming development mode.")
                return
            }

            var isDirectory: ObjCBool = false
            if FileManager.default.fileExists(atPath: backendURL.path, isDirectory: &isDirectory),
               isDirectory.boolValue {
                backendURL = backendURL.appendingPathComponent("backend")
            }

            guard FileManager.default.fileExists(atPath: backendURL.path) else {
                debugLog("Backend not found at \(backendURL.path). Skipping.")
                return
            }
            debugLog("Backend URL: \(backendURL.path)")

            let isScript: Bool
            if let data = try? Data(contentsOf: backendURL, options: [.alwaysMapped]),
               let header = String(data: data.prefix(2), encoding: .utf8),
               header == "#!" {
                isScript = true
            } else {
                isScript = false
            }

            if isScript {
                guard let backendProjectDir = Self.findBackendProjectDir() else {
                    debugLog("Backend project directory not found, skipping backend launch")
                    return
                }
                if let process = backendProcess,
                   !configurePythonBackendProcess(process, backendProjectDir: backendProjectDir, label: "script backend") {
                    return
                }
            } else {
                backendProcess?.executableURL = backendURL
                backendProcess?.arguments = ["--watch-parent"]
                backendProcess?.environment = ProcessInfo.processInfo.environment
                Self.resolvedBackendPath = backendURL.path
            }
        }

        let outFile = LocalAppPaths.logFile("backend_stdout.log")
        FileManager.default.createFile(atPath: outFile.path, contents: nil)
        if let fh = try? FileHandle(forWritingTo: outFile) {
            fh.truncateFile(atOffset: 0)
            backendProcess?.standardOutput = fh
            backendProcess?.standardError = fh
            debugLog("Backend log: \(outFile.path)")
        }

        backendProcess?.terminationHandler = { [weak self] process in
            DispatchQueue.main.async {
                self?.handleBackendTermination(process)
            }
        }

        do {
            try backendProcess?.run()
            backendLaunchDate = Date()
            debugLog("Launched PID: \(backendProcess?.processIdentifier ?? 0), running: \(backendProcess?.isRunning ?? false)")
        } catch {
            debugLog("Failed to launch backend: \(error)")
            backendProcess = nil
            if isRestart {
                scheduleBackendRestart()
            }
        }
    }

    private func handleBackendTermination(_ process: Process) {
        let pid = process.processIdentifier
        let status = process.terminationStatus
        let reason = process.terminationReason == .exit ? "exit" : "uncaught-signal"
        let runtimeBeforeTermination = backendLaunchDate.map { Date().timeIntervalSince($0) }
        let runtimeDescription = runtimeBeforeTermination.map { String(format: "%.2fs", $0) } ?? "unknown"
        debugLog("Backend terminated PID: \(pid), reason: \(reason), status: \(status), runtime: \(runtimeDescription)")

        if backendProcess?.processIdentifier == pid {
            backendProcess = nil
        }

        if let launchDate = backendLaunchDate,
           Date().timeIntervalSince(launchDate) >= backendStableRunThreshold {
            backendRestartAttempts = 0
        }
        backendLaunchDate = nil

        guard !MainWindowRegistry.shared.isTerminating, !intentionalBackendStop else {
            debugLog("Backend termination was intentional; restart skipped")
            return
        }

        guard Self.shouldRestartBackendAfterTermination(
            reason: process.terminationReason,
            status: status,
            runtime: runtimeBeforeTermination,
            stableRunThreshold: backendStableRunThreshold
        ) else {
            debugLog("Backend exited cleanly; restart skipped")
            return
        }

        scheduleBackendRestart()
    }

    static func shouldRestartBackendAfterTermination(
        reason: Process.TerminationReason,
        status: Int32,
        runtime: TimeInterval?,
        stableRunThreshold: TimeInterval
    ) -> Bool {
        if reason == .exit && status == 0 {
            guard let runtime else { return false }
            return runtime < stableRunThreshold
        }
        return true
    }

    private func scheduleBackendRestart() {
        guard backendRestartAttempts < maxBackendRestartAttempts else {
            debugLog("Backend restart limit reached; giving up until app relaunch")
            return
        }

        let attempt = backendRestartAttempts + 1
        let delay = backendRestartDelays[min(backendRestartAttempts, backendRestartDelays.count - 1)]
        backendRestartAttempts = attempt
        debugLog("Scheduling backend restart attempt \(attempt)/\(maxBackendRestartAttempts) in \(delay)s")

        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
            guard let self else { return }
            guard !MainWindowRegistry.shared.isTerminating, !self.intentionalBackendStop else {
                self.debugLog("Backend restart skipped; app is terminating or stop is intentional")
                return
            }
            self.startBackend(isRestart: true)
        }
    }

    func stopBackend() {
        intentionalBackendStop = true
        if let process = backendProcess, process.isRunning {
            process.terminate()
            // Issue 47: Don't block indefinitely; give backend 2s to shut down gracefully
            let deadline = Date().addingTimeInterval(2.0)
            while process.isRunning && Date() < deadline {
                RunLoop.current.run(until: Date().addingTimeInterval(0.1))
            }
            if process.isRunning {
                Darwin.kill(process.processIdentifier, SIGKILL)
                print("Bundled backend force-killed.")
            } else {
                print("Bundled backend terminated.")
            }
        }
        backendProcess = nil
        backendLaunchDate = nil
    }

    func setupGlobalHotkey() {
        debugLog("setupGlobalHotkey: registering global hotkeys via Carbon...")

        hotKey = HotKey(key: .tab, modifiers: [.option])

        hotKey?.keyDownHandler = { [weak self] in
            DispatchQueue.main.async {
                self?.toggleAppVisibility()
            }
        }
        debugLog("setupGlobalHotkey: Option+Tab registered")

        screenshotHotKey = HotKey(key: .s, modifiers: ScreenshotClipboardShortcut.modifiers)
        screenshotHotKey?.keyDownHandler = {
            DispatchQueue.main.async {
                _ = ScreenshotClipboardService.shared.copyInteractiveWindowSelectionToClipboard()
            }
        }
        debugLog("setupGlobalHotkey: Command+Shift+S registered")

        let numberKeys: [Key] = [.one, .two, .three, .four, .five, .six, .seven, .eight, .nine]
        let modifiers: NSEvent.ModifierFlags = [.option]

        for (index, key) in numberKeys.enumerated() {
            let agentHotKey = HotKey(key: key, modifiers: modifiers)
            let capturedIndex = index
            agentHotKey.keyDownHandler = { [weak self] in
                DispatchQueue.main.async {
                    self?.selectAgentByIndex(capturedIndex)
                }
            }
            agentHotKeys.append(agentHotKey)
        }
        debugLog("setupGlobalHotkey: Option+1~9 registered (\(agentHotKeys.count) keys)")
    }

    func selectAgentByIndex(_ index: Int) {
        guard index >= 0 && index < 9 else { return }
        NotificationCenter.default.post(name: .selectAgentByIndex, object: nil, userInfo: ["index": index])
    }
}
