import Foundation

enum StartupDiagnosticStatus: String, Decodable {
    case ready
    case attention
    case blocked
    case passed
    case warning
    case failed
    case info

    var title: String {
        switch self {
        case .ready: return "Ready"
        case .attention: return "Attention"
        case .blocked: return "Blocked"
        case .passed: return "Passed"
        case .warning: return "Warning"
        case .failed: return "Failed"
        case .info: return "Info"
        }
    }
}

enum StartupDiagnosticJSONValue: Decodable, CustomStringConvertible {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: StartupDiagnosticJSONValue])
    case array([StartupDiagnosticJSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([StartupDiagnosticJSONValue].self) {
            self = .array(value)
        } else {
            self = .object(try container.decode([String: StartupDiagnosticJSONValue].self))
        }
    }

    var description: String {
        switch self {
        case .string(let value):
            return value
        case .number(let value):
            if value.rounded() == value {
                return String(Int(value))
            }
            return String(value)
        case .bool(let value):
            return value ? "true" : "false"
        case .object(let value):
            return value
                .keys
                .sorted()
                .map { "\($0): \(value[$0]?.description ?? "")" }
                .joined(separator: ", ")
        case .array(let value):
            return value.map(\.description).joined(separator: ", ")
        case .null:
            return "-"
        }
    }
}

struct StartupDiagnosticsSummary: Decodable {
    let status: StartupDiagnosticStatus
    let passed: Int
    let warnings: Int
    let failed: Int
    let checkCount: Int

    enum CodingKeys: String, CodingKey {
        case status
        case passed
        case warnings
        case failed
        case checkCount = "check_count"
    }
}

struct StartupDiagnosticsPaths: Decodable {
    let appHome: String
    let logsDir: String
    let runDir: String
    let tmpDir: String
    let evidenceDir: String
    let socketPath: String
    let databasePath: String

    enum CodingKeys: String, CodingKey {
        case appHome = "app_home"
        case logsDir = "logs_dir"
        case runDir = "run_dir"
        case tmpDir = "tmp_dir"
        case evidenceDir = "evidence_dir"
        case socketPath = "socket_path"
        case databasePath = "database_path"
    }
}

struct StartupDiagnosticsRuntime: Decodable {
    let pid: Int
    let startedAt: Double
    let uptimeSec: Double
    let knownTasks: Int
    let persistenceInitialized: Bool
    let dispatcherInitialized: Bool

    enum CodingKeys: String, CodingKey {
        case pid
        case startedAt = "started_at"
        case uptimeSec = "uptime_sec"
        case knownTasks = "known_tasks"
        case persistenceInitialized = "persistence_initialized"
        case dispatcherInitialized = "dispatcher_initialized"
    }
}

struct StartupDiagnosticsKeys: Decodable {
    let hasAnyKey: Bool
    let providers: [String: String]
    let readinessBlockers: [String]

    enum CodingKeys: String, CodingKey {
        case hasAnyKey = "has_any_key"
        case providers
        case readinessBlockers = "readiness_blockers"
    }
}

struct StartupDiagnosticsCheck: Decodable, Identifiable {
    let id: String
    let title: String
    let status: StartupDiagnosticStatus
    let detail: String
    let remediation: String?
    let metadata: [String: StartupDiagnosticJSONValue]

    var metadataString: String {
        guard !metadata.isEmpty else { return "" }
        return metadata
            .keys
            .sorted()
            .map { "\($0): \(metadata[$0]?.description ?? "")" }
            .joined(separator: " · ")
    }

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case status
        case detail
        case remediation
        case metadata
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        title = try container.decode(String.self, forKey: .title)
        status = try container.decode(StartupDiagnosticStatus.self, forKey: .status)
        detail = try container.decode(String.self, forKey: .detail)
        remediation = try container.decodeIfPresent(String.self, forKey: .remediation)
        metadata = try container.decodeIfPresent([String: StartupDiagnosticJSONValue].self, forKey: .metadata) ?? [:]
    }
}

struct StartupDiagnosticsReport: Decodable, Identifiable {
    let schemaVersion: String
    let appVersion: String
    let generatedAt: String
    let status: StartupDiagnosticStatus
    let summary: StartupDiagnosticsSummary
    let paths: StartupDiagnosticsPaths
    let runtime: StartupDiagnosticsRuntime
    let keys: StartupDiagnosticsKeys
    let checks: [StartupDiagnosticsCheck]

    var id: String {
        "startup-diagnostics-\(generatedAt)"
    }

    var warningChecks: [StartupDiagnosticsCheck] {
        checks.filter { $0.status == .warning }
    }

    var failedChecks: [StartupDiagnosticsCheck] {
        checks.filter { $0.status == .failed }
    }

    var readyHeadline: String {
        var parts = ["\(status.title)"]
        parts.append("\(summary.passed) passed")
        if summary.warnings > 0 {
            parts.append(summary.warnings == 1 ? "1 warning" : "\(summary.warnings) warnings")
        }
        if summary.failed > 0 {
            parts.append(summary.failed == 1 ? "1 failed" : "\(summary.failed) failed")
        }
        return parts.joined(separator: " · ")
    }

    var providerSummary: String {
        let knownProviders = [
            ("deepseek", "DeepSeek"),
            ("minimax", "MiniMax"),
        ]
        return knownProviders
            .map { id, title in
                let status = (keys.providers[id] ?? "unknown").replacingOccurrences(of: "_", with: " ")
                return "\(title): \(status)"
            }
            .joined(separator: " · ")
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case appVersion = "app_version"
        case generatedAt = "generated_at"
        case status
        case summary
        case paths
        case runtime
        case keys
        case checks
    }
}
