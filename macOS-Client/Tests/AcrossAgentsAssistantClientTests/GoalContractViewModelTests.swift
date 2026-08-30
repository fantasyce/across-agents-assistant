import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct GoalContractViewModelTests {
    @Test
    func taskSubmissionErrorParsesStructuredCapabilityDecisions() {
        let data = Data("""
        {"detail":{"code":"capability_decision_required","decision_ids":["approve_risky_capabilities"]}}
        """.utf8)

        #expect(TaskOrchestrationViewModel.taskSubmissionErrorMessage(
            from: data,
            statusCode: 409
        ) == "approve_risky_capabilities")
        #expect(!TaskOrchestrationViewModel.taskSubmissionErrorMessage(
            from: data,
            statusCode: 409
        ).contains("{"))
    }

    @Test @MainActor
    func missingGoalIsAStableLegacyState() async {
        let viewModel = TaskOrchestrationViewModel(requestData: { request in
            (Data(), Self.response(request, status: 404))
        })

        await viewModel.loadGoalContract("legacy-task").value

        #expect(viewModel.goalTaskState == .legacyEmpty)
        #expect(viewModel.goalContractError == nil)
        #expect(!viewModel.isLoadingGoalContract)
    }

    @Test @MainActor
    func clearingGoalFencesALateResponse() async {
        let gate = GoalResponseGate()
        let viewModel = TaskOrchestrationViewModel(requestData: { request in
            try await gate.response(for: request)
        })
        let load = viewModel.loadGoalContract("task-1")
        await gate.waitUntilRequested()

        viewModel.clearGoalContract()
        await gate.release(data: Data(GoalContractModelsTests.envelopeJSON().utf8))
        await load.value

        #expect(viewModel.selectedGoalContract == nil)
        #expect(viewModel.goalTaskState == .legacyEmpty)
        #expect(!viewModel.isLoadingGoalContract)
    }

    @Test @MainActor
    func decisionSendsRevisionAndRefreshesAuthoritativeProjection() async throws {
        let stub = GoalMutationStub(goalData: Data(GoalContractModelsTests.envelopeJSON().utf8))
        let viewModel = TaskOrchestrationViewModel(requestData: { request in
            try await stub.response(for: request)
        })

        await viewModel.decideGoalProposal(
            taskId: "task-1",
            proposalId: "proposal-1",
            decision: "accepted",
            expectedRevision: 2,
            idempotencyKey: "decision-fixed"
        ).value

        let requests = await stub.requests
        #expect(requests.count == 2)
        #expect(requests[0].url?.path.hasSuffix("/api/tasks/task-1/goal/proposals/proposal-1/decision") == true)
        let body = try #require(requests[0].httpBody)
        let object = try #require(try JSONSerialization.jsonObject(with: body) as? [String: Any])
        #expect(object["expected_revision"] as? Int == 2)
        #expect(object["idempotency_key"] as? String == "decision-fixed")
        #expect(viewModel.selectedGoalContract?.contract.taskId == "task-1")
        #expect(viewModel.goalContractError == nil)
    }

    @Test @MainActor
    func criterionReviewSendsHumanDecisionAndRefreshesProjection() async throws {
        let stub = GoalMutationStub(goalData: Data(GoalContractModelsTests.envelopeJSON().utf8))
        let viewModel = TaskOrchestrationViewModel(requestData: { request in
            try await stub.response(for: request)
        })

        await viewModel.reviewGoalCriterion(
            taskId: "task-1",
            expectedRevision: 2,
            criterionId: "criterion-1",
            decision: "rejected",
            reason: "Needs correction",
            idempotencyKey: "review-fixed"
        ).value

        let requests = await stub.requests
        #expect(requests.count == 2)
        #expect(requests[0].url?.path.hasSuffix("/api/tasks/task-1/goal/reviews") == true)
        let body = try #require(requests[0].httpBody)
        let object = try #require(try JSONSerialization.jsonObject(with: body) as? [String: Any])
        #expect(object["criterion_id"] as? String == "criterion-1")
        #expect(object["decision"] as? String == "rejected")
        #expect(object["expected_revision"] as? Int == 2)
    }

    @Test @MainActor
    func acceptingResultAppliesReturnedGoalWithoutNavigation() async throws {
        let completedGoal = GoalContractModelsTests.envelopeJSON(
            displayState: "completed",
            evidenceState: "satisfied",
            reasons: []
        )
        .replacingOccurrences(of: "\"is_complete\": false", with: "\"is_complete\": true")
        let responseData = Data("""
        {
          "task_review":{"task_id":"task-1","review_status":"accepted","accepted_at":42},
          "goal":\(completedGoal),
          "decision_receipt":{"receipt_id":"receipt-1","purpose":"goal_result_review","receipt_hash":"abc","integrity_status":"verified"}
        }
        """.utf8)
        let viewModel = TaskOrchestrationViewModel(requestData: { request in
            (responseData, Self.response(request, status: 200))
        })
        viewModel.selectedGoalContract = try JSONDecoder().decode(
            GoalContractEnvelope.self,
            from: Data(GoalContractModelsTests.envelopeJSON().utf8)
        )

        await viewModel.acceptTaskResult("task-1") {}.value

        #expect(viewModel.selectedGoalContract?.projection.isComplete == true)
        #expect(viewModel.goalTaskState == .completed)
        #expect(viewModel.goalContractError == nil)
    }

    @Test @MainActor
    func failedResultDecisionPreservesLastGoalAndSetsActionError() async throws {
        let original = try JSONDecoder().decode(
            GoalContractEnvelope.self,
            from: Data(GoalContractModelsTests.envelopeJSON().utf8)
        )
        let viewModel = TaskOrchestrationViewModel(requestData: { request in
            let data = Data("{\"detail\":{\"reason_code\":\"goal_repair_required\",\"message\":\"Repair required\"}}".utf8)
            return (data, Self.response(request, status: 409))
        })
        viewModel.selectedGoalContract = original
        viewModel.goalTaskState = GoalProjectionReducer.reduce(original, loading: false, error: nil)

        await viewModel.acceptTaskResult("task-1") {}.value

        #expect(viewModel.selectedGoalContract == original)
        #expect(viewModel.goalTaskState == GoalProjectionReducer.reduce(original, loading: false, error: nil))
        #expect(viewModel.goalContractError == "Repair required")
    }

    private static func response(_ request: URLRequest, status: Int) -> HTTPURLResponse {
        HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
    }
}

private actor GoalResponseGate {
    private var continuation: CheckedContinuation<(Data, URLResponse), Error>?
    private var requested = false

    func response(for request: URLRequest) async throws -> (Data, URLResponse) {
        requested = true
        return try await withCheckedThrowingContinuation { continuation = $0 }
    }

    func waitUntilRequested() async {
        while !requested { await Task.yield() }
    }

    func release(data: Data) {
        let response = HTTPURLResponse(
            url: URL(string: "http://backend/api/tasks/task-1/goal")!,
            statusCode: 200,
            httpVersion: nil,
            headerFields: nil
        )!
        continuation?.resume(returning: (data, response))
        continuation = nil
    }
}

private actor GoalMutationStub {
    private(set) var requests: [URLRequest] = []
    let goalData: Data

    init(goalData: Data) {
        self.goalData = goalData
    }

    func response(for request: URLRequest) throws -> (Data, URLResponse) {
        requests.append(request)
        let status = 200
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
        return (request.httpMethod == "GET" ? goalData : Data("{}".utf8), response)
    }
}
