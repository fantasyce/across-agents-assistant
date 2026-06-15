import Foundation

enum RuntimeBoundary {
    private static let truthyValues: Set<String> = ["1", "true", "yes", "on", "y"]

    static func isProductMode(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        bundledBackendAvailable: Bool = false
    ) -> Bool {
        truthy(environment["ACROSS_AGENTS_PRODUCT_MODE"]) || bundledBackendAvailable
    }

    static func isDeveloperMode(environment: [String: String] = ProcessInfo.processInfo.environment) -> Bool {
        truthy(environment["ACROSS_AGENTS_DEVELOPER_MODE"])
            || truthy(environment["ACROSS_AGENTS_ALLOW_DEVELOPMENT_RUNTIME_PATHS"])
    }

    static func safeAcrossRoot(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        bundledBackendAvailable: Bool = false
    ) -> URL {
        if let configured = nonEmpty(environment["ACROSS_HOME"]),
           runtimeOverrideAllowed(configured, environment: environment, bundledBackendAvailable: bundledBackendAvailable) {
            return URL(fileURLWithPath: expandUser(configured, environment: environment))
        }
        return homeDirectory(environment: environment)
            .appendingPathComponent(".across", isDirectory: true)
    }

    static func safeBackendProjectDirectoryOverride(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        bundledBackendAvailable: Bool
    ) -> URL? {
        guard let configured = nonEmpty(environment["ACROSS_AGENTS_BACKEND_DIR"]) else {
            return nil
        }
        guard runtimeOverrideAllowed(configured, environment: environment, bundledBackendAvailable: bundledBackendAvailable) else {
            return nil
        }
        return URL(fileURLWithPath: expandUser(configured, environment: environment))
    }

    static func safeAppHome(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        bundledBackendAvailable: Bool = false
    ) -> URL {
        if let configured = nonEmpty(environment["ACROSS_AGENTS_HOME"]),
           runtimeOverrideAllowed(configured, environment: environment, bundledBackendAvailable: bundledBackendAvailable) {
            return URL(fileURLWithPath: expandUser(configured, environment: environment))
        }
        return safeAcrossRoot(environment: environment, bundledBackendAvailable: bundledBackendAvailable)
            .appendingPathComponent("data", isDirectory: true)
            .appendingPathComponent("across-agents-assistant", isDirectory: true)
    }

    static func hasAllowedAppHomeOverride(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        bundledBackendAvailable: Bool = false
    ) -> Bool {
        guard let configured = nonEmpty(environment["ACROSS_AGENTS_HOME"]) else {
            return false
        }
        return runtimeOverrideAllowed(configured, environment: environment, bundledBackendAvailable: bundledBackendAvailable)
    }

    static func containsProtectedUserReference(
        _ value: String,
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> Bool {
        let expanded = expandUser(value, environment: environment)
        if protectedUserRoots(environment: environment).contains(where: { referencesPathRoot(expanded, root: $0) }) {
            return true
        }
        let pattern = #"(~|/Users/[^/]+)/(Documents|Desktop|Downloads)(/|$)"#
        return expanded.range(of: pattern, options: .regularExpression) != nil
    }

    private static func runtimeOverrideAllowed(
        _ value: String,
        environment: [String: String],
        bundledBackendAvailable: Bool
    ) -> Bool {
        if !isProductMode(environment: environment, bundledBackendAvailable: bundledBackendAvailable) {
            return true
        }
        if isDeveloperMode(environment: environment) {
            return true
        }
        return !containsProtectedUserReference(value, environment: environment)
    }

    private static func truthy(_ value: String?) -> Bool {
        guard let text = value?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
              !text.isEmpty else {
            return false
        }
        return truthyValues.contains(text)
    }

    private static func nonEmpty(_ value: String?) -> String? {
        guard let text = value?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else {
            return nil
        }
        return text
    }

    private static func homeDirectory(environment: [String: String]) -> URL {
        if let configured = nonEmpty(environment["HOME"]) {
            return URL(fileURLWithPath: (configured as NSString).expandingTildeInPath)
        }
        return FileManager.default.homeDirectoryForCurrentUser
    }

    private static func expandUser(_ value: String, environment: [String: String]) -> String {
        if value == "~" {
            return homeDirectory(environment: environment).path
        }
        if value.hasPrefix("~/") {
            return (homeDirectory(environment: environment).path as NSString)
                .appendingPathComponent(String(value.dropFirst(2)))
        }
        return (value as NSString).expandingTildeInPath
    }

    private static func protectedUserRoots(environment: [String: String]) -> [URL] {
        let home = homeDirectory(environment: environment)
        return [
            home.appendingPathComponent("Documents", isDirectory: true),
            home.appendingPathComponent("Desktop", isDirectory: true),
            home.appendingPathComponent("Downloads", isDirectory: true)
        ]
    }

    private static func referencesPathRoot(_ text: String, root: URL) -> Bool {
        let rootPath = root.standardizedFileURL.path
        return text == rootPath || text.hasPrefix(rootPath + "/") || text.contains(rootPath + "/")
    }
}
