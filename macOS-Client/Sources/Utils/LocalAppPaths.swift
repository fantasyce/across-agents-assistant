import Foundation

enum LocalAppPaths {
    static var root: URL {
        let env = ProcessInfo.processInfo.environment["ACROSS_AGENTS_HOME"]
        let path = env?.isEmpty == false ? env! : "~/.across_agents"
        return URL(fileURLWithPath: (path as NSString).expandingTildeInPath)
    }

    static var logsDir: URL {
        subdir("logs")
    }

    static var runDir: URL {
        subdir("run")
    }

    static var tmpDir: URL {
        subdir("tmp")
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
}
