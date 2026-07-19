import Foundation

enum LocalAppPaths {
    static var acrossRoot: URL {
        RuntimeBoundary.safeAcrossRoot(
            bundledBackendAvailable: AppDelegate.backendExecutablePath != nil
        )
    }

    static var root: URL {
        RuntimeBoundary.safeAppHome(
            bundledBackendAvailable: AppDelegate.backendExecutablePath != nil
        )
    }

    static var logsDir: URL {
        runtimeDir(section: "logs", legacyName: "logs")
    }

    static var runDir: URL {
        runtimeDir(section: "run", legacyName: "run")
    }

    static var tmpDir: URL {
        if hasAllowedAppHomeOverride {
            return subdir("tmp")
        }
        let url = acrossRoot
            .appendingPathComponent("cache", isDirectory: true)
            .appendingPathComponent("across-agents-assistant", isDirectory: true)
            .appendingPathComponent("tmp", isDirectory: true)
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    static var screenshotAttachmentsDir: URL {
        let url = tmpDir.appendingPathComponent("screenshots", isDirectory: true)
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    static var evidenceExportsDir: URL {
        subdir("evidence")
    }

    static var autopilotWorkbenchSnapshotCache: URL {
        let cacheDirectory: URL
        if hasAllowedAppHomeOverride {
            cacheDirectory = subdir("cache")
        } else {
            cacheDirectory = acrossRoot
                .appendingPathComponent("cache", isDirectory: true)
                .appendingPathComponent("across-agents-assistant", isDirectory: true)
            try? FileManager.default.createDirectory(
                at: cacheDirectory,
                withIntermediateDirectories: true
            )
        }
        return cacheDirectory.appendingPathComponent("autopilot-workbench-snapshot.json")
    }

    static var backendSocketPath: String {
        runDir.appendingPathComponent("across-agents.sock").path
    }

    static func logFile(_ name: String) -> URL {
        logsDir.appendingPathComponent(name)
    }

    private static func subdir(_ name: String) -> URL {
        let url = root.appendingPathComponent(name, isDirectory: true)
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    private static func runtimeDir(section: String, legacyName: String) -> URL {
        if hasAllowedAppHomeOverride {
            return subdir(legacyName)
        }
        let url = acrossRoot
            .appendingPathComponent(section, isDirectory: true)
            .appendingPathComponent("across-agents-assistant", isDirectory: true)
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    private static var hasAllowedAppHomeOverride: Bool {
        RuntimeBoundary.hasAllowedAppHomeOverride(
            bundledBackendAvailable: AppDelegate.backendExecutablePath != nil
        )
    }
}
