import Foundation

struct ReleaseEvaluationRisk: Decodable, Identifiable {
    let kind: String
    let severity: String
    let count: Int?
    let message: String

    var id: String { "\(kind)-\(severity)-\(message)" }
}

struct ReleaseEvaluationProbeSummary: Decodable {
    let passed: [String]
    let failed: [String]
    let manualRequired: [String]
    let skipped: [String]
    let unknown: [String]

    enum CodingKeys: String, CodingKey {
        case passed
        case failed
        case manualRequired = "manual_required"
        case skipped
        case unknown
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        passed = try container.decodeIfPresent([String].self, forKey: .passed) ?? []
        failed = try container.decodeIfPresent([String].self, forKey: .failed) ?? []
        manualRequired = try container.decodeIfPresent([String].self, forKey: .manualRequired) ?? []
        skipped = try container.decodeIfPresent([String].self, forKey: .skipped) ?? []
        unknown = try container.decodeIfPresent([String].self, forKey: .unknown) ?? []
    }
}

struct ReleaseEvaluationRecentAgentMix: Decodable {
    let actualAgents: [String]
    let localAgents: [String]
    let cloudAgents: [String]

    enum CodingKeys: String, CodingKey {
        case actualAgents = "actual_agents"
        case localAgents = "local_agents"
        case cloudAgents = "cloud_agents"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        actualAgents = try container.decodeIfPresent([String].self, forKey: .actualAgents) ?? []
        localAgents = try container.decodeIfPresent([String].self, forKey: .localAgents) ?? []
        cloudAgents = try container.decodeIfPresent([String].self, forKey: .cloudAgents) ?? []
    }
}

struct ReleaseEvaluationAuditTrace: Decodable {
    let qualityGate: String?
    let finalQualityScore: Int?
    let remediationCount: Int
    let requiredFailedCount: Int
    let manualRequiredCount: Int
    let skippedRequiredCount: Int
    let passedProbeCount: Int
    let failedProbeCount: Int

    enum CodingKeys: String, CodingKey {
        case qualityGate = "quality_gate"
        case finalQualityScore = "final_quality_score"
        case remediationCount = "remediation_count"
        case requiredFailedCount = "required_failed_count"
        case manualRequiredCount = "manual_required_count"
        case skippedRequiredCount = "skipped_required_count"
        case passedProbeCount = "passed_probe_count"
        case failedProbeCount = "failed_probe_count"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        qualityGate = try container.decodeIfPresent(String.self, forKey: .qualityGate)
        finalQualityScore = try container.decodeIfPresent(Int.self, forKey: .finalQualityScore)
        remediationCount = try container.decodeIfPresent(Int.self, forKey: .remediationCount) ?? 0
        requiredFailedCount = try container.decodeIfPresent(Int.self, forKey: .requiredFailedCount) ?? 0
        manualRequiredCount = try container.decodeIfPresent(Int.self, forKey: .manualRequiredCount) ?? 0
        skippedRequiredCount = try container.decodeIfPresent(Int.self, forKey: .skippedRequiredCount) ?? 0
        passedProbeCount = try container.decodeIfPresent(Int.self, forKey: .passedProbeCount) ?? 0
        failedProbeCount = try container.decodeIfPresent(Int.self, forKey: .failedProbeCount) ?? 0
    }
}

struct ReleaseEvaluationRecentTask: Decodable, Identifiable {
    let taskId: String
    let description: String
    let status: String
    let qualityGate: String?
    let finalQualityScore: Int?
    let benchmarkStatus: String?
    let probeSummary: ReleaseEvaluationProbeSummary?
    let agentMix: ReleaseEvaluationRecentAgentMix?
    let auditTrace: ReleaseEvaluationAuditTrace?

    var id: String { taskId }

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case description
        case status
        case qualityGate = "quality_gate"
        case finalQualityScore = "final_quality_score"
        case benchmarkStatus = "benchmark_status"
        case probeSummary = "probe_summary"
        case agentMix = "agent_mix"
        case auditTrace = "audit_trace"
    }
}

struct ReleaseEvaluationTrendPoint: Decodable, Identifiable {
    let taskId: String
    let score: Int?
    let qualityGate: String?
    let updatedAt: Double?

    var id: String { taskId }

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case score
        case qualityGate = "quality_gate"
        case updatedAt = "updated_at"
    }
}

struct ReleaseEvaluationQualityTrend: Decodable {
    let direction: String
    let latestScore: Int?
    let previousScore: Int?
    let delta: Int?
    let pointCount: Int
    let points: [ReleaseEvaluationTrendPoint]

    enum CodingKeys: String, CodingKey {
        case direction
        case latestScore = "latest_score"
        case previousScore = "previous_score"
        case delta
        case pointCount = "point_count"
        case points
    }
}

struct ReleaseEvaluationAgentMixSummary: Decodable {
    let distinctAgentCount: Int
    let localAgentCount: Int
    let cloudAgentCount: Int
    let distinctAgents: [String]
    let localAgents: [String]
    let cloudAgents: [String]
    let satisfiesReleaseMix: Bool
    let missing: [String]

    enum CodingKeys: String, CodingKey {
        case distinctAgentCount = "distinct_agent_count"
        case localAgentCount = "local_agent_count"
        case cloudAgentCount = "cloud_agent_count"
        case distinctAgents = "distinct_agents"
        case localAgents = "local_agents"
        case cloudAgents = "cloud_agents"
        case satisfiesReleaseMix = "satisfies_release_mix"
        case missing
    }
}

struct ReleaseEvaluationProbeCoverage: Decodable {
    let passed: [String: Int]
    let failed: [String: Int]
    let skipped: [String: Int]
    let manualRequired: [String: Int]
    let unknown: [String: Int]
    let requiredProbeTypes: [String]
    let missingRequiredProbeTypes: [String]
    let satisfiesReleaseProbeCoverage: Bool

    enum CodingKeys: String, CodingKey {
        case passed
        case failed
        case skipped
        case manualRequired = "manual_required"
        case unknown
        case requiredProbeTypes = "required_probe_types"
        case missingRequiredProbeTypes = "missing_required_probe_types"
        case satisfiesReleaseProbeCoverage = "satisfies_release_probe_coverage"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        passed = try container.decodeIfPresent([String: Int].self, forKey: .passed) ?? [:]
        failed = try container.decodeIfPresent([String: Int].self, forKey: .failed) ?? [:]
        skipped = try container.decodeIfPresent([String: Int].self, forKey: .skipped) ?? [:]
        manualRequired = try container.decodeIfPresent([String: Int].self, forKey: .manualRequired) ?? [:]
        unknown = try container.decodeIfPresent([String: Int].self, forKey: .unknown) ?? [:]
        requiredProbeTypes = try container.decodeIfPresent([String].self, forKey: .requiredProbeTypes) ?? []
        missingRequiredProbeTypes = try container.decodeIfPresent([String].self, forKey: .missingRequiredProbeTypes) ?? []
        satisfiesReleaseProbeCoverage = try container.decodeIfPresent(Bool.self, forKey: .satisfiesReleaseProbeCoverage) ?? false
    }
}

struct ReleaseEvaluationReadinessCheck: Decodable, Identifiable {
    let id: String
    let status: String
    let label: String
    let message: String
    let severity: String
}

struct ReleaseEvaluationSupplementalEvidence: Decodable, Identifiable {
    let id: String
    let kind: String
    let status: String
    let qualityGate: String
    let passedCount: Int
    let failedCount: Int
    let hostTargetCount: Int
    let mcpServerCount: Int
    let protocolReadinessScore: Int
    let endpoint: String?

    enum CodingKeys: String, CodingKey {
        case id
        case kind
        case status
        case qualityGate = "quality_gate"
        case passedCount = "passed_count"
        case failedCount = "failed_count"
        case hostTargetCount = "host_target_count"
        case mcpServerCount = "mcp_server_count"
        case protocolReadinessScore = "protocol_readiness_score"
        case endpoint
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
        kind = try container.decodeIfPresent(String.self, forKey: .kind) ?? "supplemental"
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "unknown"
        qualityGate = try container.decodeIfPresent(String.self, forKey: .qualityGate) ?? "unknown"
        passedCount = try container.decodeIfPresent(Int.self, forKey: .passedCount) ?? 0
        failedCount = try container.decodeIfPresent(Int.self, forKey: .failedCount) ?? 0
        hostTargetCount = try container.decodeIfPresent(Int.self, forKey: .hostTargetCount) ?? 0
        mcpServerCount = try container.decodeIfPresent(Int.self, forKey: .mcpServerCount) ?? 0
        protocolReadinessScore = try container.decodeIfPresent(Int.self, forKey: .protocolReadinessScore) ?? 0
        endpoint = try container.decodeIfPresent(String.self, forKey: .endpoint)
    }
}

struct ReleaseEvaluationSummary: Decodable {
    let releaseReadiness: String
    let generatedAt: Double?
    let releaseEvidenceCount: Int
    let passedEvidenceCount: Int
    let agentInteropE2EStatus: String?
    let evaluatedTaskCount: Int
    let terminalTaskCount: Int
    let passedTaskCount: Int
    let blockedTaskCount: Int
    let manualTaskCount: Int
    let skippedTaskCount: Int
    let passRate: Double
    let averageFinalQualityScore: Int?
    let totalRemediationCount: Int
    let recommendation: String?
    let topRisks: [ReleaseEvaluationRisk]
    let recentEvaluations: [ReleaseEvaluationRecentTask]
    let qualityTrend: ReleaseEvaluationQualityTrend?
    let agentMixSummary: ReleaseEvaluationAgentMixSummary?
    let probeCoverage: ReleaseEvaluationProbeCoverage?
    let readinessChecks: [ReleaseEvaluationReadinessCheck]
    let supplementalEvidence: [ReleaseEvaluationSupplementalEvidence]
    let gateBreakdown: [String: Int]
    let stackCoverage: [String: Int]
    let agentCoverage: [String: Int]

    enum CodingKeys: String, CodingKey {
        case releaseReadiness = "release_readiness"
        case generatedAt = "generated_at"
        case releaseEvidenceCount = "release_evidence_count"
        case passedEvidenceCount = "passed_evidence_count"
        case agentInteropE2EStatus = "agent_interop_e2e_status"
        case evaluatedTaskCount = "evaluated_task_count"
        case terminalTaskCount = "terminal_task_count"
        case passedTaskCount = "passed_task_count"
        case blockedTaskCount = "blocked_task_count"
        case manualTaskCount = "manual_task_count"
        case skippedTaskCount = "skipped_task_count"
        case passRate = "pass_rate"
        case averageFinalQualityScore = "average_final_quality_score"
        case totalRemediationCount = "total_remediation_count"
        case recommendation
        case topRisks = "top_risks"
        case recentEvaluations = "recent_evaluations"
        case qualityTrend = "quality_trend"
        case agentMixSummary = "agent_mix_summary"
        case probeCoverage = "probe_coverage"
        case readinessChecks = "readiness_checks"
        case supplementalEvidence = "supplemental_evidence"
        case gateBreakdown = "gate_breakdown"
        case stackCoverage = "stack_coverage"
        case agentCoverage = "agent_coverage"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        releaseReadiness = try container.decode(String.self, forKey: .releaseReadiness)
        generatedAt = try container.decodeIfPresent(Double.self, forKey: .generatedAt)
        evaluatedTaskCount = try container.decodeIfPresent(Int.self, forKey: .evaluatedTaskCount) ?? 0
        releaseEvidenceCount = try container.decodeIfPresent(Int.self, forKey: .releaseEvidenceCount) ?? evaluatedTaskCount
        terminalTaskCount = try container.decodeIfPresent(Int.self, forKey: .terminalTaskCount) ?? 0
        passedTaskCount = try container.decodeIfPresent(Int.self, forKey: .passedTaskCount) ?? 0
        passedEvidenceCount = try container.decodeIfPresent(Int.self, forKey: .passedEvidenceCount) ?? passedTaskCount
        agentInteropE2EStatus = try container.decodeIfPresent(String.self, forKey: .agentInteropE2EStatus)
        blockedTaskCount = try container.decodeIfPresent(Int.self, forKey: .blockedTaskCount) ?? 0
        manualTaskCount = try container.decodeIfPresent(Int.self, forKey: .manualTaskCount) ?? 0
        skippedTaskCount = try container.decodeIfPresent(Int.self, forKey: .skippedTaskCount) ?? 0
        passRate = try container.decodeIfPresent(Double.self, forKey: .passRate) ?? 0
        averageFinalQualityScore = try container.decodeIfPresent(Int.self, forKey: .averageFinalQualityScore)
        totalRemediationCount = try container.decodeIfPresent(Int.self, forKey: .totalRemediationCount) ?? 0
        recommendation = try container.decodeIfPresent(String.self, forKey: .recommendation)
        topRisks = try container.decodeIfPresent([ReleaseEvaluationRisk].self, forKey: .topRisks) ?? []
        recentEvaluations = try container.decodeIfPresent([ReleaseEvaluationRecentTask].self, forKey: .recentEvaluations) ?? []
        qualityTrend = try container.decodeIfPresent(ReleaseEvaluationQualityTrend.self, forKey: .qualityTrend)
        agentMixSummary = try container.decodeIfPresent(ReleaseEvaluationAgentMixSummary.self, forKey: .agentMixSummary)
        probeCoverage = try container.decodeIfPresent(ReleaseEvaluationProbeCoverage.self, forKey: .probeCoverage)
        readinessChecks = try container.decodeIfPresent([ReleaseEvaluationReadinessCheck].self, forKey: .readinessChecks) ?? []
        supplementalEvidence = try container.decodeIfPresent([ReleaseEvaluationSupplementalEvidence].self, forKey: .supplementalEvidence) ?? []
        gateBreakdown = try container.decodeIfPresent([String: Int].self, forKey: .gateBreakdown) ?? [:]
        stackCoverage = try container.decodeIfPresent([String: Int].self, forKey: .stackCoverage) ?? [:]
        agentCoverage = try container.decodeIfPresent([String: Int].self, forKey: .agentCoverage) ?? [:]
    }

    var passRatePercent: Int {
        Int((passRate * 100).rounded())
    }

    var primaryRiskMessage: String? {
        topRisks.first?.message ?? recommendation
    }

    var trendDeltaText: String {
        guard let delta = qualityTrend?.delta else { return "-" }
        if delta > 0 { return "+\(delta)" }
        return "\(delta)"
    }
}

struct TaskQualityBenchmarkScenario: Decodable, Identifiable {
    let taskId: String
    let status: String
    let qualityGate: String?
    let finalStatus: String?
    let qualityScore: Int
    let remediationAttempts: Int
    let producedFiles: [String]
    let checks: [String: Bool]
    let failures: [String]

    var id: String { taskId }

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case status
        case qualityGate = "quality_gate"
        case finalStatus = "final_status"
        case qualityScore = "quality_score"
        case remediationAttempts = "remediation_attempts"
        case producedFiles = "produced_files"
        case checks
        case failures
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        taskId = try container.decodeIfPresent(String.self, forKey: .taskId) ?? ""
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "unknown"
        qualityGate = try container.decodeIfPresent(String.self, forKey: .qualityGate)
        finalStatus = try container.decodeIfPresent(String.self, forKey: .finalStatus)
        qualityScore = try container.decodeIfPresent(Int.self, forKey: .qualityScore) ?? 0
        remediationAttempts = try container.decodeIfPresent(Int.self, forKey: .remediationAttempts) ?? 0
        producedFiles = try container.decodeIfPresent([String].self, forKey: .producedFiles) ?? []
        checks = try container.decodeIfPresent([String: Bool].self, forKey: .checks) ?? [:]
        failures = try container.decodeIfPresent([String].self, forKey: .failures) ?? []
    }
}

struct TaskQualityBenchmarkSummary: Decodable {
    let scenarioCount: Int
    let passedScenarios: Int
    let failedScenarios: Int
    let minQualityScore: Int
    let maxRemediationAttempts: Int

    enum CodingKeys: String, CodingKey {
        case scenarioCount = "scenario_count"
        case passedScenarios = "passed_scenarios"
        case failedScenarios = "failed_scenarios"
        case minQualityScore = "min_quality_score"
        case maxRemediationAttempts = "max_remediation_attempts"
    }

    init(
        scenarioCount: Int = 0,
        passedScenarios: Int = 0,
        failedScenarios: Int = 0,
        minQualityScore: Int = 0,
        maxRemediationAttempts: Int = 0
    ) {
        self.scenarioCount = scenarioCount
        self.passedScenarios = passedScenarios
        self.failedScenarios = failedScenarios
        self.minQualityScore = minQualityScore
        self.maxRemediationAttempts = maxRemediationAttempts
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        scenarioCount = try container.decodeIfPresent(Int.self, forKey: .scenarioCount) ?? 0
        passedScenarios = try container.decodeIfPresent(Int.self, forKey: .passedScenarios) ?? 0
        failedScenarios = try container.decodeIfPresent(Int.self, forKey: .failedScenarios) ?? 0
        minQualityScore = try container.decodeIfPresent(Int.self, forKey: .minQualityScore) ?? 0
        maxRemediationAttempts = try container.decodeIfPresent(Int.self, forKey: .maxRemediationAttempts) ?? 0
    }
}

struct TaskQualityBenchmark: Decodable {
    let benchmarkId: String
    let benchmarkVersion: String?
    let appVersion: String?
    let status: String
    let summary: TaskQualityBenchmarkSummary
    let scenarios: [TaskQualityBenchmarkScenario]

    enum CodingKeys: String, CodingKey {
        case benchmarkId = "benchmark_id"
        case benchmarkVersion = "benchmark_version"
        case appVersion = "app_version"
        case status
        case summary
        case scenarios
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        benchmarkId = try container.decodeIfPresent(String.self, forKey: .benchmarkId) ?? ""
        benchmarkVersion = try container.decodeIfPresent(String.self, forKey: .benchmarkVersion)
        appVersion = try container.decodeIfPresent(String.self, forKey: .appVersion)
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "unknown"
        summary = try container.decodeIfPresent(TaskQualityBenchmarkSummary.self, forKey: .summary) ?? TaskQualityBenchmarkSummary()
        scenarios = try container.decodeIfPresent([TaskQualityBenchmarkScenario].self, forKey: .scenarios) ?? []
    }
}

struct TaskEvidenceAudit: Decodable {
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
        if let value = try? container.decode(Bool.self, forKey: .secretsRedacted) {
            secretsRedacted = value
        } else if (try? container.decode(String.self, forKey: .secretsRedacted)) != nil {
            secretsRedacted = true
        } else {
            secretsRedacted = false
        }
        expectedFiles = try container.decodeIfPresent([String].self, forKey: .expectedFiles) ?? []
        requiredProbes = try container.decodeIfPresent([String].self, forKey: .requiredProbes) ?? []
    }
}

struct TaskEvidenceBundle: Decodable, Identifiable {
    static let releaseE2EExpectedFiles = [
        "README.md",
        "web/index.html",
        "web/styles.css",
        "web/app.js",
        "api/server.mjs",
        "cli/quality-check.mjs",
        "tests/e2e-smoke.mjs"
    ]

    static let releaseE2ERequiredProbes = [
        "static_web_smoke",
        "browser_e2e",
        "api_service",
        "cli_generic"
    ]

    let schemaVersion: String
    let appVersion: String?
    let generatedAt: Double?
    let taskId: String
    let description: String?
    let taskStatus: String
    let taskTypes: [String]
    let deliveryMode: String
    let projectDir: String?
    let ownerAgent: String?
    let allowedSubtaskAgents: [String]
    let resultReport: String?
    let benchmark: TaskQualityBenchmark
    let audit: TaskEvidenceAudit

    var id: String { taskId }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case appVersion = "app_version"
        case generatedAt = "generated_at"
        case taskId = "task_id"
        case description
        case taskStatus = "task_status"
        case taskTypes = "task_types"
        case deliveryMode = "delivery_mode"
        case projectDir = "project_dir"
        case ownerAgent = "owner_agent"
        case allowedSubtaskAgents = "allowed_subtask_agents"
        case resultReport = "result_report"
        case benchmark
        case audit
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? "unknown"
        appVersion = try container.decodeIfPresent(String.self, forKey: .appVersion)
        generatedAt = try container.decodeIfPresent(Double.self, forKey: .generatedAt)
        taskId = try container.decodeIfPresent(String.self, forKey: .taskId) ?? ""
        description = try container.decodeIfPresent(String.self, forKey: .description)
        taskStatus = try container.decodeIfPresent(String.self, forKey: .taskStatus) ?? "unknown"
        taskTypes = try container.decodeIfPresent([String].self, forKey: .taskTypes) ?? []
        deliveryMode = try container.decodeIfPresent(String.self, forKey: .deliveryMode) ?? "external"
        projectDir = try container.decodeIfPresent(String.self, forKey: .projectDir)
        ownerAgent = try container.decodeIfPresent(String.self, forKey: .ownerAgent)
        allowedSubtaskAgents = try container.decodeIfPresent([String].self, forKey: .allowedSubtaskAgents) ?? []
        resultReport = try container.decodeIfPresent(String.self, forKey: .resultReport)
        benchmark = try container.decode(TaskQualityBenchmark.self, forKey: .benchmark)
        audit = try container.decode(TaskEvidenceAudit.self, forKey: .audit)
    }

    var releaseReadinessSummary: String {
        let score = benchmark.scenarios.first?.qualityScore ?? benchmark.summary.minQualityScore
        let repairs = benchmark.scenarios.first?.remediationAttempts ?? benchmark.summary.maxRemediationAttempts
        let repairWord = repairs == 1 ? "repair" : "repairs"
        return "\(benchmark.status) · score \(score) · \(repairs) \(repairWord)"
    }

    func isVerifiedForPresentation(resultContract: AcrossVisualResultContract?) -> Bool {
        guard ["passed", "completed"].contains(benchmark.status),
              ["completed", "passed"].contains(taskStatus) else {
            return false
        }
        guard let resultContract else { return true }
        guard resultContract.taskID == taskId else { return false }
        return [AcrossTrustDimension.outcome, .proof, .safety].allSatisfy {
            resultContract.trustCompass.state(for: $0) == .confirmed
        }
    }

    var usesReleaseE2EBenchmark: Bool {
        Set(audit.expectedFiles) == Set(Self.releaseE2EExpectedFiles)
            && Set(audit.requiredProbes) == Set(Self.releaseE2ERequiredProbes)
    }

    static func exportFileName(taskId: String) -> String {
        let cleaned = taskId
            .replacingOccurrences(of: "/", with: "-")
            .replacingOccurrences(of: ":", with: "-")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return "\(cleaned.isEmpty ? "task" : cleaned)-evidence-bundle.json"
    }
}

struct ReleaseE2EScenario: Decodable, Identifiable {
    let id: String
    let title: String
    let summary: String
    let complexityScore: Int
    let requiredFiles: [String]
    let requiredQualityGates: [String]
    let localAgents: [String]
    let cloudAgents: [String]

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case summary
        case complexityScore = "complexity_score"
        case requiredFiles = "required_files"
        case requiredQualityGates = "required_quality_gates"
        case localAgents = "local_agents"
        case cloudAgents = "cloud_agents"
    }
}

struct ReleaseE2EScenarioListResponse: Decodable {
    let scenarios: [ReleaseE2EScenario]
}

struct ReleaseE2ETaskResponse: Decodable {
    let taskId: String
    let status: String
    let message: String
    let scenarioId: String
    let projectDir: String
    let complexityScore: Int
    let requiredFiles: [String]

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case status
        case message
        case scenarioId = "scenario_id"
        case projectDir = "project_dir"
        case complexityScore = "complexity_score"
        case requiredFiles = "required_files"
    }
}
