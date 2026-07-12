import Foundation

struct QualityGateRunRequest: Encodable, Equatable {
    let repoRoot: String
    let baseRef: String?
    let headRef: String?
    let branch: String?
    let commit: String?
    let ciPath: String?
    let ciWaitSeconds: Int
    let draftPR: Bool
    let maxRepairs: Int
    let timeoutSeconds: Int
    let pushBranch: Bool?
    let approveRemote: Bool?
    let watchCI: Bool?
    let ciIdleTimeoutSeconds: Int?
    let ciMaxWallTimeoutSeconds: Int?

    enum CodingKeys: String, CodingKey {
        case repoRoot = "repo_root"
        case baseRef = "base_ref"
        case headRef = "head_ref"
        case branch
        case commit
        case ciPath = "ci_path"
        case ciWaitSeconds = "ci_wait_seconds"
        case draftPR = "draft_pr"
        case maxRepairs = "max_repairs"
        case timeoutSeconds = "timeout_seconds"
        case pushBranch = "push_branch"
        case approveRemote = "approve_remote"
        case watchCI = "watch_ci"
        case ciIdleTimeoutSeconds = "ci_idle_timeout_seconds"
        case ciMaxWallTimeoutSeconds = "ci_max_wall_timeout_seconds"
    }
}

enum QualityGateOperationMode: String, CaseIterable, Identifiable, Equatable {
    case localReadOnly = "local_read_only"
    case approvedRemoteDraftPR = "approved_remote_draft_pr"

    var id: String { rawValue }
    var requiresRemoteConfirmation: Bool { self == .approvedRemoteDraftPR }
}

struct QualityGateRunDraft: Equatable {
    var repoRoot = ""
    var baseRef = "main"
    var headRef = "HEAD"
    var branch = ""
    var commit = ""
    var ciPath = ""
    var ciWaitSeconds = 30
    var maxRepairs = 0
    var draftPR = false
    var timeoutSeconds = 900
    var operationMode = QualityGateOperationMode.localReadOnly
    var watchCI = true
    var ciIdleTimeoutSeconds = 900
    var ciMaxWallTimeoutSeconds = 7_200

    var validationError: String? {
        if repoRoot.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return "Repository path is required." }
        if !(0...900).contains(ciWaitSeconds) { return "CI wait must be between 0 and 900 seconds." }
        if !(0...10).contains(maxRepairs) { return "Maximum repairs must be between 0 and 10." }
        if operationMode.requiresRemoteConfirmation {
            let normalizedBranch = branch.trimmingCharacters(in: .whitespacesAndNewlines)
            let normalizedBase = baseRef.trimmingCharacters(in: .whitespacesAndNewlines)
            if normalizedBranch.isEmpty { return "A named feature branch is required for remote mode." }
            if ["HEAD", "main", "master", normalizedBase].contains(normalizedBranch) {
                return "Remote mode requires a feature branch distinct from the base branch."
            }
            if !(30...7_200).contains(ciIdleTimeoutSeconds) {
                return "CI idle timeout must be between 30 seconds and 2 hours."
            }
            if !(60...14_400).contains(ciMaxWallTimeoutSeconds) {
                return "CI maximum wall time must be between 1 and 4 hours."
            }
            if ciIdleTimeoutSeconds > ciMaxWallTimeoutSeconds {
                return "CI idle timeout cannot exceed maximum wall time."
            }
        }
        return nil
    }

    func request() throws -> QualityGateRunRequest {
        if let validationError {
            throw OperationsRequestError.invalidInput(validationError)
        }
        let isRemote = operationMode.requiresRemoteConfirmation
        return QualityGateRunRequest(
            repoRoot: repoRoot.trimmingCharacters(in: .whitespacesAndNewlines),
            baseRef: baseRef.trimmedNil,
            headRef: headRef.trimmedNil,
            branch: branch.trimmedNil,
            commit: commit.trimmedNil,
            ciPath: ciPath.trimmedNil,
            ciWaitSeconds: ciWaitSeconds,
            draftPR: isRemote ? true : draftPR,
            maxRepairs: maxRepairs,
            timeoutSeconds: timeoutSeconds,
            pushBranch: isRemote ? true : nil,
            approveRemote: isRemote ? true : nil,
            watchCI: isRemote ? watchCI : nil,
            ciIdleTimeoutSeconds: isRemote && watchCI ? ciIdleTimeoutSeconds : nil,
            ciMaxWallTimeoutSeconds: isRemote && watchCI ? ciMaxWallTimeoutSeconds : nil
        )
    }
}

struct QualityGateResult: Decodable, Equatable {
    let schemaVersion: String?
    let status: String?
    let repository: QualityGateRepository?
    let baseRef: String?
    let headRef: String?
    let headSha: String?
    let dirtyTree: Bool
    let findings: [QualityGateFinding]
    let gateVerdict: String
    let evidenceHash: String?
    let prReadySummary: String?
    let checks: QualityGateChecks?
    let repairPlan: QualityGateRepairPlan?
    let ci: QualityGateCI?
    let draftPR: QualityGateDraftPRPlan?
    let gitBinding: QualityGateGitBinding?
    let pushReceipt: QualityGatePushReceipt?
    let githubReview: QualityGateGitHubReview?
    let githubRemote: QualityGateGitHubRemote?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case status
        case repository
        case baseRef = "base_ref"
        case headRef = "head_ref"
        case headSha = "head_sha"
        case dirtyTree = "dirty_tree"
        case findings
        case gateVerdict = "gate_verdict"
        case evidenceHash = "evidence_hash"
        case prReadySummary = "pr_ready_summary"
        case checks
        case repairPlan = "repair_plan"
        case ci
        case draftPR = "draft_pr"
        case gitBinding = "git_binding"
        case pushReceipt = "push_receipt"
        case githubReview = "github_review"
        case githubRemote = "github_remote"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion)
        status = try container.decodeIfPresent(String.self, forKey: .status)
        repository = try container.decodeIfPresent(QualityGateRepository.self, forKey: .repository)
        baseRef = try container.decodeIfPresent(String.self, forKey: .baseRef)
        headRef = try container.decodeIfPresent(String.self, forKey: .headRef)
        headSha = try container.decodeIfPresent(String.self, forKey: .headSha)
        dirtyTree = try container.decodeIfPresent(Bool.self, forKey: .dirtyTree) ?? false
        findings = try container.decodeIfPresent([QualityGateFinding].self, forKey: .findings) ?? []
        gateVerdict = try container.decodeIfPresent(String.self, forKey: .gateVerdict) ?? "unknown"
        evidenceHash = try container.decodeIfPresent(String.self, forKey: .evidenceHash)
        prReadySummary = try container.decodeIfPresent(String.self, forKey: .prReadySummary)
        checks = try container.decodeIfPresent(QualityGateChecks.self, forKey: .checks)
        repairPlan = try container.decodeIfPresent(QualityGateRepairPlan.self, forKey: .repairPlan)
        ci = try container.decodeIfPresent(QualityGateCI.self, forKey: .ci)
        draftPR = try container.decodeIfPresent(QualityGateDraftPRPlan.self, forKey: .draftPR)
        gitBinding = try container.decodeIfPresent(QualityGateGitBinding.self, forKey: .gitBinding)
        pushReceipt = try container.decodeIfPresent(QualityGatePushReceipt.self, forKey: .pushReceipt)
        githubReview = try container.decodeIfPresent(QualityGateGitHubReview.self, forKey: .githubReview)
        githubRemote = try container.decodeIfPresent(QualityGateGitHubRemote.self, forKey: .githubRemote)
    }

    var isBlocked: Bool {
        ["blocked", "fail", "failed"].contains(gateVerdict.lowercased())
    }
}

enum QualityGateRepository: Decodable, Equatable {
    case name(String)
    case details(name: String?, path: String?)

    private enum CodingKeys: String, CodingKey { case name; case path }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let value = try? container.decode(String.self) {
            self = .name(value)
            return
        }
        let keyed = try decoder.container(keyedBy: CodingKeys.self)
        self = .details(
            name: try keyed.decodeIfPresent(String.self, forKey: .name),
            path: try keyed.decodeIfPresent(String.self, forKey: .path)
        )
    }

    var displayText: String {
        switch self {
        case .name(let value): return value
        case .details(let name, let path): return path ?? name ?? "-"
        }
    }
}

struct QualityGateFinding: Decodable, Equatable, Identifiable {
    let id: String
    let state: String
    let severity: String
    let summary: String?
    let suggestedAction: String?
    let owner: String?
    let sourceGate: String?

    enum CodingKeys: String, CodingKey {
        case id
        case state
        case severity
        case summary
        case suggestedAction = "suggested_action"
        case owner
        case sourceGate = "source_gate"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(String.self, forKey: .id) ?? "finding"
        state = try container.decodeIfPresent(String.self, forKey: .state) ?? "unknown"
        severity = try container.decodeIfPresent(String.self, forKey: .severity) ?? state
        summary = try container.decodeIfPresent(String.self, forKey: .summary)
        suggestedAction = try container.decodeIfPresent(String.self, forKey: .suggestedAction)
        owner = try container.decodeIfPresent(String.self, forKey: .owner)
        sourceGate = try container.decodeIfPresent(String.self, forKey: .sourceGate)
    }
}

struct QualityGateChecks: Decodable, Equatable {
    let commands: [QualityGateCheck]
    let tools: [QualityGateCheck]
    let policies: [String: OperationsJSONValue]

    init(from decoder: Decoder) throws {
        enum CodingKeys: String, CodingKey { case commands; case tools; case policies }
        let container = try decoder.container(keyedBy: CodingKeys.self)
        commands = try container.decodeIfPresent([QualityGateCheck].self, forKey: .commands) ?? []
        tools = try container.decodeIfPresent([QualityGateCheck].self, forKey: .tools) ?? []
        policies = try container.decodeIfPresent([String: OperationsJSONValue].self, forKey: .policies) ?? [:]
    }
}

struct QualityGateCheck: Decodable, Equatable, Identifiable {
    let id: String
    let category: String?
    let status: String
    let reason: String?
    let available: Bool?
    let argv: [String]

    init(from decoder: Decoder) throws {
        enum CodingKeys: String, CodingKey { case id; case category; case status; case reason; case available; case argv }
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(String.self, forKey: .id) ?? "check"
        category = try container.decodeIfPresent(String.self, forKey: .category)
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "unknown"
        reason = try container.decodeIfPresent(String.self, forKey: .reason)
        available = try container.decodeIfPresent(Bool.self, forKey: .available)
        argv = try container.decodeIfPresent([String].self, forKey: .argv) ?? []
    }
}

struct QualityGateRepairPlan: Decodable, Equatable {
    let schemaVersion: String?
    let status: String
    let mutationPerformed: Bool
    let currentRound: Int
    let maxRounds: Int
    let maxActions: Int
    let actions: [QualityGateRepairAction]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case status
        case mutationPerformed = "mutation_performed"
        case currentRound = "current_round"
        case maxRounds = "max_rounds"
        case maxActions = "max_actions"
        case actions
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion)
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "not_needed"
        mutationPerformed = try container.decodeIfPresent(Bool.self, forKey: .mutationPerformed) ?? false
        currentRound = try container.decodeIfPresent(Int.self, forKey: .currentRound) ?? 0
        maxRounds = try container.decodeIfPresent(Int.self, forKey: .maxRounds) ?? 0
        maxActions = try container.decodeIfPresent(Int.self, forKey: .maxActions) ?? 0
        actions = try container.decodeIfPresent([QualityGateRepairAction].self, forKey: .actions) ?? []
    }
}

struct QualityGateRepairAction: Decodable, Equatable, Identifiable {
    let id: String
    let category: String
    let sourceFindingIds: [String]
    let suggestedAction: String?
    let remainingRounds: Int?
    let execution: String
    let commandSource: String?

    enum CodingKeys: String, CodingKey {
        case id
        case category
        case sourceFindingIds = "source_finding_ids"
        case suggestedAction = "suggested_action"
        case remainingRounds = "remaining_rounds"
        case execution
        case commandSource = "command_source"
    }
}

struct QualityGateCI: Decodable, Equatable {
    let schemaVersion: String?
    let mode: String
    let status: String
    let taxonomy: [String]
    let counts: [String: Int]
    let checks: [QualityGateCICheck]
    let watcher: QualityGateCIWatcher?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case mode
        case status
        case taxonomy
        case counts
        case checks
        case watcher
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion)
        mode = try container.decodeIfPresent(String.self, forKey: .mode) ?? "not_configured"
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "unavailable"
        taxonomy = try container.decodeIfPresent([String].self, forKey: .taxonomy) ?? []
        counts = try container.decodeIfPresent([String: Int].self, forKey: .counts) ?? [:]
        checks = try container.decodeIfPresent([QualityGateCICheck].self, forKey: .checks) ?? []
        watcher = try container.decodeIfPresent(QualityGateCIWatcher.self, forKey: .watcher)
    }
}

struct QualityGateCIWatcher: Decodable, Equatable {
    let schemaVersion: String?
    let mode: String
    let status: String
    let maximumWaitSeconds: Int
    let deterministicSnapshot: Bool
    let polls: Int?
    let heartbeatRefresh: Bool?
    let idleTimeoutMilliseconds: Int?
    let maxWallTimeoutMilliseconds: Int?
    let elapsedMilliseconds: Int?
    let lastHeartbeatAt: String?
    let errors: [String]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case mode
        case status
        case maximumWaitSeconds = "max_wait_seconds"
        case deterministicSnapshot = "deterministic_snapshot"
        case polls
        case heartbeatRefresh = "heartbeat_refresh"
        case idleTimeoutMilliseconds = "idle_timeout_ms"
        case maxWallTimeoutMilliseconds = "max_wall_timeout_ms"
        case elapsedMilliseconds = "elapsed_ms"
        case lastHeartbeatAt = "last_heartbeat_at"
        case errors
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion)
        mode = try container.decodeIfPresent(String.self, forKey: .mode) ?? "not_configured"
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "unavailable"
        maximumWaitSeconds = try container.decodeIfPresent(Int.self, forKey: .maximumWaitSeconds) ?? 0
        deterministicSnapshot = try container.decodeIfPresent(Bool.self, forKey: .deterministicSnapshot) ?? false
        polls = try container.decodeIfPresent(Int.self, forKey: .polls)
        heartbeatRefresh = try container.decodeIfPresent(Bool.self, forKey: .heartbeatRefresh)
        idleTimeoutMilliseconds = try container.decodeIfPresent(Int.self, forKey: .idleTimeoutMilliseconds)
        maxWallTimeoutMilliseconds = try container.decodeIfPresent(Int.self, forKey: .maxWallTimeoutMilliseconds)
        elapsedMilliseconds = try container.decodeIfPresent(Int.self, forKey: .elapsedMilliseconds)
        lastHeartbeatAt = try container.decodeIfPresent(String.self, forKey: .lastHeartbeatAt)
        if let structuredErrors = try? container.decode([String].self, forKey: .errors) {
            errors = structuredErrors
        } else if let encodedErrors = try? container.decode(String.self, forKey: .errors),
                  let data = encodedErrors.data(using: .utf8),
                  let decodedErrors = try? JSONDecoder().decode([String].self, from: data) {
            errors = decodedErrors
        } else {
            errors = []
        }
    }
}

struct QualityGateCICheck: Decodable, Equatable, Identifiable {
    let id: String
    let name: String
    let status: String
    let conclusion: String?
    let category: String?
    let required: Bool?
    let detailsURL: String?
    let failureSummary: String?
    let failureLogSHA256: String?

    init(from decoder: Decoder) throws {
        enum CodingKeys: String, CodingKey {
            case id
            case name
            case status
            case conclusion
            case category
            case required
            case detailsURL = "details_url"
            case failureSummary = "failure_summary"
            case failureLogSHA256 = "failure_log_sha256"
        }
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(String.self, forKey: .id) ?? "ci-check"
        name = try container.decodeIfPresent(String.self, forKey: .name) ?? id
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "unknown"
        conclusion = try container.decodeIfPresent(String.self, forKey: .conclusion)
        category = try container.decodeIfPresent(String.self, forKey: .category)
        required = try container.decodeIfPresent(Bool.self, forKey: .required)
        detailsURL = try container.decodeIfPresent(String.self, forKey: .detailsURL)
        failureSummary = try container.decodeIfPresent(String.self, forKey: .failureSummary)
        failureLogSHA256 = try container.decodeIfPresent(String.self, forKey: .failureLogSHA256)
    }
}

struct QualityGateDraftPRPlan: Decodable, Equatable {
    let status: String
    let requested: Bool
    let ready: Bool
    let mutationPerformed: Bool
    let remoteMutationAllowed: Bool
    let provider: String?
    let operation: String?
    let repository: String?
    let baseRef: String?
    let headRef: String?
    let headSha: String?
    let title: String?
    let bodyEvidenceRefs: [String]
    let blockingReasons: [String]

    enum CodingKeys: String, CodingKey {
        case status
        case requested
        case ready
        case mutationPerformed = "mutation_performed"
        case remoteMutationAllowed = "remote_mutation_allowed"
        case provider
        case operation
        case repository
        case baseRef = "base_ref"
        case headRef = "head_ref"
        case headSha = "head_sha"
        case title
        case bodyEvidenceRefs = "body_evidence_refs"
        case blockingReasons = "blocking_reasons"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "not_requested"
        requested = try container.decodeIfPresent(Bool.self, forKey: .requested) ?? false
        ready = try container.decodeIfPresent(Bool.self, forKey: .ready) ?? false
        mutationPerformed = try container.decodeIfPresent(Bool.self, forKey: .mutationPerformed) ?? false
        remoteMutationAllowed = try container.decodeIfPresent(Bool.self, forKey: .remoteMutationAllowed) ?? false
        provider = try container.decodeIfPresent(String.self, forKey: .provider)
        operation = try container.decodeIfPresent(String.self, forKey: .operation)
        repository = try container.decodeIfPresent(String.self, forKey: .repository)
        baseRef = try container.decodeIfPresent(String.self, forKey: .baseRef)
        headRef = try container.decodeIfPresent(String.self, forKey: .headRef)
        headSha = try container.decodeIfPresent(String.self, forKey: .headSha)
        title = try container.decodeIfPresent(String.self, forKey: .title)
        bodyEvidenceRefs = try container.decodeIfPresent([String].self, forKey: .bodyEvidenceRefs) ?? []
        blockingReasons = try container.decodeIfPresent([String].self, forKey: .blockingReasons) ?? []
    }
}

struct QualityGateGitBinding: Decodable, Equatable {
    let baseSha: String?
    let headSha: String?
    let currentHeadSha: String?
    let branch: String?
    let expectedBranch: String?
    let expectedCommit: String?
    let expectedBaseSha: String?
    let mergeBaseSha: String?
    let baseIsAncestor: Bool?
    let dirtyPaths: [String]
    let dirtyStatusHash: String?

    enum CodingKeys: String, CodingKey {
        case baseSha = "base_sha"
        case headSha = "head_sha"
        case currentHeadSha = "current_head_sha"
        case branch
        case expectedBranch = "expected_branch"
        case expectedCommit = "expected_commit"
        case expectedBaseSha = "expected_base_sha"
        case mergeBaseSha = "merge_base_sha"
        case baseIsAncestor = "base_is_ancestor"
        case dirtyPaths = "dirty_paths"
        case dirtyStatusHash = "dirty_status_hash"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        baseSha = try container.decodeIfPresent(String.self, forKey: .baseSha)
        headSha = try container.decodeIfPresent(String.self, forKey: .headSha)
        currentHeadSha = try container.decodeIfPresent(String.self, forKey: .currentHeadSha)
        branch = try container.decodeIfPresent(String.self, forKey: .branch)
        expectedBranch = try container.decodeIfPresent(String.self, forKey: .expectedBranch)
        expectedCommit = try container.decodeIfPresent(String.self, forKey: .expectedCommit)
        expectedBaseSha = try container.decodeIfPresent(String.self, forKey: .expectedBaseSha)
        mergeBaseSha = try container.decodeIfPresent(String.self, forKey: .mergeBaseSha)
        baseIsAncestor = try container.decodeIfPresent(Bool.self, forKey: .baseIsAncestor)
        dirtyPaths = try container.decodeIfPresent([String].self, forKey: .dirtyPaths) ?? []
        dirtyStatusHash = try container.decodeIfPresent(String.self, forKey: .dirtyStatusHash)
    }
}

struct QualityGatePushReceipt: Decodable, Equatable {
    let schemaVersion: String?
    let gateVerdict: String?
    let evidenceHash: String?
    let prReadySummary: String?
    let repository: QualityGateRepository?
    let baseRef: String?
    let headRef: String?
    let headSha: String?
    let dirtyTree: Bool?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case gateVerdict = "gate_verdict"
        case evidenceHash = "evidence_hash"
        case prReadySummary = "pr_ready_summary"
        case repository
        case baseRef = "base_ref"
        case headRef = "head_ref"
        case headSha = "head_sha"
        case dirtyTree = "dirty_tree"
    }
}

struct QualityGateGitHubReview: Decodable, Equatable {
    let schemaVersion: String?
    let mutationPerformed: Bool
    let remoteMutationAllowed: Bool
    let checkRun: QualityGateGitHubCheckRun?
    let prComment: QualityGateGitHubPRComment?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case mutationPerformed = "mutation_performed"
        case remoteMutationAllowed = "remote_mutation_allowed"
        case checkRun = "check_run"
        case prComment = "pr_comment"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion)
        mutationPerformed = try container.decodeIfPresent(Bool.self, forKey: .mutationPerformed) ?? false
        remoteMutationAllowed = try container.decodeIfPresent(Bool.self, forKey: .remoteMutationAllowed) ?? false
        checkRun = try container.decodeIfPresent(QualityGateGitHubCheckRun.self, forKey: .checkRun)
        prComment = try container.decodeIfPresent(QualityGateGitHubPRComment.self, forKey: .prComment)
    }
}

struct QualityGateGitHubCheckRun: Decodable, Equatable {
    let name: String?
    let externalId: String?
    let headSha: String?
    let conclusion: String?
    let output: QualityGateGitHubOutput?

    enum CodingKeys: String, CodingKey {
        case name
        case externalId = "external_id"
        case headSha = "head_sha"
        case conclusion
        case output
    }
}

struct QualityGateGitHubOutput: Decodable, Equatable {
    let title: String?
    let summary: String?
    let text: String?
}

struct QualityGateGitHubPRComment: Decodable, Equatable {
    let body: String?
    let evidenceHash: String?

    enum CodingKeys: String, CodingKey {
        case body
        case evidenceHash = "evidence_hash"
    }
}

struct QualityGateGitHubRemote: Decodable, Equatable {
    let schemaVersion: String?
    let status: String
    let mutationPerformed: Bool
    let remoteStateRequiresReconciliation: Bool
    let recoverable: Bool
    let secretMaterialPersisted: Bool
    let authorization: QualityGateRemoteAuthorization?
    let branchPush: QualityGateRemoteBranchPush?
    let pullRequest: QualityGateRemotePullRequest?
    let ciWatch: QualityGateRemoteCIWatch?
    let operations: [QualityGateRemoteOperation]
    let errors: [String]
    let auditHash: String?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case status
        case mutationPerformed = "mutation_performed"
        case remoteStateRequiresReconciliation = "remote_state_requires_reconciliation"
        case recoverable
        case secretMaterialPersisted = "secret_material_persisted"
        case authorization
        case branchPush = "branch_push"
        case pullRequest = "pull_request"
        case ciWatch = "ci_watch"
        case operations
        case errors
        case auditHash = "audit_hash"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion)
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "not_requested"
        mutationPerformed = try container.decodeIfPresent(Bool.self, forKey: .mutationPerformed) ?? false
        remoteStateRequiresReconciliation = try container.decodeIfPresent(Bool.self, forKey: .remoteStateRequiresReconciliation) ?? false
        recoverable = try container.decodeIfPresent(Bool.self, forKey: .recoverable) ?? false
        secretMaterialPersisted = try container.decodeIfPresent(Bool.self, forKey: .secretMaterialPersisted) ?? false
        authorization = try container.decodeIfPresent(QualityGateRemoteAuthorization.self, forKey: .authorization)
        branchPush = try container.decodeIfPresent(QualityGateRemoteBranchPush.self, forKey: .branchPush)
        pullRequest = try container.decodeIfPresent(QualityGateRemotePullRequest.self, forKey: .pullRequest)
        ciWatch = try container.decodeIfPresent(QualityGateRemoteCIWatch.self, forKey: .ciWatch)
        operations = try container.decodeIfPresent([QualityGateRemoteOperation].self, forKey: .operations) ?? []
        errors = try container.decodeIfPresent([String].self, forKey: .errors) ?? []
        auditHash = try container.decodeIfPresent(String.self, forKey: .auditHash)
    }

    var verificationMode: String? {
        operations.first(where: { $0.id == "check_run" })?.verificationMode
    }
}

struct QualityGateRemoteAuthorization: Decodable, Equatable {
    let requested: Bool
    let allowed: Bool
    let repository: String?
    let host: String?
    let pushRequested: Bool
    let pushRef: String?
    let approvalTokenVerified: Bool
    let credentialPresent: Bool
    let secretMaterialIncluded: Bool

    enum CodingKeys: String, CodingKey {
        case requested
        case allowed
        case repository
        case host
        case pushRequested = "push_requested"
        case pushRef = "push_ref"
        case approvalTokenVerified = "approval_token_verified"
        case credentialPresent = "credential_present"
        case secretMaterialIncluded = "secret_material_included"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        requested = try container.decodeIfPresent(Bool.self, forKey: .requested) ?? false
        allowed = try container.decodeIfPresent(Bool.self, forKey: .allowed) ?? false
        repository = try container.decodeIfPresent(String.self, forKey: .repository)
        host = try container.decodeIfPresent(String.self, forKey: .host)
        pushRequested = try container.decodeIfPresent(Bool.self, forKey: .pushRequested) ?? false
        pushRef = try container.decodeIfPresent(String.self, forKey: .pushRef)
        approvalTokenVerified = try container.decodeIfPresent(Bool.self, forKey: .approvalTokenVerified) ?? false
        credentialPresent = try container.decodeIfPresent(Bool.self, forKey: .credentialPresent) ?? false
        secretMaterialIncluded = try container.decodeIfPresent(Bool.self, forKey: .secretMaterialIncluded) ?? false
    }
}

struct QualityGateRemoteBranchPush: Decodable, Equatable {
    let status: String?
    let mutationPerformed: Bool
    let resumed: Bool
    let reconciled: Bool
    let sourceSHA: String?
    let targetRef: String?
    let remoteSHA: String?

    enum CodingKeys: String, CodingKey {
        case status
        case mutationPerformed = "mutation_performed"
        case resumed
        case reconciled
        case sourceSHA = "source_sha"
        case targetRef = "target_ref"
        case remoteSHA = "remote_sha"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        status = try container.decodeIfPresent(String.self, forKey: .status)
        mutationPerformed = try container.decodeIfPresent(Bool.self, forKey: .mutationPerformed) ?? false
        resumed = try container.decodeIfPresent(Bool.self, forKey: .resumed) ?? false
        reconciled = try container.decodeIfPresent(Bool.self, forKey: .reconciled) ?? false
        sourceSHA = try container.decodeIfPresent(String.self, forKey: .sourceSHA)
        targetRef = try container.decodeIfPresent(String.self, forKey: .targetRef)
        remoteSHA = try container.decodeIfPresent(String.self, forKey: .remoteSHA)
    }
}

struct QualityGateRemotePullRequest: Decodable, Equatable {
    let number: Int?
    let url: String?
    let state: String?
    let draft: Bool
    let headRef: String?
    let baseRef: String?

    enum CodingKeys: String, CodingKey {
        case number
        case url
        case state
        case draft
        case headRef = "head_ref"
        case baseRef = "base_ref"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        number = try container.decodeIfPresent(Int.self, forKey: .number)
        url = try container.decodeIfPresent(String.self, forKey: .url)
        state = try container.decodeIfPresent(String.self, forKey: .state)
        draft = try container.decodeIfPresent(Bool.self, forKey: .draft) ?? false
        headRef = try container.decodeIfPresent(String.self, forKey: .headRef)
        baseRef = try container.decodeIfPresent(String.self, forKey: .baseRef)
    }
}

struct QualityGateRemoteCIWatch: Decodable, Equatable {
    let schemaVersion: String?
    let status: String
    let polls: Int
    let heartbeats: [QualityGateRemoteHeartbeat]
    let snapshot: QualityGateCI?
    let failureSummaries: [QualityGateRemoteFailureSummary]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case status
        case polls
        case heartbeats
        case snapshot
        case failureSummaries = "failure_summaries"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion)
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "unknown"
        polls = try container.decodeIfPresent(Int.self, forKey: .polls) ?? 0
        heartbeats = try container.decodeIfPresent([QualityGateRemoteHeartbeat].self, forKey: .heartbeats) ?? []
        snapshot = try container.decodeIfPresent(QualityGateCI.self, forKey: .snapshot)
        failureSummaries = try container.decodeIfPresent([QualityGateRemoteFailureSummary].self, forKey: .failureSummaries) ?? []
    }
}

struct QualityGateRemoteHeartbeat: Decodable, Equatable, Identifiable {
    let sequence: Int
    let observedAt: String?
    let checkCount: Int
    let pendingCount: Int
    let snapshotSHA256: String?

    var id: Int { sequence }

    enum CodingKeys: String, CodingKey {
        case sequence
        case observedAt = "observed_at"
        case checkCount = "check_count"
        case pendingCount = "pending_count"
        case snapshotSHA256 = "snapshot_sha256"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        sequence = try container.decodeIfPresent(Int.self, forKey: .sequence) ?? 0
        observedAt = try container.decodeIfPresent(String.self, forKey: .observedAt)
        checkCount = try container.decodeIfPresent(Int.self, forKey: .checkCount) ?? 0
        pendingCount = try container.decodeIfPresent(Int.self, forKey: .pendingCount) ?? 0
        snapshotSHA256 = try container.decodeIfPresent(String.self, forKey: .snapshotSHA256)
    }
}

struct QualityGateRemoteFailureSummary: Decodable, Equatable, Identifiable {
    let runID: String?
    let name: String
    let summary: String?
    let logSHA256: String?

    var id: String { runID ?? name }

    enum CodingKeys: String, CodingKey {
        case runID = "run_id"
        case name
        case summary
        case logSHA256 = "log_sha256"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        runID = try container.decodeIfPresent(String.self, forKey: .runID)
        name = try container.decodeIfPresent(String.self, forKey: .name) ?? runID ?? "CI"
        summary = try container.decodeIfPresent(String.self, forKey: .summary)
        logSHA256 = try container.decodeIfPresent(String.self, forKey: .logSHA256)
    }
}

struct QualityGateRemoteOperation: Decodable, Equatable, Identifiable {
    let id: String
    let status: String
    let mutationPerformed: Bool
    let mutationMayHaveOccurred: Bool
    let resumed: Bool
    let verificationMode: String?
    let recovery: String?
    let attempts: Int?
    let lastHeartbeatAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case status
        case mutationPerformed = "mutation_performed"
        case mutationMayHaveOccurred = "mutation_may_have_occurred"
        case resumed
        case verificationMode = "verification_mode"
        case recovery
        case attempts
        case lastHeartbeatAt = "last_heartbeat_at"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(String.self, forKey: .id) ?? "operation"
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? "unknown"
        mutationPerformed = try container.decodeIfPresent(Bool.self, forKey: .mutationPerformed) ?? false
        mutationMayHaveOccurred = try container.decodeIfPresent(Bool.self, forKey: .mutationMayHaveOccurred) ?? false
        resumed = try container.decodeIfPresent(Bool.self, forKey: .resumed) ?? false
        verificationMode = try container.decodeIfPresent(String.self, forKey: .verificationMode)
        recovery = try container.decodeIfPresent(String.self, forKey: .recovery)
        attempts = try container.decodeIfPresent(Int.self, forKey: .attempts)
        lastHeartbeatAt = try container.decodeIfPresent(String.self, forKey: .lastHeartbeatAt)
    }
}

private extension String {
    var trimmedNil: String? {
        let value = trimmingCharacters(in: .whitespacesAndNewlines)
        return value.isEmpty ? nil : value
    }
}
