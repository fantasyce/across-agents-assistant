import Foundation

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
    let remediations: [String]
    let reportFiles: ReleaseVerificationReportFiles
    let audit: ReleaseVerificationAudit

    var id: String {
        "release-verification-\(generatedAt)"
    }

    var primaryRemediation: String? {
        remediations.first
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
        case remediations
        case reportFiles = "report_files"
        case audit
    }
}
