import Foundation

struct WorkerControlSnapshot: Codable, Equatable {
    let schemaVersion: String
    let nodes: [WorkerNode]
    let pending: [WorkerNode]
    let listener: WorkerListenerConfiguration
    let relay: WorkerRelayConfiguration
    let health: WorkerControlHealth
    let recovery: WorkerControlRecovery?
    let release: WorkerReleaseStatus?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case nodes, pending, listener, relay, health, recovery, release
    }
}

struct WorkerReleaseStatus: Codable, Equatable {
    let published: Bool
    let version: String?
    let platforms: [String]
}

struct WorkerNode: Codable, Identifiable, Equatable {
    static let reconnectGraceSeconds: TimeInterval = 45

    let nodeID: String
    let displayName: String
    let state: String
    let fingerprint: String
    let approvedAt: Double?
    let lastSeenAt: Double?
    let transport: String
    let transportQuality: WorkerTransportQuality?
    let currentJob: WorkerJobSummary?
    let recentResult: WorkerResultSummary?
    let draining: Bool
    let capabilityManifest: WorkerCapabilityManifest
    let verificationCode: String?

    var id: String { nodeID }

    var presentationState: String {
        Self.presentationState(
            reportedState: state,
            lastSeenAt: lastSeenAt,
            now: Date().timeIntervalSince1970
        )
    }

    static func presentationState(
        reportedState: String,
        lastSeenAt: Double?,
        now: TimeInterval,
        reconnectGraceSeconds: TimeInterval = 45
    ) -> String {
        guard reportedState == "offline", let lastSeenAt else { return reportedState }
        let elapsed = max(0, now - lastSeenAt)
        return elapsed <= reconnectGraceSeconds ? "reconnecting" : reportedState
    }

    enum CodingKeys: String, CodingKey {
        case nodeID = "node_id"
        case displayName = "display_name"
        case state, fingerprint, transport, draining
        case approvedAt = "approved_at"
        case lastSeenAt = "last_seen_at"
        case transportQuality = "transport_quality"
        case currentJob = "current_job"
        case recentResult = "recent_result"
        case capabilityManifest = "capability_manifest"
        case verificationCode = "verification_code"
    }
}

struct WorkerCapabilityManifest: Codable, Equatable {
    let workerVersion: String?
    let os: String?
    let osVersion: String?
    let architecture: String?
    let cpuCount: Int?
    let memoryBytes: Int64?
    let diskAvailableBytes: Int64?
    let executors: [String]?
    let isolationLevel: String?
    let verificationStatus: String?

    enum CodingKeys: String, CodingKey {
        case workerVersion = "worker_version"
        case os
        case osVersion = "os_version"
        case architecture
        case cpuCount = "cpu_count"
        case memoryBytes = "memory_bytes"
        case diskAvailableBytes = "disk_available_bytes"
        case executors
        case isolationLevel = "isolation_level"
        case verificationStatus = "verification_status"
    }
}

struct WorkerTransportQuality: Codable, Equatable {
    let latencyMilliseconds: Double?
    let lossPercent: Double?

    enum CodingKeys: String, CodingKey {
        case latencyMilliseconds = "latency_ms"
        case lossPercent = "loss_percent"
    }
}

struct WorkerJobSummary: Codable, Equatable {
    let jobID: String?
    let title: String?
    let state: String?

    enum CodingKeys: String, CodingKey {
        case jobID = "job_id"
        case title, state
    }
}

struct WorkerResultSummary: Codable, Equatable {
    let jobID: String?
    let state: String?
    let finishedAt: Double?

    enum CodingKeys: String, CodingKey {
        case jobID = "job_id"
        case state
        case finishedAt = "finished_at"
    }
}

struct WorkerListenerConfiguration: Codable, Equatable {
    let enabled: Bool
    let bindHost: String?
    let port: Int
    let modelGatewayPort: Int?
    let enrollmentPort: Int?
    let certificateFingerprint: String?
    let tlsMinimum: String?
    let mutualAuthentication: Bool?
    let runtime: WorkerListenerRuntime?

    enum CodingKeys: String, CodingKey {
        case enabled, port, runtime
        case bindHost = "bind_host"
        case modelGatewayPort = "model_gateway_port"
        case enrollmentPort = "enrollment_port"
        case certificateFingerprint = "certificate_fingerprint"
        case tlsMinimum = "tls_minimum"
        case mutualAuthentication = "mutual_authentication"
    }
}

struct WorkerListenerRuntime: Codable, Equatable {
    let status: String
    let listenerRunning: Bool
    let modelGatewayRunning: Bool
    let enrollmentGatewayRunning: Bool?
    let lastError: String?
    let tlsMinimum: String?
    let hostCredentialsCopied: Bool

    enum CodingKeys: String, CodingKey {
        case status
        case listenerRunning = "listener_running"
        case modelGatewayRunning = "model_gateway_running"
        case enrollmentGatewayRunning = "enrollment_gateway_running"
        case lastError = "last_error"
        case tlsMinimum = "tls_minimum"
        case hostCredentialsCopied = "host_credentials_copied"
    }
}

struct WorkerRelayConfiguration: Codable, Equatable {
    let enabled: Bool
    let endpoint: String?
    let status: String
    let storesJobContent: Bool?
    let storesCredentials: Bool?

    enum CodingKeys: String, CodingKey {
        case enabled, endpoint, status
        case storesJobContent = "stores_job_content"
        case storesCredentials = "stores_credentials"
    }
}

struct WorkerControlHealth: Codable, Equatable {
    let status: String
    let nodeCount: Int
    let onlineCount: Int
    let pendingCount: Int
    let incompatibleCount: Int
    let listenerEnabled: Bool
    let relayEnabled: Bool

    enum CodingKeys: String, CodingKey {
        case status
        case nodeCount = "node_count"
        case onlineCount = "online_count"
        case pendingCount = "pending_count"
        case incompatibleCount = "incompatible_count"
        case listenerEnabled = "listener_enabled"
        case relayEnabled = "relay_enabled"
    }
}

struct WorkerControlRecovery: Codable, Equatable {
    let status: String
    let at: Double?
    let backupName: String?

    enum CodingKeys: String, CodingKey {
        case status, at
        case backupName = "backup_name"
    }
}

struct WorkerPairingResponse: Codable, Equatable {
    let enrollmentID: String
    let pairingCode: String
    let expiresAt: Double
    let oneTime: Bool
    let containsLongTermSecret: Bool
    let install: WorkerInstallCommand?
    let installUnavailableReason: String?

    enum CodingKeys: String, CodingKey {
        case enrollmentID = "enrollment_id"
        case pairingCode = "pairing_code"
        case expiresAt = "expires_at"
        case oneTime = "one_time"
        case containsLongTermSecret = "contains_long_term_secret"
        case install
        case installUnavailableReason = "install_unavailable_reason"
    }
}

struct WorkerInstallCommand: Codable, Equatable {
    let platform: String
    let argv: [String]
    let shellCommand: String
    let expiresAt: Double
    let containsLongTermSecret: Bool

    enum CodingKeys: String, CodingKey {
        case platform, argv
        case shellCommand = "shell_command"
        case expiresAt = "expires_at"
        case containsLongTermSecret = "contains_long_term_secret"
    }
}
