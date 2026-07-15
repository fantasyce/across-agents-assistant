import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

private final class BeginnerRequestRecorder: @unchecked Sendable {
    private let lock = NSLock()
    private var storedRequest: URLRequest?

    func record(_ request: URLRequest) {
        lock.lock()
        storedRequest = request
        lock.unlock()
    }

    func request() -> URLRequest? {
        lock.lock()
        defer { lock.unlock() }
        return storedRequest
    }
}

struct BeginnerMissionTests {
    @Test @MainActor func oneClickMissionUsesSelectedProjectAndDecodesCompactResult() async throws {
        let recorder = BeginnerRequestRecorder()
        let goal = "Tell me whether the release is safe"
        let payload = Self.verifiedPayload(userGoal: goal)
        let viewModel = BeginnerMissionViewModel { request in
            recorder.record(request)
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (Data(payload.utf8), response)
        }

        let result = await viewModel.run(
            projectPath: "/tmp/../tmp/beginner-project",
            userGoal: "  \(goal)  "
        )

        #expect(result?.isVerified == true)
        #expect(viewModel.errorMessage == nil)
        let visual = try #require(viewModel.visualResult)
        #expect(visual.verdict == AcrossRunVerdict.ready)
        #expect(visual.trustCompass.state(for: AcrossTrustDimension.proof) == AcrossEvidenceState.confirmed)
        let request = try #require(recorder.request())
        #expect(request.url?.path == "/api/autopilot/no-key-demo/run")
        #expect(request.httpMethod == "POST")
        let requestBody = try #require(request.httpBody)
        let bodyObject = try JSONSerialization.jsonObject(with: requestBody)
        let body = try #require(bodyObject as? [String: Any])
        #expect(body["project_dir"] as? String == "/tmp/beginner-project")
        #expect(body["pattern_id"] as? String == "first-verified-task")
        #expect(body["user_goal"] as? String == goal)
        #expect(result?.goalSHA256 == BeginnerMissionViewModel.sha256(goal))
        #expect(result?.nextActionID == "inspect_evidence")
        #expect(viewModel.requestedGoal == goal)
    }

    @Test func unsafeOrFailedEvidenceCanNeverRenderAsReady() throws {
        let unsafe = try JSONDecoder().decode(
            BeginnerNoKeyDemoResult.self,
            from: Data(Self.verifiedPayload(
                verdict: "needs_attention",
                gateStatus: "failed",
                networkUsed: true
            ).utf8)
        )

        let visual = AcrossVisualResultFactory.make(beginnerResult: unsafe)

        #expect(unsafe.isVerified == false)
        #expect(visual.verdict == AcrossRunVerdict.blocked)
        #expect(visual.trustCompass.state(for: AcrossTrustDimension.proof) == AcrossEvidenceState.blocked)
        #expect(visual.trustCompass.state(for: AcrossTrustDimension.safety) == AcrossEvidenceState.blocked)
        #expect(visual.attentionStack.count == 1)
    }

    @Test func runSpecificEvidenceAndIntegrityHashesAreRequired() throws {
        let wrongRoutePayload = Self.verifiedPayload().replacingOccurrences(
            of: "run://run-beginner-1/evidence",
            with: "run://another-run/evidence"
        )
        let wrongRoute = try JSONDecoder().decode(
            BeginnerNoKeyDemoResult.self,
            from: Data(wrongRoutePayload.utf8)
        )
        #expect(wrongRoute.hasValidIntegrityEnvelope == false)
        #expect(wrongRoute.isVerified == false)

        let missingEvidenceHashPayload = Self.verifiedPayload().replacingOccurrences(
            of: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            with: ""
        )
        let missingEvidenceHash = try JSONDecoder().decode(
            BeginnerNoKeyDemoResult.self,
            from: Data(missingEvidenceHashPayload.utf8)
        )
        #expect(missingEvidenceHash.hasValidIntegrityEnvelope == false)
        #expect(missingEvidenceHash.isVerified == false)
    }

    @Test @MainActor func changingProjectClearsPriorResult() async {
        let goal = "Find the first blocked check"
        let payload = Self.verifiedPayload(userGoal: goal)
        let viewModel = BeginnerMissionViewModel { request in
            (
                Data(payload.utf8),
                HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            )
        }
        _ = await viewModel.run(projectPath: "/tmp/project-a", userGoal: goal)
        #expect(viewModel.result != nil)

        viewModel.resetIfProjectChanged(to: "/tmp/project-b")

        #expect(viewModel.result == nil)
        #expect(viewModel.projectPath == "/tmp/project-b")
        #expect(viewModel.requestedGoal == nil)
    }

    @Test @MainActor
    func openEvidenceLoadsTheSelectedBeginnerRunInsteadOfTheGenericWorkbench() async throws {
        let recorder = BeginnerRequestRecorder()
        let target = try #require(
            AutopilotEvidenceTarget(
                runID: "run-beginner-1",
                evidenceRoute: "run://run-beginner-1/evidence"
            )
        )
        let viewModel = AutopilotEvidenceViewModel(
            backendBaseURL: URL(string: "http://backend")!
        ) { request in
            recorder.record(request)
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (
                Data("""
                {
                  "schema_version": "across-loop-evidence/1.0",
                  "run_id": "run-beginner-1",
                  "status": "completed",
                  "gates": [{"id":"manifest_readable","status":"passed","required":true}]
                }
                """.utf8),
                response
            )
        }

        await viewModel.load(target: target)

        let request = try #require(recorder.request())
        #expect(request.httpMethod == "GET")
        #expect(request.url?.path == "/api/autopilot/runs/run-beginner-1/evidence")
        #expect(viewModel.loadedTarget == target)
        #expect(viewModel.payload?.objectValue?["run_id"]?.description == "run-beginner-1")
        #expect(viewModel.errorMessage == nil)
    }

    @Test @MainActor func blankGoalNeverStartsTheMission() async {
        let recorder = BeginnerRequestRecorder()
        let viewModel = BeginnerMissionViewModel { request in
            recorder.record(request)
            throw URLError(.unknown)
        }

        let result = await viewModel.run(projectPath: "/tmp/project-a", userGoal: " \n ")

        #expect(result == nil)
        #expect(recorder.request() == nil)
        #expect(viewModel.errorMessage != nil)
    }

    @Test @MainActor func resultForAnotherGoalIsRejected() async {
        let payload = Self.verifiedPayload(userGoal: "A different goal")
        let viewModel = BeginnerMissionViewModel { request in
            (
                Data(payload.utf8),
                HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            )
        }

        let result = await viewModel.run(
            projectPath: "/tmp/project-a",
            userGoal: "My actual goal"
        )

        #expect(result == nil)
        #expect(viewModel.result == nil)
        #expect(viewModel.errorMessage?.contains("not bound") == true)
    }

    private static func verifiedPayload(
        userGoal: String = "Check whether this project is safe",
        verdict: String = "verified",
        gateStatus: String = "passed",
        networkUsed: Bool = false
    ) -> String {
        """
        {
          "schema_version": "across-no-key-demo-result/1.0",
          "pattern_id": "first-verified-task",
          "mission_id": "first_verified_task",
          "run_id": "run-beginner-1",
          "status": "completed",
          "verdict": "\(verdict)",
          "evidence_route": "run://run-beginner-1/evidence",
          "gates": [{"id":"manifest_readable","status":"\(gateStatus)","required":true}],
          "policy": {
            "provider_key_used": false,
            "network_used": \(networkUsed),
            "model_calls": 0,
            "external_side_effects_performed": false
          },
          "evidence_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "next_action": "Open evidence.",
          "next_action_id": "inspect_evidence",
          "goal_sha256": "\(BeginnerMissionViewModel.sha256(userGoal))",
          "result_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        }
        """
    }
}
