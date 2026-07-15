import CryptoKit
import Foundation

struct BeginnerNoKeyDemoGate: Decodable, Equatable, Identifiable {
    let id: String
    let status: String
    let required: Bool
}

struct BeginnerNoKeyDemoPolicy: Decodable, Equatable {
    let providerKeyUsed: Bool
    let networkUsed: Bool
    let modelCalls: Int
    let externalSideEffectsPerformed: Bool

    enum CodingKeys: String, CodingKey {
        case providerKeyUsed = "provider_key_used"
        case networkUsed = "network_used"
        case modelCalls = "model_calls"
        case externalSideEffectsPerformed = "external_side_effects_performed"
    }

    var isReadOnlyNoKey: Bool {
        !providerKeyUsed
            && !networkUsed
            && modelCalls == 0
            && !externalSideEffectsPerformed
    }
}

struct BeginnerNoKeyDemoResult: Decodable, Equatable {
    static let supportedSchemaVersion = "across-no-key-demo-result/1.0"

    let schemaVersion: String
    let patternID: String
    let missionID: String
    let runID: String?
    let status: String
    let verdict: String
    let evidenceRoute: String?
    let gates: [BeginnerNoKeyDemoGate]
    let policy: BeginnerNoKeyDemoPolicy
    let evidenceSHA256: String?
    let nextAction: String
    let nextActionID: String
    let goalSHA256: String
    let resultSHA256: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case patternID = "pattern_id"
        case missionID = "mission_id"
        case runID = "run_id"
        case status
        case verdict
        case evidenceRoute = "evidence_route"
        case gates
        case policy
        case evidenceSHA256 = "evidence_sha256"
        case nextAction = "next_action"
        case nextActionID = "next_action_id"
        case goalSHA256 = "goal_sha256"
        case resultSHA256 = "result_sha256"
    }

    var isVerified: Bool {
        hasValidIntegrityEnvelope
            && status == "completed"
            && verdict == "verified"
            && policy.isReadOnlyNoKey
            && !gates.contains { $0.required && $0.status != "passed" }
    }

    var hasValidIntegrityEnvelope: Bool {
        guard schemaVersion == Self.supportedSchemaVersion,
              patternID == "first-verified-task",
              missionID == "first_verified_task",
              let runID,
              !runID.isEmpty,
              !runID.contains("/"),
              evidenceRoute == "run://\(runID)/evidence",
              Self.isSHA256(evidenceSHA256 ?? ""),
              Self.isSHA256(goalSHA256),
              Self.isSHA256(resultSHA256),
              nextActionID == "inspect_evidence",
              !nextAction.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !gates.isEmpty else {
            return false
        }
        return gates.allSatisfy {
            !$0.id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                && ["passed", "failed", "blocked", "skipped"].contains($0.status)
        }
    }

    private static func isSHA256(_ value: String) -> Bool {
        let lowercaseHex = Set("0123456789abcdef")
        return value.count == 64 && value.allSatisfy(lowercaseHex.contains)
    }
}

private struct BeginnerNoKeyDemoRequest: Encodable {
    let projectDirectory: String
    let patternID: String
    let userGoal: String

    enum CodingKeys: String, CodingKey {
        case projectDirectory = "project_dir"
        case patternID = "pattern_id"
        case userGoal = "user_goal"
    }
}

@MainActor
final class BeginnerMissionViewModel: ObservableObject {
    typealias DataLoader = @Sendable (URLRequest) async throws -> (Data, URLResponse)

    @Published private(set) var result: BeginnerNoKeyDemoResult?
    @Published private(set) var isRunning = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var projectPath: String?
    @Published private(set) var requestedGoal: String?

    private let dataLoader: DataLoader
    private let backendBaseURL: URL

    init(
        backendBaseURL: URL = URL(string: "http://backend")!,
        dataLoader: @escaping DataLoader = { request in
            try await URLSession.shared.data(for: request)
        }
    ) {
        self.backendBaseURL = backendBaseURL
        self.dataLoader = dataLoader
    }

    var visualResult: AcrossVisualResultContract? {
        result.map(AcrossVisualResultFactory.make(beginnerResult:))
    }

    func resetIfProjectChanged(to newProjectPath: String?) {
        let normalized = Self.normalizedProjectPath(newProjectPath)
        guard normalized != projectPath else { return }
        projectPath = normalized
        result = nil
        errorMessage = nil
        requestedGoal = nil
    }

    @discardableResult
    func run(projectPath rawProjectPath: String, userGoal rawUserGoal: String) async -> BeginnerNoKeyDemoResult? {
        let normalized = Self.normalizedProjectPath(rawProjectPath)
        guard let normalized else {
            errorMessage = "A project folder is required."
            return nil
        }
        guard let userGoal = Self.normalizedGoal(rawUserGoal) else {
            errorMessage = "Describe the result you want before starting."
            return nil
        }

        projectPath = normalized
        requestedGoal = userGoal
        result = nil
        errorMessage = nil
        isRunning = true
        defer { isRunning = false }

        do {
            let url = backendBaseURL.appendingPathComponent("api/autopilot/no-key-demo/run")
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(
                BeginnerNoKeyDemoRequest(
                    projectDirectory: normalized,
                    patternID: "first-verified-task",
                    userGoal: userGoal
                )
            )
            let (data, response) = try await dataLoader(request)
            try Self.validate(response: response, data: data)
            let decoded = try JSONDecoder().decode(BeginnerNoKeyDemoResult.self, from: data)
            guard decoded.schemaVersion == BeginnerNoKeyDemoResult.supportedSchemaVersion else {
                throw NSError(
                    domain: "BeginnerMission",
                    code: 2,
                    userInfo: [NSLocalizedDescriptionKey: "The first-mission result uses an unsupported schema."]
                )
            }
            guard decoded.hasValidIntegrityEnvelope,
                  decoded.goalSHA256 == Self.sha256(userGoal) else {
                throw NSError(
                    domain: "BeginnerMission",
                    code: 3,
                    userInfo: [NSLocalizedDescriptionKey: "The first-mission result is not bound to your goal or run evidence."]
                )
            }
            result = decoded
            return decoded
        } catch {
            errorMessage = error.localizedDescription
            return nil
        }
    }

    nonisolated static func normalizedProjectPath(_ value: String?) -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else {
            return nil
        }
        return URL(fileURLWithPath: value)
            .standardizedFileURL
            .resolvingSymlinksInPath()
            .path
    }

    nonisolated static func normalizedGoal(_ value: String?) -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else {
            return nil
        }
        return value
    }

    nonisolated static func sha256(_ value: String) -> String {
        SHA256.hash(data: Data(value.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    nonisolated static func validate(response: URLResponse, data: Data) throws {
        guard let httpResponse = response as? HTTPURLResponse else {
            throw URLError(.badServerResponse)
        }
        guard (200..<300).contains(httpResponse.statusCode) else {
            if let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let detail = payload["detail"] as? String,
               !detail.isEmpty {
                throw NSError(
                    domain: "BeginnerMission",
                    code: httpResponse.statusCode,
                    userInfo: [NSLocalizedDescriptionKey: detail]
                )
            }
            throw NSError(
                domain: "BeginnerMission",
                code: httpResponse.statusCode,
                userInfo: [NSLocalizedDescriptionKey: "HTTP \(httpResponse.statusCode)"]
            )
        }
    }
}

extension AcrossVisualResultFactory {
    static func make(beginnerResult result: BeginnerNoKeyDemoResult) -> AcrossVisualResultContract {
        let requiredGates = result.gates.filter(\.required)
        let failedRequiredGates = requiredGates.filter { $0.status != "passed" }
        let outcome: AcrossEvidenceState = result.status == "completed"
            ? (result.verdict == "verified" ? .confirmed : .partial)
            : .blocked
        let proof: AcrossEvidenceState
        if !failedRequiredGates.isEmpty {
            proof = .blocked
        } else if !requiredGates.isEmpty,
                  requiredGates.allSatisfy({ $0.status == "passed" }),
                  result.evidenceRoute != nil,
                  result.evidenceSHA256?.isEmpty == false {
            proof = .confirmed
        } else {
            proof = .partial
        }
        let safety: AcrossEvidenceState = result.policy.isReadOnlyNoKey ? .confirmed : .blocked
        let humanControl: AcrossEvidenceState = result.policy.externalSideEffectsPerformed ? .blocked : .confirmed
        let verdict: AcrossRunVerdict
        if [.blocked].contains(outcome) || proof == .blocked || safety == .blocked || humanControl == .blocked {
            verdict = .blocked
        } else if result.isVerified && proof == .confirmed {
            verdict = .ready
        } else {
            verdict = .needsReview
        }

        let runReference = result.runID ?? result.resultSHA256
        let attention = failedRequiredGates.map { gate in
            AcrossAttentionItem(
                id: "beginner-gate-\(gate.id)",
                priority: .actNow,
                titleKey: "result.attention.resolveBlocked",
                detail: gate.id
            )
        }
        let checkCount = max(requiredGates.count, result.gates.count)
        let nodes = [
            AcrossEvidenceNode(kind: .source, state: .confirmed, referenceCount: 1),
            AcrossEvidenceNode(kind: .action, state: outcome, referenceCount: 1),
            AcrossEvidenceNode(kind: .check, state: proof, referenceCount: checkCount),
            AcrossEvidenceNode(kind: .artifact, state: .missing, referenceCount: 0),
            AcrossEvidenceNode(kind: .approval, state: humanControl, referenceCount: 0),
            AcrossEvidenceNode(kind: .memory, state: .missing, referenceCount: 0),
        ]
        let relations = [
            AcrossEvidenceRelation(from: .source, to: .action, relation: "supports"),
            AcrossEvidenceRelation(from: .action, to: .check, relation: "verified_by"),
        ]

        return AcrossVisualResultContract(
            taskID: runReference,
            verdict: verdict,
            trustCompass: AcrossTrustCompass(
                outcome: outcome,
                proof: proof,
                safety: safety,
                humanControl: humanControl
            ),
            loopTrail: [
                AcrossLoopTrailStep(stage: .goal, state: .complete),
                AcrossLoopTrailStep(stage: .prepare, state: .complete),
                AcrossLoopTrailStep(stage: .execute, state: outcome == .blocked ? .blocked : .complete),
                AcrossLoopTrailStep(stage: .verify, state: proof == .blocked ? .blocked : .complete),
                AcrossLoopTrailStep(stage: .decide, state: .active),
                AcrossLoopTrailStep(stage: .remember, state: .pending),
            ],
            evidenceConstellation: AcrossEvidenceConstellation(nodes: nodes, relations: relations),
            attentionStack: attention,
            nextAction: result.evidenceRoute == nil ? .retry : .inspectEvidence
        )
    }
}
