import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct GoalContractViewModelTests {
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
