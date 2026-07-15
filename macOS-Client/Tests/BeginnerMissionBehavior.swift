import Foundation

@main
struct BeginnerMissionBehavior {
    @MainActor
    static func main() async throws {
        let goal = "Tell me the safest next step for this project"
        let goalSHA256 = BeginnerMissionViewModel.sha256(goal)
        let payload = Data(
            """
            {
              "schema_version": "across-no-key-demo-result/1.0",
              "pattern_id": "first-verified-task",
              "mission_id": "first_verified_task",
              "run_id": "run-behavior",
              "status": "completed",
              "verdict": "verified",
              "evidence_route": "run://run-behavior/evidence",
              "gates": [{"id":"manifest_readable","status":"passed","required":true}],
              "policy": {
                "provider_key_used": false,
                "network_used": false,
                "model_calls": 0,
                "external_side_effects_performed": false
              },
              "evidence_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
              "next_action": "Open evidence.",
              "next_action_id": "inspect_evidence",
              "goal_sha256": "\(goalSHA256)",
              "result_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
            }
            """.utf8
        )
        let viewModel = BeginnerMissionViewModel { request in
            guard let body = request.httpBody,
                  let object = try JSONSerialization.jsonObject(with: body) as? [String: String],
                  object["pattern_id"] == "first-verified-task",
                  object["user_goal"] == goal else {
                throw URLError(.badURL)
            }
            return (
                payload,
                HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            )
        }
        guard let decoded = await viewModel.run(projectPath: "/tmp", userGoal: goal) else {
            fatalError(viewModel.errorMessage ?? "Beginner mission did not return a result")
        }
        precondition(decoded.isVerified)
        precondition(decoded.policy.isReadOnlyNoKey)
        precondition(decoded.goalSHA256 == goalSHA256)
        precondition(viewModel.requestedGoal == goal)

        let visual = AcrossVisualResultFactory.make(beginnerResult: decoded)
        precondition(visual.verdict == .ready)
        precondition(visual.trustCompass.state(for: .proof) == .confirmed)
        precondition(visual.nextAction == .inspectEvidence)
        precondition(visual.evidenceConstellation.nodes.first(where: { $0.kind == .check })?.referenceCount == 1)

        print("Beginner mission behavior checks passed.")
    }
}
