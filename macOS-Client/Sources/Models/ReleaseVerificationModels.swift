import Foundation

struct ReleaseVerificationPreReleaseGateEvidence: Decodable {
    let schemaVersion: String
    let gateId: String
    let status: String
    let source: String
    let summary: String
    let generatedAt: String?
    let startedAt: String?
    let completedAt: String?
    let durationSeconds: Int?
    let tier: String?
    let runURL: String?
    let workflowRunURL: String?
    let commitSHA: String?
    let workspaceDirty: Bool
    let evidencePath: String?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case gateId = "gate_id"
        case status
        case source
        case summary
        case generatedAt = "generated_at"
        case startedAt = "started_at"
        case completedAt = "completed_at"
        case durationSeconds = "duration_seconds"
        case tier
        case runURL = "run_url"
        case workflowRunURL = "workflow_run_url"
        case commitSHA = "commit_sha"
        case workspaceDirty = "workspace_dirty"
        case evidencePath = "evidence_path"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? "1.0"
        gateId = try container.decodeIfPresent(String.self, forKey: .gateId) ?? ""
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "unknown"
        source = try container.decodeIfPresent(String.self, forKey: .source) ?? ""
        summary = try container.decodeIfPresent(String.self, forKey: .summary) ?? ""
        generatedAt = try container.decodeIfPresent(String.self, forKey: .generatedAt)
        startedAt = try container.decodeIfPresent(String.self, forKey: .startedAt)
        completedAt = try container.decodeIfPresent(String.self, forKey: .completedAt)
        durationSeconds = try container.decodeIfPresent(Int.self, forKey: .durationSeconds)
        tier = try container.decodeIfPresent(String.self, forKey: .tier)
        runURL = try container.decodeIfPresent(String.self, forKey: .runURL)
        workflowRunURL = try container.decodeIfPresent(String.self, forKey: .workflowRunURL)
        commitSHA = try container.decodeIfPresent(String.self, forKey: .commitSHA)
        workspaceDirty = try container.decodeIfPresent(Bool.self, forKey: .workspaceDirty) ?? false
        evidencePath = try container.decodeIfPresent(String.self, forKey: .evidencePath)
    }
}

struct ReleaseVerificationPreReleaseGate: Decodable, Identifiable {
    let id: String
    let label: String
    let status: String
    let source: String
    let command: String
    let detail: String
    let paths: [String]
    let required: Bool
    let readinessImpact: String
    let evidence: ReleaseVerificationPreReleaseGateEvidence?

    enum CodingKeys: String, CodingKey {
        case id
        case label
        case status
        case source
        case command
        case detail
        case paths
        case required
        case readinessImpact = "readiness_impact"
        case evidence
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(String.self, forKey: .id) ?? ""
        label = try container.decodeIfPresent(String.self, forKey: .label) ?? id
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "unknown"
        source = try container.decodeIfPresent(String.self, forKey: .source) ?? "unknown"
        command = try container.decodeIfPresent(String.self, forKey: .command) ?? ""
        detail = try container.decodeIfPresent(String.self, forKey: .detail) ?? ""
        paths = try container.decodeIfPresent([String].self, forKey: .paths) ?? []
        required = try container.decodeIfPresent(Bool.self, forKey: .required) ?? false
        readinessImpact = try container.decodeIfPresent(String.self, forKey: .readinessImpact) ?? "required"
        evidence = try container.decodeIfPresent(ReleaseVerificationPreReleaseGateEvidence.self, forKey: .evidence)
    }
}

struct ReleaseVerificationPreReleaseGateSummary: Decodable {
    let total: Int
    let passed: Int
    let configured: Int
    let manualRequired: Int
    let missing: Int
    let failed: Int
    let requiredMissing: Int
    let requiredManual: Int
    let requiredFailed: Int
    let requiredUnverified: Int

    enum CodingKeys: String, CodingKey {
        case total
        case passed
        case configured
        case manualRequired = "manual_required"
        case missing
        case failed
        case requiredMissing = "required_missing"
        case requiredManual = "required_manual"
        case requiredFailed = "required_failed"
        case requiredUnverified = "required_unverified"
    }

    init(
        total: Int = 0,
        passed: Int = 0,
        configured: Int = 0,
        manualRequired: Int = 0,
        missing: Int = 0,
        failed: Int = 0,
        requiredMissing: Int = 0,
        requiredManual: Int = 0,
        requiredFailed: Int = 0,
        requiredUnverified: Int = 0
    ) {
        self.total = total
        self.passed = passed
        self.configured = configured
        self.manualRequired = manualRequired
        self.missing = missing
        self.failed = failed
        self.requiredMissing = requiredMissing
        self.requiredManual = requiredManual
        self.requiredFailed = requiredFailed
        self.requiredUnverified = requiredUnverified
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        total = try container.decodeIfPresent(Int.self, forKey: .total) ?? 0
        passed = try container.decodeIfPresent(Int.self, forKey: .passed) ?? 0
        configured = try container.decodeIfPresent(Int.self, forKey: .configured) ?? 0
        manualRequired = try container.decodeIfPresent(Int.self, forKey: .manualRequired) ?? 0
        missing = try container.decodeIfPresent(Int.self, forKey: .missing) ?? 0
        failed = try container.decodeIfPresent(Int.self, forKey: .failed) ?? 0
        requiredMissing = try container.decodeIfPresent(Int.self, forKey: .requiredMissing) ?? 0
        requiredManual = try container.decodeIfPresent(Int.self, forKey: .requiredManual) ?? 0
        requiredFailed = try container.decodeIfPresent(Int.self, forKey: .requiredFailed) ?? 0
        requiredUnverified = try container.decodeIfPresent(Int.self, forKey: .requiredUnverified) ?? 0
    }
}

struct ReleaseVerificationPreReleaseGateParseError: Decodable, Identifiable {
    let evidencePath: String
    let errorType: String
    let message: String

    var id: String {
        "\(evidencePath)-\(errorType)-\(message)"
    }

    enum CodingKeys: String, CodingKey {
        case evidencePath = "evidence_path"
        case errorType = "error_type"
        case message
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        evidencePath = try container.decodeIfPresent(String.self, forKey: .evidencePath) ?? ""
        errorType = try container.decodeIfPresent(String.self, forKey: .errorType) ?? "Error"
        message = try container.decodeIfPresent(String.self, forKey: .message) ?? ""
    }
}

struct ReleaseVerificationLatestSummary: Decodable {
    let status: String
    let qualityScore: Int?
    let remediationAttempts: Int
    let failedScenarios: Int

    enum CodingKeys: String, CodingKey {
        case status
        case qualityScore = "quality_score"
        case remediationAttempts = "remediation_attempts"
        case failedScenarios = "failed_scenarios"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "unknown"
        qualityScore = try container.decodeIfPresent(Int.self, forKey: .qualityScore)
        remediationAttempts = try container.decodeIfPresent(Int.self, forKey: .remediationAttempts) ?? 0
        failedScenarios = try container.decodeIfPresent(Int.self, forKey: .failedScenarios) ?? 0
    }
}

struct ReleaseVerificationLatestE2E: Decodable, Identifiable {
    let taskId: String
    let description: String
    let taskStatus: String
    let projectDir: String?
    let updatedAt: Double?
    let benchmark: TaskQualityBenchmark
    let summary: ReleaseVerificationLatestSummary

    var id: String { taskId }

    var compactDescription: String {
        let firstLine = description
            .split(whereSeparator: \.isNewline)
            .first
            .map(String.init)?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? description
        guard firstLine.count > 160 else { return firstLine }
        return "\(firstLine.prefix(157))..."
    }

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case description
        case taskStatus = "task_status"
        case projectDir = "project_dir"
        case updatedAt = "updated_at"
        case benchmark
        case summary
    }
}

struct ReleaseVerificationReportFiles: Decodable {
    let directory: String
    let jsonName: String
    let jsonPath: String
    let markdownName: String
    let markdownPath: String

    enum CodingKeys: String, CodingKey {
        case directory
        case jsonName = "json_name"
        case jsonPath = "json_path"
        case markdownName = "markdown_name"
        case markdownPath = "markdown_path"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        directory = try container.decodeIfPresent(String.self, forKey: .directory) ?? ""
        jsonName = try container.decodeIfPresent(String.self, forKey: .jsonName) ?? ""
        jsonPath = try container.decodeIfPresent(String.self, forKey: .jsonPath) ?? ""
        markdownName = try container.decodeIfPresent(String.self, forKey: .markdownName) ?? ""
        markdownPath = try container.decodeIfPresent(String.self, forKey: .markdownPath) ?? ""
    }
}

struct ReleaseVerificationAudit: Decodable {
    let readOnly: Bool
    let repairOrResumeTriggered: Bool
    let secretsRedacted: Bool
    let expectedFiles: [String]
    let requiredProbes: [String]

    enum CodingKeys: String, CodingKey {
        case readOnly = "read_only"
        case repairOrResumeTriggered = "repair_or_resume_triggered"
        case secretsRedacted = "secrets_redacted"
        case expectedFiles = "expected_files"
        case requiredProbes = "required_probes"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        readOnly = try container.decodeIfPresent(Bool.self, forKey: .readOnly) ?? false
        repairOrResumeTriggered = try container.decodeIfPresent(Bool.self, forKey: .repairOrResumeTriggered) ?? false
        secretsRedacted = try container.decodeIfPresent(Bool.self, forKey: .secretsRedacted) ?? false
        expectedFiles = try container.decodeIfPresent([String].self, forKey: .expectedFiles) ?? []
        requiredProbes = try container.decodeIfPresent([String].self, forKey: .requiredProbes) ?? []
    }
}

struct ReleaseVerificationReport: Decodable, Identifiable {
    let schemaVersion: String
    let appVersion: String
    let generatedAt: String
    let status: StartupDiagnosticStatus
    let startup: StartupDiagnosticsReport
    let releaseEvaluation: ReleaseEvaluationSummary
    let latestReleaseE2E: ReleaseVerificationLatestE2E?
    let preReleaseGates: [ReleaseVerificationPreReleaseGate]?
    let preReleaseGateSummary: ReleaseVerificationPreReleaseGateSummary?
    let preReleaseGateMissingPaths: [String]
    let preReleaseGateParseErrors: [ReleaseVerificationPreReleaseGateParseError]
    let remediations: [String]
    let reportFiles: ReleaseVerificationReportFiles
    let audit: ReleaseVerificationAudit

    var id: String {
        "release-verification-\(generatedAt)"
    }

    var primaryRemediation: String? {
        remediations.first
    }

    var gateSummary: ReleaseVerificationPreReleaseGateSummary {
        if let preReleaseGateSummary {
            return preReleaseGateSummary
        }
        let gates = preReleaseGates ?? []
        return ReleaseVerificationPreReleaseGateSummary(
            total: gates.count,
            passed: gates.filter { $0.status == "passed" }.count,
            configured: gates.filter { $0.status == "configured" }.count,
            manualRequired: gates.filter { $0.status == "manual_required" }.count,
            missing: gates.filter { $0.status == "missing" }.count,
            failed: gates.filter { $0.status == "failed" || $0.status == "blocked" }.count,
            requiredMissing: gates.filter { $0.required && $0.status == "missing" }.count,
            requiredManual: gates.filter { $0.required && $0.status == "manual_required" }.count,
            requiredFailed: gates.filter { $0.required && ($0.status == "failed" || $0.status == "blocked") }.count,
            requiredUnverified: gates.filter { $0.required && $0.status == "configured" }.count
        )
    }

    var gateHeadline: String {
        let summary = gateSummary
        if summary.total == 0 {
            return "No pre-release gates reported"
        }
        return "\(summary.passed) passed · \(summary.configured) configured · \(summary.manualRequired) manual · \(summary.missing) missing"
    }

    var readyHeadline: String {
        guard let latestReleaseE2E else {
            return "\(status.title) · Release E2E missing"
        }
        let score = latestReleaseE2E.summary.qualityScore.map(String.init) ?? "-"
        return "\(status.title) · Release E2E \(latestReleaseE2E.summary.status) · score \(score)"
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case appVersion = "app_version"
        case generatedAt = "generated_at"
        case status
        case startup
        case releaseEvaluation = "release_evaluation"
        case latestReleaseE2E = "latest_release_e2e"
        case preReleaseGates = "pre_release_gates"
        case preReleaseGateSummary = "pre_release_gate_summary"
        case preReleaseGateMissingPaths = "pre_release_gate_missing_paths"
        case preReleaseGateParseErrors = "pre_release_gate_parse_errors"
        case remediations
        case reportFiles = "report_files"
        case audit
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? "1.0"
        appVersion = try container.decodeIfPresent(String.self, forKey: .appVersion) ?? ""
        generatedAt = try container.decodeIfPresent(String.self, forKey: .generatedAt) ?? ""
        status = try container.decodeIfPresent(StartupDiagnosticStatus.self, forKey: .status) ?? .attention
        startup = try container.decode(StartupDiagnosticsReport.self, forKey: .startup)
        releaseEvaluation = try container.decode(ReleaseEvaluationSummary.self, forKey: .releaseEvaluation)
        latestReleaseE2E = try container.decodeIfPresent(ReleaseVerificationLatestE2E.self, forKey: .latestReleaseE2E)
        preReleaseGates = try container.decodeIfPresent([ReleaseVerificationPreReleaseGate].self, forKey: .preReleaseGates)
        preReleaseGateSummary = try container.decodeIfPresent(ReleaseVerificationPreReleaseGateSummary.self, forKey: .preReleaseGateSummary)
        preReleaseGateMissingPaths = try container.decodeIfPresent([String].self, forKey: .preReleaseGateMissingPaths) ?? []
        preReleaseGateParseErrors = try container.decodeIfPresent([ReleaseVerificationPreReleaseGateParseError].self, forKey: .preReleaseGateParseErrors) ?? []
        remediations = try container.decodeIfPresent([String].self, forKey: .remediations) ?? []
        reportFiles = try container.decode(ReleaseVerificationReportFiles.self, forKey: .reportFiles)
        audit = try container.decode(ReleaseVerificationAudit.self, forKey: .audit)
    }
}
