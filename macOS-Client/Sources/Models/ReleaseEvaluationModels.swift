import Foundation

struct ReleaseEvaluationRisk: Decodable, Identifiable {
    let kind: String
    let severity: String
    let count: Int?
    let message: String

    var id: String { "\(kind)-\(severity)-\(message)" }
}

struct ReleaseEvaluationRecentTask: Decodable, Identifiable {
    let taskId: String
    let description: String
    let status: String
    let qualityGate: String?
    let finalQualityScore: Int?

    var id: String { taskId }

    enum CodingKeys: String, CodingKey {
        case taskId = "task_id"
        case description
        case status
        case qualityGate = "quality_gate"
        case finalQualityScore = "final_quality_score"
    }
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
    }

    var passRatePercent: Int {
        Int((passRate * 100).rounded())
    }

    var primaryRiskMessage: String? {
        topRisks.first?.message ?? recommendation
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
