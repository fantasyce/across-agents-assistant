import Foundation

enum LocalAppPaths {
    static var acrossRoot: URL {
        let env = ProcessInfo.processInfo.environment["ACROSS_HOME"]
        let path = env?.isEmpty == false ? env! : "~/.across"
        return URL(fileURLWithPath: (path as NSString).expandingTildeInPath)
    }

    static var root: URL {
        let env = ProcessInfo.processInfo.environment["ACROSS_AGENTS_HOME"]
        if env?.isEmpty == false {
            return URL(fileURLWithPath: (env! as NSString).expandingTildeInPath)
        }
        return acrossRoot
            .appendingPathComponent("data", isDirectory: true)
            .appendingPathComponent("across-agents-assistant", isDirectory: true)
    }

    static var logsDir: URL {
        runtimeDir(section: "logs", legacyName: "logs")
    }

    static var runDir: URL {
        runtimeDir(section: "run", legacyName: "run")
    }

    static var tmpDir: URL {
        if ProcessInfo.processInfo.environment["ACROSS_AGENTS_HOME"]?.isEmpty == false {
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
        if ProcessInfo.processInfo.environment["ACROSS_AGENTS_HOME"]?.isEmpty == false {
            return subdir(legacyName)
        }
        let url = acrossRoot
            .appendingPathComponent(section, isDirectory: true)
            .appendingPathComponent("across-agents-assistant", isDirectory: true)
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }
}
