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

struct ReleaseEvaluationReadinessCheck: Decodable, Identifiable {
    let id: String
    let status: String
    let label: String
    let message: String
    let severity: String
}

struct ReleaseEvaluationSummary: Decodable {
    let releaseReadiness: String
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
    let readinessChecks: [ReleaseEvaluationReadinessCheck]

    enum CodingKeys: String, CodingKey {
        case releaseReadiness = "release_readiness"
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
        case readinessChecks = "readiness_checks"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        releaseReadiness = try container.decode(String.self, forKey: .releaseReadiness)
        evaluatedTaskCount = try container.decodeIfPresent(Int.self, forKey: .evaluatedTaskCount) ?? 0
        terminalTaskCount = try container.decodeIfPresent(Int.self, forKey: .terminalTaskCount) ?? 0
        passedTaskCount = try container.decodeIfPresent(Int.self, forKey: .passedTaskCount) ?? 0
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
        readinessChecks = try container.decodeIfPresent([ReleaseEvaluationReadinessCheck].self, forKey: .readinessChecks) ?? []
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
