import Foundation

struct WorkspaceDiffLineAnchor: Codable, Equatable, Hashable {
    let path: String
    let oldLine: Int?
    let newLine: Int?
    let side: String
    let hunk: String?
    let lineText: String?

    enum CodingKeys: String, CodingKey {
        case path
        case oldLine = "old_line"
        case newLine = "new_line"
        case side
        case hunk
        case lineText = "line_text"
    }

    var displayLine: Int? { side == "LEFT" ? oldLine : newLine ?? oldLine }
    var displayText: String { "\(path):\(displayLine.map(String.init) ?? "-")" }
}

struct AgentWorkspaceReviewAnchor: Codable, Equatable, Hashable {
    let baseSha: String
    let headSha: String
    let patchSha256: String

    enum CodingKeys: String, CodingKey {
        case baseSha = "base_sha"
        case headSha = "head_sha"
        case patchSha256 = "patch_sha256"
    }
}

struct AgentWorkspaceReviewComment: Decodable, Equatable, Identifiable {
    let commentId: String
    let candidateId: String
    let createdAt: String?
    let commentDigest: String?
    let commentLength: Int?
    let redacted: Bool

    var id: String { commentId }

    enum CodingKeys: String, CodingKey {
        case commentId = "comment_id"
        case candidateId = "candidate_id"
        case createdAt = "created_at"
        case commentDigest = "comment_digest"
        case commentLength = "comment_length"
        case redacted
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        commentId = try container.decodeIfPresent(String.self, forKey: .commentId) ?? UUID().uuidString
        candidateId = try container.decodeIfPresent(String.self, forKey: .candidateId) ?? "unknown"
        createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
        commentDigest = try container.decodeIfPresent(String.self, forKey: .commentDigest)
        commentLength = try container.decodeIfPresent(Int.self, forKey: .commentLength)
        redacted = try container.decodeIfPresent(Bool.self, forKey: .redacted) ?? true
    }
}

struct AgentWorkspaceLineReviewCommentMetadata: Decodable, Equatable, Identifiable {
    let commentId: String
    let path: String
    let side: String
    let startLine: Int?
    let line: Int
    let bodyDigest: String?
    let bodyLength: Int?
    let redacted: Bool

    var id: String { commentId }
    var displayText: String { "\(path):\(line)" }

    enum CodingKeys: String, CodingKey {
        case commentId = "comment_id"
        case path
        case side
        case startLine = "start_line"
        case line
        case bodyDigest = "body_digest"
        case bodyLength = "body_length"
        case redacted
    }
}

struct AgentWorkspaceLineReviewBatch: Decodable, Equatable, Identifiable {
    let batchId: String
    let candidateId: String
    let createdAt: String?
    let status: String
    let anchor: AgentWorkspaceReviewAnchor
    let comments: [AgentWorkspaceLineReviewCommentMetadata]

    var id: String { batchId }

    enum CodingKeys: String, CodingKey {
        case batchId = "batch_id"
        case candidateId = "candidate_id"
        case createdAt = "created_at"
        case status
        case anchor
        case comments
    }
}

struct AgentWorkspaceRepoAccess: Encodable, Equatable {
    let mode: String
    let securityScopeActive: Bool
    let grantId: String?

    enum CodingKeys: String, CodingKey {
        case mode
        case securityScopeActive = "security_scope_active"
        case grantId = "grant_id"
    }
}

struct AgentWorkspaceAccount: Decodable, Equatable {
    let id: String?
    let displayName: String?
    let plan: String?
    let subscription: String?
    let status: String?

    enum CodingKeys: String, CodingKey {
        case id
        case displayName = "display_name"
        case plan
        case subscription
        case status
    }
}

struct AgentWorkspaceRateLimit: Decodable, Equatable {
    let status: String?
    let limit: Int?
    let remaining: Int?
    let requestsRemaining: Int?
    let tokensRemaining: Int?
    let resetAt: String?
    let retryAfterSeconds: Double?

    enum CodingKeys: String, CodingKey {
        case status
        case limit
        case remaining
        case requestsRemaining = "requests_remaining"
        case tokensRemaining = "tokens_remaining"
        case resetAt = "reset_at"
        case retryAfterSeconds = "retry_after_seconds"
    }
}

struct AgentWorkspaceCreateRequest: Encodable, Equatable {
    let repoRoot: String
    let prompt: String
    let agentIds: [String]
    let executionStrategy: String
    let validationCommands: [[String]]
    let taskTimeoutSeconds: Double
    let testTimeoutSeconds: Double
    let idempotencyKey: String?
    let workflow: String?
    let qualityGateCIPath: String?
    let qualityGateCIWaitSeconds: Int
    let qualityGateDraftPR: Bool
    let repoAccess: AgentWorkspaceRepoAccess?

    enum CodingKeys: String, CodingKey {
        case repoRoot = "repo_root"
        case prompt
        case agentIds = "agent_ids"
        case executionStrategy = "execution_strategy"
        case validationCommands = "validation_commands"
        case taskTimeoutSeconds = "task_timeout_seconds"
        case testTimeoutSeconds = "test_timeout_seconds"
        case idempotencyKey = "idempotency_key"
        case workflow
        case qualityGateCIPath = "quality_gate_ci_path"
        case qualityGateCIWaitSeconds = "quality_gate_ci_wait_seconds"
        case qualityGateDraftPR = "quality_gate_draft_pr"
        case repoAccess = "repo_access"
    }
}

struct AgentWorkspaceCreateDraft: Equatable {
    static let defaultPrompt = "Review this repository, implement the requested bounded improvement, and leave validated changes for human review."
    static let defaultWorkflow = "repo-quality-copilot"
    static let safeValidationCommands = [["git", "diff", "--check"]]

    var repoRoot = ""
    var prompt = defaultPrompt
    var selectedAgentIds: Set<String> = []
    var workflow = defaultWorkflow
    var validationCommands = safeValidationCommands
    var taskTimeoutSeconds = 900.0
    var testTimeoutSeconds = 300.0
    var qualityGateCIPath = ""
    var qualityGateCIWaitSeconds = 30
    var qualityGateDraftPR = false

    var validationError: String? {
        if repoRoot.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return "Repository path is required." }
        if prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return "Prompt is required." }
        if selectedAgentIds.isEmpty || selectedAgentIds.count > 4 { return "Choose between 1 and 4 available agents." }
        if !(0...900).contains(qualityGateCIWaitSeconds) { return "CI wait must be between 0 and 900 seconds." }
        return nil
    }

    func request(idempotencyKey: String? = nil, repoAccess: AgentWorkspaceRepoAccess? = nil) throws -> AgentWorkspaceCreateRequest {
        if let validationError {
            throw OperationsRequestError.invalidInput(validationError)
        }
        return AgentWorkspaceCreateRequest(
            repoRoot: repoRoot.trimmingCharacters(in: .whitespacesAndNewlines),
            prompt: prompt.trimmingCharacters(in: .whitespacesAndNewlines),
            agentIds: selectedAgentIds.sorted(),
            executionStrategy: "parallel_worktrees",
            validationCommands: validationCommands,
            taskTimeoutSeconds: taskTimeoutSeconds,
            testTimeoutSeconds: testTimeoutSeconds,
            idempotencyKey: idempotencyKey,
            workflow: workflow.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
            qualityGateCIPath: qualityGateCIPath.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
            qualityGateCIWaitSeconds: qualityGateCIWaitSeconds,
            qualityGateDraftPR: qualityGateDraftPR,
            repoAccess: repoAccess
        )
    }
}

struct AgentWorkspaceListResponse: Decodable, Equatable {
    let workspaces: [AgentWorkspaceState]
    let count: Int
}

struct AgentWorkspaceState: Decodable, Equatable, Identifiable {
    var id: String { workspaceId }

    let schemaVersion: String?
    let workspaceId: String
    let status: String
    let createdAt: String?
    let updatedAt: String?
    let repoRoot: String
    let baseSha: String?
    let baseBranch: String?
    let executionStrategy: String?
    let workflow: String?
    let agentIds: [String]
    let validationCommands: [[String]]
    let selectedCandidateId: String?
    let candidates: [AgentWorkspaceCandidate]
    let reviewComments: [AgentWorkspaceReviewComment]
    let lineReviewBatches: [AgentWorkspaceLineReviewBatch]
    let promotion: AgentWorkspacePromotion?
    let cleanup: AgentWorkspaceCleanup?
    let cancelRequested: Bool

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case workspaceId = "workspace_id"
        case status
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case repoRoot = "repo_root"
        case baseSha = "base_sha"
        case baseBranch = "base_branch"
        case executionStrategy = "execution_strategy"
        case workflow
        case agentIds = "agent_ids"
        case validationCommands = "validation_commands"
        case selectedCandidateId = "selected_candidate_id"
        case candidates
        case reviewComments = "review_comments"
        case lineReviewBatches = "line_review_batches"
        case promotion
        case cleanup
        case cancelRequested = "cancel_requested"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion)
        workspaceId = try container.decode(String.self, forKey: .workspaceId)
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "unknown"
        createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
        updatedAt = try container.decodeIfPresent(String.self, forKey: .updatedAt)
        repoRoot = try container.decodeIfPresent(String.self, forKey: .repoRoot) ?? ""
        baseSha = try container.decodeIfPresent(String.self, forKey: .baseSha)
        baseBranch = try container.decodeIfPresent(String.self, forKey: .baseBranch)
        executionStrategy = try container.decodeIfPresent(String.self, forKey: .executionStrategy)
        workflow = try container.decodeIfPresent(String.self, forKey: .workflow)
        agentIds = try container.decodeIfPresent([String].self, forKey: .agentIds) ?? []
        validationCommands = try container.decodeIfPresent([[String]].self, forKey: .validationCommands) ?? []
        selectedCandidateId = try container.decodeIfPresent(String.self, forKey: .selectedCandidateId)
        candidates = try container.decodeIfPresent([AgentWorkspaceCandidate].self, forKey: .candidates) ?? []
        reviewComments = try container.decodeIfPresent([AgentWorkspaceReviewComment].self, forKey: .reviewComments) ?? []
        lineReviewBatches = try container.decodeIfPresent([AgentWorkspaceLineReviewBatch].self, forKey: .lineReviewBatches) ?? []
        promotion = try container.decodeIfPresent(AgentWorkspacePromotion.self, forKey: .promotion)
        cleanup = try container.decodeIfPresent(AgentWorkspaceCleanup.self, forKey: .cleanup)
        cancelRequested = try container.decodeIfPresent(Bool.self, forKey: .cancelRequested) ?? false
    }

    var isActive: Bool {
        ["creating", "running", "revising", "cancelling", "promoting"].contains(normalizedStatus)
    }

    var canCancel: Bool {
        ["creating", "running", "revising"].contains(normalizedStatus) && !cancelRequested
    }

    var canCleanup: Bool {
        !isActive && cleanup?.status != "completed"
    }

    private var normalizedStatus: String {
        status.lowercased().replacingOccurrences(of: "-", with: "_")
    }
}

struct AgentWorkspaceCandidate: Decodable, Equatable, Identifiable {
    var id: String { candidateId }

    let candidateId: String
    let agentId: String
    let status: String
    let attempt: Int
    let startedAt: String?
    let completedAt: String?
    let run: AgentWorkspaceCandidateRun?
    let comparison: AgentWorkspaceCandidateComparison
    let evidence: AgentWorkspaceCandidateEvidence

    enum CodingKeys: String, CodingKey {
        case candidateId = "candidate_id"
        case agentId = "agent_id"
        case status
        case attempt
        case startedAt = "started_at"
        case completedAt = "completed_at"
        case run
        case comparison
        case evidence
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        candidateId = try container.decode(String.self, forKey: .candidateId)
        agentId = try container.decodeIfPresent(String.self, forKey: .agentId) ?? "unknown"
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "unknown"
        attempt = try container.decodeIfPresent(Int.self, forKey: .attempt) ?? 1
        startedAt = try container.decodeIfPresent(String.self, forKey: .startedAt)
        completedAt = try container.decodeIfPresent(String.self, forKey: .completedAt)
        run = try container.decodeIfPresent(AgentWorkspaceCandidateRun.self, forKey: .run)
        comparison = try container.decodeIfPresent(AgentWorkspaceCandidateComparison.self, forKey: .comparison) ?? .empty
        evidence = try container.decodeIfPresent(AgentWorkspaceCandidateEvidence.self, forKey: .evidence) ?? .empty
    }

    var canCommentAndRelaunch: Bool {
        ["cancelled", "completed", "failed", "interrupted"].contains(status) && status != "blocked"
    }

    var canSelect: Bool { status == "completed" && evidence.readyForReview }
}

struct AgentWorkspaceCandidateRun: Decodable, Equatable {
    let success: Bool?
    let errorCode: String?
    let elapsedSeconds: Double?
    let outputBytes: Int?
    let outputSha256: String?
    let provider: String?
    let model: String?
    let usage: AgentWorkspaceUsage?
    let account: AgentWorkspaceAccount?
    let rateLimit: AgentWorkspaceRateLimit?
    let toolCalls: [String]
    let evidenceLinks: [String]
    let transcriptPersisted: Bool

    enum CodingKeys: String, CodingKey {
        case success
        case errorCode = "error_code"
        case elapsedSeconds = "elapsed_seconds"
        case outputBytes = "output_bytes"
        case outputSha256 = "output_sha256"
        case provider
        case model
        case usage
        case account
        case rateLimit = "rate_limit"
        case toolCalls = "tool_calls"
        case evidenceLinks = "evidence_links"
        case transcriptPersisted = "transcript_persisted"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        success = try container.decodeIfPresent(Bool.self, forKey: .success)
        errorCode = try container.decodeIfPresent(String.self, forKey: .errorCode)
        elapsedSeconds = try container.decodeIfPresent(Double.self, forKey: .elapsedSeconds)
        outputBytes = try container.decodeIfPresent(Int.self, forKey: .outputBytes)
        outputSha256 = try container.decodeIfPresent(String.self, forKey: .outputSha256)
        provider = try container.decodeIfPresent(String.self, forKey: .provider)
        model = try container.decodeIfPresent(String.self, forKey: .model)
        usage = try container.decodeIfPresent(AgentWorkspaceUsage.self, forKey: .usage)
        account = try container.decodeIfPresent(AgentWorkspaceAccount.self, forKey: .account)
        rateLimit = try container.decodeIfPresent(AgentWorkspaceRateLimit.self, forKey: .rateLimit)
        toolCalls = try container.decodeIfPresent([String].self, forKey: .toolCalls) ?? []
        evidenceLinks = try container.decodeIfPresent([String].self, forKey: .evidenceLinks) ?? []
        transcriptPersisted = try container.decodeIfPresent(Bool.self, forKey: .transcriptPersisted) ?? false
    }
}

struct AgentWorkspaceUsage: Decodable, Equatable {
    let inputTokens: Int?
    let outputTokens: Int?
    let totalTokens: Int?

    enum CodingKeys: String, CodingKey {
        case inputTokens = "input_tokens"
        case outputTokens = "output_tokens"
        case totalTokens = "total_tokens"
    }
}

struct AgentWorkspaceCandidateComparison: Decodable, Equatable {
    static let empty = AgentWorkspaceCandidateComparison()

    let changedFiles: [String]
    let diff: AgentWorkspaceDiffSummary
    let patchAvailable: Bool
    let patchSha256: String?
    let headSha: String?
    let reviewAnchor: AgentWorkspaceReviewAnchor?
    let tests: AgentWorkspaceTests
    let qualityGate: AgentWorkspaceEmbeddedGate
    let risk: AgentWorkspaceRisk
    let conflicts: AgentWorkspaceConflicts

    enum CodingKeys: String, CodingKey {
        case changedFiles = "changed_files"
        case diff
        case patchAvailable = "patch_available"
        case patchSha256 = "patch_sha256"
        case headSha = "head_sha"
        case reviewAnchor = "review_anchor"
        case tests
        case qualityGate = "quality_gate"
        case risk
        case conflicts
    }

    init(
        changedFiles: [String] = [],
        diff: AgentWorkspaceDiffSummary = .init(),
        patchAvailable: Bool = false,
        patchSha256: String? = nil,
        headSha: String? = nil,
        reviewAnchor: AgentWorkspaceReviewAnchor? = nil,
        tests: AgentWorkspaceTests = .init(),
        qualityGate: AgentWorkspaceEmbeddedGate = .init(),
        risk: AgentWorkspaceRisk = .init(),
        conflicts: AgentWorkspaceConflicts = .init()
    ) {
        self.changedFiles = changedFiles
        self.diff = diff
        self.patchAvailable = patchAvailable
        self.patchSha256 = patchSha256
        self.headSha = headSha
        self.reviewAnchor = reviewAnchor
        self.tests = tests
        self.qualityGate = qualityGate
        self.risk = risk
        self.conflicts = conflicts
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            changedFiles: try container.decodeIfPresent([String].self, forKey: .changedFiles) ?? [],
            diff: try container.decodeIfPresent(AgentWorkspaceDiffSummary.self, forKey: .diff) ?? .init(),
            patchAvailable: try container.decodeIfPresent(Bool.self, forKey: .patchAvailable) ?? false,
            patchSha256: try container.decodeIfPresent(String.self, forKey: .patchSha256),
            headSha: try container.decodeIfPresent(String.self, forKey: .headSha),
            reviewAnchor: try container.decodeIfPresent(AgentWorkspaceReviewAnchor.self, forKey: .reviewAnchor),
            tests: try container.decodeIfPresent(AgentWorkspaceTests.self, forKey: .tests) ?? .init(),
            qualityGate: try container.decodeIfPresent(AgentWorkspaceEmbeddedGate.self, forKey: .qualityGate) ?? .init(),
            risk: try container.decodeIfPresent(AgentWorkspaceRisk.self, forKey: .risk) ?? .init(),
            conflicts: try container.decodeIfPresent(AgentWorkspaceConflicts.self, forKey: .conflicts) ?? .init()
        )
    }
}

struct AgentWorkspaceDiffSummary: Decodable, Equatable {
    let filesChanged: Int
    let insertions: Int
    let deletions: Int
    let binaryFiles: Int

    enum CodingKeys: String, CodingKey {
        case filesChanged = "files_changed"
        case insertions
        case deletions
        case binaryFiles = "binary_files"
    }

    init(filesChanged: Int = 0, insertions: Int = 0, deletions: Int = 0, binaryFiles: Int = 0) {
        self.filesChanged = filesChanged
        self.insertions = insertions
        self.deletions = deletions
        self.binaryFiles = binaryFiles
    }
}

struct AgentWorkspaceTests: Decodable, Equatable {
    let status: String
    let configuredCount: Int
    let completedCount: Int
    let results: [AgentWorkspaceTestResult]

    enum CodingKeys: String, CodingKey {
        case status
        case configuredCount = "configured_count"
        case completedCount = "completed_count"
        case results
    }

    init(status: String = "not_run", configuredCount: Int = 0, completedCount: Int = 0, results: [AgentWorkspaceTestResult] = []) {
        self.status = status
        self.configuredCount = configuredCount
        self.completedCount = completedCount
        self.results = results
    }
}

struct AgentWorkspaceTestResult: Decodable, Equatable, Identifiable {
    var id: Int { index }
    let index: Int
    let command: [String]
    let status: String
    let exitCode: Int?
    let elapsedSeconds: Double?
    let stdoutBytes: Int
    let stderrBytes: Int
    let outputPersisted: Bool

    enum CodingKeys: String, CodingKey {
        case index
        case command
        case status
        case exitCode = "exit_code"
        case elapsedSeconds = "elapsed_seconds"
        case stdoutBytes = "stdout_bytes"
        case stderrBytes = "stderr_bytes"
        case outputPersisted = "output_persisted"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        index = try container.decodeIfPresent(Int.self, forKey: .index) ?? 0
        command = try container.decodeIfPresent([String].self, forKey: .command) ?? []
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "unknown"
        exitCode = try container.decodeIfPresent(Int.self, forKey: .exitCode)
        elapsedSeconds = try container.decodeIfPresent(Double.self, forKey: .elapsedSeconds)
        stdoutBytes = try container.decodeIfPresent(Int.self, forKey: .stdoutBytes) ?? 0
        stderrBytes = try container.decodeIfPresent(Int.self, forKey: .stderrBytes) ?? 0
        outputPersisted = try container.decodeIfPresent(Bool.self, forKey: .outputPersisted) ?? false
    }
}

struct AgentWorkspaceEmbeddedGate: Decodable, Equatable {
    let required: Bool
    let status: String
    let gateVerdict: String?
    let findings: [QualityGateFinding]
    let evidenceHash: String?
    let prReadySummary: String?
    let evidenceRoutes: [String]

    enum CodingKeys: String, CodingKey {
        case required
        case status
        case gateVerdict = "gate_verdict"
        case findings
        case evidenceHash = "evidence_hash"
        case prReadySummary = "pr_ready_summary"
        case evidenceRoutes = "evidence_routes"
    }

    init(required: Bool = false, status: String = "not_requested", gateVerdict: String? = nil, findings: [QualityGateFinding] = [], evidenceHash: String? = nil, prReadySummary: String? = nil, evidenceRoutes: [String] = []) {
        self.required = required
        self.status = status
        self.gateVerdict = gateVerdict
        self.findings = findings
        self.evidenceHash = evidenceHash
        self.prReadySummary = prReadySummary
        self.evidenceRoutes = evidenceRoutes
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            required: try container.decodeIfPresent(Bool.self, forKey: .required) ?? false,
            status: try container.decodeIfPresent(String.self, forKey: .status) ?? "not_requested",
            gateVerdict: try container.decodeIfPresent(String.self, forKey: .gateVerdict),
            findings: try container.decodeIfPresent([QualityGateFinding].self, forKey: .findings) ?? [],
            evidenceHash: try container.decodeIfPresent(String.self, forKey: .evidenceHash),
            prReadySummary: try container.decodeIfPresent(String.self, forKey: .prReadySummary),
            evidenceRoutes: try container.decodeIfPresent([String].self, forKey: .evidenceRoutes) ?? []
        )
    }
}

struct AgentWorkspaceRisk: Decodable, Equatable {
    let level: String
    let blocking: Bool
    let findings: [QualityGateFinding]

    init(level: String = "unknown", blocking: Bool = false, findings: [QualityGateFinding] = []) {
        self.level = level
        self.blocking = blocking
        self.findings = findings
    }
}

struct AgentWorkspaceConflicts: Decodable, Equatable {
    let status: String
    let checkedAt: String?

    enum CodingKeys: String, CodingKey {
        case status
        case checkedAt = "checked_at"
    }

    init(status: String = "not_checked", checkedAt: String? = nil) {
        self.status = status
        self.checkedAt = checkedAt
    }
}

struct AgentWorkspaceCandidateEvidence: Decodable, Equatable {
    static let empty = AgentWorkspaceCandidateEvidence()

    let schemaVersion: String?
    let generatedAt: String?
    let baseSha: String?
    let patchSha256: String?
    let evidenceSha256: String?
    let changedFilesValidated: Bool
    let diffValidated: Bool
    let testsValidated: Bool
    let qualityGateValidated: Bool
    let riskValidated: Bool
    let conflictsValidated: Bool
    let humanApprovalRequired: Bool
    let readyForReview: Bool
    let blockingReasons: [String]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case generatedAt = "generated_at"
        case baseSha = "base_sha"
        case patchSha256 = "patch_sha256"
        case evidenceSha256 = "evidence_sha256"
        case changedFilesValidated = "changed_files_validated"
        case diffValidated = "diff_validated"
        case testsValidated = "tests_validated"
        case qualityGateValidated = "quality_gate_validated"
        case riskValidated = "risk_validated"
        case conflictsValidated = "conflicts_validated"
        case humanApprovalRequired = "human_approval_required"
        case readyForReview = "ready_for_review"
        case blockingReasons = "blocking_reasons"
    }

    init(
        schemaVersion: String? = nil,
        generatedAt: String? = nil,
        baseSha: String? = nil,
        patchSha256: String? = nil,
        evidenceSha256: String? = nil,
        changedFilesValidated: Bool = false,
        diffValidated: Bool = false,
        testsValidated: Bool = false,
        qualityGateValidated: Bool = false,
        riskValidated: Bool = false,
        conflictsValidated: Bool = false,
        humanApprovalRequired: Bool = true,
        readyForReview: Bool = false,
        blockingReasons: [String] = []
    ) {
        self.schemaVersion = schemaVersion
        self.generatedAt = generatedAt
        self.baseSha = baseSha
        self.patchSha256 = patchSha256
        self.evidenceSha256 = evidenceSha256
        self.changedFilesValidated = changedFilesValidated
        self.diffValidated = diffValidated
        self.testsValidated = testsValidated
        self.qualityGateValidated = qualityGateValidated
        self.riskValidated = riskValidated
        self.conflictsValidated = conflictsValidated
        self.humanApprovalRequired = humanApprovalRequired
        self.readyForReview = readyForReview
        self.blockingReasons = blockingReasons
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            schemaVersion: try container.decodeIfPresent(String.self, forKey: .schemaVersion),
            generatedAt: try container.decodeIfPresent(String.self, forKey: .generatedAt),
            baseSha: try container.decodeIfPresent(String.self, forKey: .baseSha),
            patchSha256: try container.decodeIfPresent(String.self, forKey: .patchSha256),
            evidenceSha256: try container.decodeIfPresent(String.self, forKey: .evidenceSha256),
            changedFilesValidated: try container.decodeIfPresent(Bool.self, forKey: .changedFilesValidated) ?? false,
            diffValidated: try container.decodeIfPresent(Bool.self, forKey: .diffValidated) ?? false,
            testsValidated: try container.decodeIfPresent(Bool.self, forKey: .testsValidated) ?? false,
            qualityGateValidated: try container.decodeIfPresent(Bool.self, forKey: .qualityGateValidated) ?? false,
            riskValidated: try container.decodeIfPresent(Bool.self, forKey: .riskValidated) ?? false,
            conflictsValidated: try container.decodeIfPresent(Bool.self, forKey: .conflictsValidated) ?? false,
            humanApprovalRequired: try container.decodeIfPresent(Bool.self, forKey: .humanApprovalRequired) ?? true,
            readyForReview: try container.decodeIfPresent(Bool.self, forKey: .readyForReview) ?? false,
            blockingReasons: try container.decodeIfPresent([String].self, forKey: .blockingReasons) ?? []
        )
    }
}

struct AgentWorkspacePromotion: Decodable, Equatable {
    let status: String
    let approved: Bool
    let approvedBy: String?
    let approvedAt: String?
    let candidateId: String?
    let promotedAt: String?

    enum CodingKeys: String, CodingKey {
        case status
        case approved
        case approvedBy = "approved_by"
        case approvedAt = "approved_at"
        case candidateId = "candidate_id"
        case promotedAt = "promoted_at"
    }
}

struct AgentWorkspaceCleanup: Decodable, Equatable {
    let status: String
    let completedAt: String?

    enum CodingKeys: String, CodingKey {
        case status
        case completedAt = "completed_at"
    }
}

struct AgentWorkspaceComparisonResponse: Decodable, Equatable {
    let workspaceId: String
    let baseSha: String?
    let status: String
    let selectedCandidateId: String?
    let candidates: [AgentWorkspaceComparisonCandidate]

    enum CodingKeys: String, CodingKey {
        case workspaceId = "workspace_id"
        case baseSha = "base_sha"
        case status
        case selectedCandidateId = "selected_candidate_id"
        case candidates
    }
}

struct AgentWorkspaceComparisonCandidate: Decodable, Equatable, Identifiable {
    var id: String { candidateId }
    let candidateId: String
    let agentId: String
    let status: String
    let selected: Bool
    let comparison: AgentWorkspaceCandidateComparison
    let evidence: AgentWorkspaceCandidateEvidence
    let diff: String?

    enum CodingKeys: String, CodingKey {
        case candidateId = "candidate_id"
        case agentId = "agent_id"
        case status
        case selected
        case comparison
        case evidence
        case diff
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        candidateId = try container.decode(String.self, forKey: .candidateId)
        agentId = try container.decodeIfPresent(String.self, forKey: .agentId) ?? "unknown"
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "unknown"
        selected = try container.decodeIfPresent(Bool.self, forKey: .selected) ?? false
        comparison = try container.decodeIfPresent(AgentWorkspaceCandidateComparison.self, forKey: .comparison) ?? .empty
        evidence = try container.decodeIfPresent(AgentWorkspaceCandidateEvidence.self, forKey: .evidence) ?? .empty
        diff = try container.decodeIfPresent(String.self, forKey: .diff).map { String($0.prefix(64_000)) }
    }
}

struct AgentWorkspaceEventsResponse: Decodable, Equatable {
    let workspaceId: String
    let workspaceStatus: String
    let events: [AgentWorkspaceEvent]
    let lastSequence: Int

    enum CodingKeys: String, CodingKey {
        case workspaceId = "workspace_id"
        case workspaceStatus = "workspace_status"
        case events
        case lastSequence = "last_sequence"
    }
}

struct AgentWorkspaceEvent: Decodable, Equatable, Identifiable {
    var id: Int { sequence }
    let sequence: Int
    let timestamp: String?
    let type: String
    let workspaceId: String
    let candidateId: String?
    let data: [String: OperationsJSONValue]

    enum CodingKeys: String, CodingKey {
        case sequence
        case timestamp
        case type
        case workspaceId = "workspace_id"
        case candidateId = "candidate_id"
        case data
    }

    var boundedSummary: String {
        String(data.keys.sorted().map { "\($0)=\(data[$0]?.displayText ?? "-")" }.joined(separator: " · ").prefix(2_000))
    }
}

struct AgentWorkspaceCancelRequest: Encodable, Equatable { let reason: String? }

struct AgentWorkspaceCommentRequest: Encodable, Equatable {
    let candidateId: String
    let comment: String
    enum CodingKeys: String, CodingKey { case candidateId = "candidate_id"; case comment }
}

struct AgentWorkspaceLineCommentRequest: Encodable, Equatable {
    let path: String
    let side: String
    let line: Int
    let startLine: Int?
    let body: String

    enum CodingKeys: String, CodingKey {
        case path
        case side
        case line
        case startLine = "start_line"
        case body
    }
}

struct AgentWorkspaceLineReviewRequest: Encodable, Equatable {
    let candidateId: String
    let anchor: AgentWorkspaceReviewAnchor
    let comments: [AgentWorkspaceLineCommentRequest]
    let idempotencyKey: String?

    enum CodingKeys: String, CodingKey {
        case candidateId = "candidate_id"
        case anchor
        case comments
        case idempotencyKey = "idempotency_key"
    }
}

struct AgentWorkspaceSelectRequest: Encodable, Equatable {
    let candidateId: String
    enum CodingKeys: String, CodingKey { case candidateId = "candidate_id" }
}

struct AgentWorkspacePromoteRequest: Encodable, Equatable {
    let candidateId: String
    let approved: Bool
    let approvedBy: String
    enum CodingKeys: String, CodingKey {
        case candidateId = "candidate_id"
        case approved
        case approvedBy = "approved_by"
    }
}

// Unified diff review models live with the workspace API contract so the
// standalone behavior harness exercises the same parser as the app.
enum WorkspaceDiffLineKind: String, Codable, Equatable {
    case context
    case addition
    case deletion
    case metadata
}

struct WorkspaceDiffLine: Equatable, Identifiable {
    let id: Int
    let kind: WorkspaceDiffLineKind
    let text: String
    let oldLine: Int?
    let newLine: Int?
    let anchor: WorkspaceDiffLineAnchor?
}

struct WorkspaceDiffFile: Equatable, Identifiable {
    let path: String
    let lines: [WorkspaceDiffLine]
    var id: String { path }
}

enum WorkspaceUnifiedDiffParser {
    static func parse(_ patch: String) -> [WorkspaceDiffFile] {
        var files: [WorkspaceDiffFile] = []
        var path: String?
        var oldPath: String?
        var newPath: String?
        var lines: [WorkspaceDiffLine] = []
        var oldLine: Int?
        var newLine: Int?
        var hunk: String?
        var sequence = 0

        func flush() {
            guard let path else { return }
            files.append(WorkspaceDiffFile(path: path, lines: lines))
            lines = []
        }

        for rawLine in patch.split(separator: "\n", omittingEmptySubsequences: false).map(String.init) {
            if rawLine.hasPrefix("diff --git ") {
                flush()
                path = parsePath(fromDiffHeader: rawLine)
                oldPath = nil
                newPath = path
                oldLine = nil
                newLine = nil
                hunk = nil
                continue
            }
            if rawLine.hasPrefix("--- ") {
                oldPath = parseMarkerPath(rawLine)
                continue
            }
            if rawLine.hasPrefix("+++ ") {
                newPath = parseMarkerPath(rawLine)
                if let newPath { path = newPath }
                continue
            }
            if rawLine.hasPrefix("@@"), let ranges = parseHunkRanges(rawLine) {
                oldLine = ranges.old
                newLine = ranges.new
                hunk = String(rawLine.prefix(500))
                lines.append(.init(id: sequence, kind: .metadata, text: rawLine, oldLine: nil, newLine: nil, anchor: nil))
                sequence += 1
                continue
            }

            guard let currentPath = path else { continue }
            let kind: WorkspaceDiffLineKind
            let currentOld: Int?
            let currentNew: Int?
            let side: String?

            if rawLine.hasPrefix("+") && !rawLine.hasPrefix("+++") {
                kind = .addition
                currentOld = nil
                currentNew = newLine
                side = "RIGHT"
                if newLine != nil { newLine! += 1 }
            } else if rawLine.hasPrefix("-") && !rawLine.hasPrefix("---") {
                kind = .deletion
                currentOld = oldLine
                currentNew = nil
                side = "LEFT"
                if oldLine != nil { oldLine! += 1 }
            } else if rawLine.hasPrefix(" ") {
                kind = .context
                currentOld = oldLine
                currentNew = newLine
                side = "RIGHT"
                if oldLine != nil { oldLine! += 1 }
                if newLine != nil { newLine! += 1 }
            } else {
                kind = .metadata
                currentOld = nil
                currentNew = nil
                side = nil
            }

            let anchor = side.map {
                WorkspaceDiffLineAnchor(
                    path: $0 == "LEFT" ? (oldPath ?? currentPath) : (newPath ?? currentPath),
                    oldLine: currentOld,
                    newLine: currentNew,
                    side: $0,
                    hunk: hunk,
                    lineText: String(rawLine.dropFirst().prefix(500))
                )
            }
            lines.append(.init(id: sequence, kind: kind, text: rawLine, oldLine: currentOld, newLine: currentNew, anchor: anchor))
            sequence += 1
        }
        flush()
        return files
    }

    private static func parsePath(fromDiffHeader line: String) -> String? {
        guard let marker = line.range(of: " b/") else { return nil }
        return normalizedPath(String(line[marker.upperBound...]))
    }

    private static func parseMarkerPath(_ line: String) -> String? {
        let value = String(line.dropFirst(4))
        guard value != "/dev/null" else { return nil }
        return normalizedPath(value)
    }

    private static func normalizedPath(_ value: String) -> String {
        let unquoted = value.trimmingCharacters(in: CharacterSet(charactersIn: "\""))
        if unquoted.hasPrefix("a/") || unquoted.hasPrefix("b/") {
            return String(unquoted.dropFirst(2))
        }
        return unquoted
    }

    private static func parseHunkRanges(_ line: String) -> (old: Int, new: Int)? {
        let parts = line.split(separator: " ")
        guard parts.count >= 3,
              let old = rangeStart(String(parts[1]), prefix: "-"),
              let new = rangeStart(String(parts[2]), prefix: "+") else { return nil }
        return (old, new)
    }

    private static func rangeStart(_ value: String, prefix: Character) -> Int? {
        guard value.first == prefix else { return nil }
        return Int(value.dropFirst().split(separator: ",", maxSplits: 1).first ?? "")
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
