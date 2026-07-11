import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct MemorySearchOperationsTests {
    @Test func ordinarySearchOmitsPendingStatusWhileReviewSearchIsExplicit() throws {
        let backend = URL(string: "http://backend")!
        let ordinary = MemorySearchRequest(
            query: "release evidence",
            projectRoot: "/tmp/repository",
            mode: "hybrid",
            status: MemorySearchScope.ordinary.requestStatus,
            limit: 50
        )
        let pending = MemorySearchRequest(
            query: "release evidence",
            projectRoot: "/tmp/repository",
            mode: "keyword",
            status: MemorySearchScope.pendingReview.requestStatus,
            limit: 5
        )
        let ordinaryRequest = try MemorySearchViewModel.makeSearchRequest(backendBase: backend, payload: ordinary)
        let pendingRequest = try MemorySearchViewModel.makeSearchRequest(backendBase: backend, payload: pending)
        let ordinaryData = try #require(ordinaryRequest.httpBody)
        let pendingData = try #require(pendingRequest.httpBody)
        let ordinaryObject = try #require(
            JSONSerialization.jsonObject(with: ordinaryData) as? [String: Any]
        )
        let pendingObject = try #require(
            JSONSerialization.jsonObject(with: pendingData) as? [String: Any]
        )

        #expect(ordinaryRequest.httpMethod == "POST")
        #expect(ordinaryRequest.url?.path == "/api/memory/search")
        #expect(ordinaryObject["status"] == nil)
        #expect(ordinaryObject["mode"] as? String == "hybrid")
        #expect(ordinaryObject["projectRoot"] as? String == "/tmp/repository")
        #expect(pendingObject["status"] as? String == "pending")
        #expect(pendingObject["mode"] as? String == "keyword")
        #expect(!MemorySearchScope.ordinary.includesPending)
        #expect(MemorySearchScope.pendingReview.includesPending)
    }

    @MainActor
    @Test func viewModelPostsSearchAndDecodesResultsForSelectedScope() async {
        var capturedBody: [String: Any] = [:]
        let body = """
        {
          "results": [{
            "id": "memory-1",
            "scope": "project",
            "type": "decision",
            "text": "Require evidence before promotion.",
            "status": "pending",
            "projectName": "fixture"
          }],
          "result_count": 1,
          "status_filter": "pending"
        }
        """.data(using: .utf8)!
        let viewModel = MemorySearchViewModel(dataLoader: { request in
            capturedBody = (try JSONSerialization.jsonObject(with: request.httpBody ?? Data()) as? [String: Any]) ?? [:]
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: "HTTP/1.1",
                headerFields: nil
            )!
            return (body, response)
        })
        viewModel.query = "promotion evidence"
        viewModel.scope = .pendingReview

        await viewModel.search(projectRoot: "/tmp/repository")

        #expect(capturedBody["status"] as? String == "pending")
        #expect(viewModel.errorMessage == nil)
        #expect(viewModel.resultCount == 1)
        #expect(viewModel.results.first?.status == "pending")
        #expect(viewModel.contentState == .success("1"))
    }

    @Test func mergedRetrievalUsesAllFiveRoutesAndKeepsPendingExplicit() throws {
        let backend = URL(string: "http://backend")!
        let ordinary = try MemorySearchViewModel.makeMergedRetrieveRequest(
            backendBase: backend,
            payload: MemoryMergedRetrieveRequest(
                query: "release evidence",
                routes: MemoryRetrievalRoute.allCases,
                projectRoot: "/tmp/repository",
                allProjects: false,
                status: MemorySearchScope.ordinary.requestStatus,
                reviewPending: MemorySearchScope.ordinary.includesPending,
                limit: 50,
                includeRouteResults: true
            )
        )
        let pending = try MemorySearchViewModel.makeMergedRetrieveRequest(
            backendBase: backend,
            payload: MemoryMergedRetrieveRequest(
                query: "candidate",
                routes: MemoryRetrievalRoute.allCases,
                projectRoot: nil,
                allProjects: false,
                status: MemorySearchScope.pendingReview.requestStatus,
                reviewPending: MemorySearchScope.pendingReview.includesPending,
                limit: 10,
                includeRouteResults: true
            )
        )
        let ordinaryData = try #require(ordinary.httpBody)
        let pendingData = try #require(pending.httpBody)
        let ordinaryBody = try #require(try JSONSerialization.jsonObject(with: ordinaryData) as? [String: Any])
        let pendingBody = try #require(try JSONSerialization.jsonObject(with: pendingData) as? [String: Any])

        #expect(ordinary.url?.path == "/api/memory/retrieve/merged")
        #expect(ordinary.timeoutInterval == 35)
        #expect(ordinaryBody["routes"] as? [String] == [
            "keyword", "embedding", "evidence_graph", "project_profile", "loop_recall",
        ])
        #expect(ordinaryBody["status"] == nil)
        #expect(ordinaryBody["reviewPending"] as? Bool == false)
        #expect(ordinaryBody["includeRouteResults"] as? Bool == true)
        #expect(pendingBody["status"] as? String == "pending")
        #expect(pendingBody["reviewPending"] as? Bool == true)
    }

    @Test func mergedRetrievalDecodesRankingRoutesAndDistilledProvenance() throws {
        let payload = Data("""
        {
          "strategy": "weighted-reciprocal-rank-fusion",
          "routes": ["keyword", "embedding", "evidence_graph", "project_profile", "loop_recall"],
          "local_only": true,
          "deterministic": true,
          "result_count": 1,
          "results": [{
            "entry": {
              "id": "mem-proposal-1",
              "scope": "project",
              "type": "decision",
              "text": "{\"memory_schema\":\"decision\",\"distilled_text\":\"Require evidence before release.\",\"governance\":{\"status\":\"active\",\"approval_required\":true,\"rollback_supported\":true},\"provenance\":{\"source_count\":2,\"sources\":[{\"memory_id\":\"mem-1\",\"status\":\"archived\"},{\"memory_id\":\"mem-2\",\"status\":\"active\"}]}}",
              "status": "active",
              "tags": ["distilled-memory"]
            },
            "reciprocal_rank_score": 0.031,
            "matched_route_count": 2,
            "merged_rank": 1,
            "classification": {"primary_schema": "decision", "schemas": ["decision"]},
            "explanation": {
              "routeContributions": [
                {"route": "keyword", "rank": 1, "route_weight": 1.15, "route_score": 0.9},
                {"route": "project_profile", "rank": 2, "route_weight": 0.95, "route_score": 0.8}
              ]
            }
          }],
          "route_results": [
            {"route": "keyword", "result_count": 3, "projection_used": false},
            {"route": "embedding", "result_count": 2, "projection_used": true}
          ]
        }
        """.utf8)

        let decoded = try JSONDecoder().decode(MemoryMergedRetrieveResponse.self, from: payload)
        let result = try #require(decoded.results.first)
        let proposal = try #require(result.distilledProposal)

        #expect(decoded.routes == MemoryRetrievalRoute.allCases)
        #expect(decoded.resultCount == 1)
        #expect(decoded.routeResults.first?.resultCount == 3)
        #expect(result.mergedRank == 1)
        #expect(result.routeContributions.map(\.route) == [.keyword, .projectProfile])
        #expect(proposal.distilledText == "Require evidence before release.")
        #expect(proposal.provenance.sourceCount == 2)
        #expect(proposal.provenance.sources.map(\.memoryId) == ["mem-1", "mem-2"])
        #expect(proposal.governance?.rollbackSupported == true)
    }

    @MainActor
    @Test func improveCreatesPendingSuggestionsWithoutAutomaticApproval() async throws {
        var paths: [String] = []
        var improveBody: [String: Any] = [:]
        let responseBody = Data("""
        {
          "status": "completed",
          "approval_required": true,
          "source_count": 3,
          "cluster_count": 1,
          "proposal_count": 1,
          "duplicate_proposal_count": 0,
          "proposals": [{
            "memory": {
              "id": "mem-proposal-1",
              "scope": "project",
              "type": "decision",
              "text": "proposal",
              "status": "pending"
            },
            "proposal": {
              "memory_schema": "decision",
              "distilled_text": "Use one release checklist.",
              "governance": {
                "status": "pending",
                "approval_required": true,
                "rollback_supported": true
              },
              "provenance": {
                "source_count": 2,
                "sources": [
                  {"memory_id": "mem-source-1", "status": "pending"},
                  {"memory_id": "mem-source-2", "status": "pending"}
                ]
              }
            }
          }]
        }
        """.utf8)
        let viewModel = MemorySearchViewModel(dataLoader: { request in
            paths.append(request.url?.path ?? "")
            improveBody = (try JSONSerialization.jsonObject(with: request.httpBody ?? Data()) as? [String: Any]) ?? [:]
            return (responseBody, Self.response(for: request, statusCode: 200))
        })

        await viewModel.improve(
            projectRoot: " /tmp/repository ",
            sourceIDs: ["mem-source-2", "mem-source-1", "mem-source-1"]
        )

        #expect(paths == ["/api/memory/improve"])
        #expect(improveBody["projectRoot"] as? String == "/tmp/repository")
        #expect(improveBody["sourceIds"] as? [String] == ["mem-source-1", "mem-source-2"])
        #expect(improveBody["similarityThreshold"] as? Double == 0.34)
        #expect(viewModel.proposals.first?.memory.status == "pending")
        #expect(viewModel.proposals.first?.proposal.provenance.sourceCount == 2)
        #expect(viewModel.improveState == .success("1"))
        #expect(viewModel.actionMessage == "1 suggestion ready for review.")
    }

    @MainActor
    @Test func approveAndRollbackUseGovernedRoutesAndSurfaceFailures() async throws {
        var requests: [URLRequest] = []
        let viewModel = MemorySearchViewModel(dataLoader: { request in
            requests.append(request)
            if request.url?.path.hasSuffix("/rollback") == true {
                let body = Data("""
                {"proposal_id":"mem-proposal-1","status":"archived","restored_source_ids":["mem-source-1"]}
                """.utf8)
                return (body, Self.response(for: request, statusCode: 200))
            }
            return (Data("{}".utf8), Self.response(for: request, statusCode: 200))
        })

        await viewModel.approve(memoryID: "mem-proposal-1", projectRoot: nil)
        await viewModel.rollback(memoryID: "mem-proposal-1", projectRoot: nil)

        #expect(requests.map { $0.url?.path } == [
            "/api/memory/memories/mem-proposal-1/status",
            "/api/memory/distilled/mem-proposal-1/rollback",
        ])
        let approveBody = try #require(requests.first?.httpBody)
        let approveObject = try #require(try JSONSerialization.jsonObject(with: approveBody) as? [String: Any])
        #expect(approveObject["status"] as? String == "active")
        #expect(requests.last?.httpBody == nil)
        #expect(viewModel.actionMessage == "1 original memory restored.")

        let failing = MemorySearchViewModel(dataLoader: { request in
            (Data("{\"detail\":\"Memory could not be restored\"}".utf8), Self.response(for: request, statusCode: 409))
        })
        await failing.rollback(memoryID: "mem-proposal-2", projectRoot: nil)
        #expect(failing.mutationErrorMessage != nil)
        #expect(failing.mutatingMemoryID == nil)
    }

    @MainActor
    @Test func mergedSearchReportsLoadingEmptyAndErrorStates() async {
        let empty = MemorySearchViewModel(dataLoader: { request in
            try await Task.sleep(for: .milliseconds(20))
            return (Data("{\"results\":[],\"result_count\":0}".utf8), Self.response(for: request, statusCode: 200))
        })
        empty.query = "nothing"
        let task = Task { await empty.search(projectRoot: nil) }
        await Task.yield()
        #expect(empty.contentState == .loading)
        await task.value
        #expect(empty.contentState == .empty)

        let failing = MemorySearchViewModel(dataLoader: { request in
            (Data("{\"detail\":\"Search unavailable\"}".utf8), Self.response(for: request, statusCode: 503))
        })
        failing.query = "release"
        await failing.search(projectRoot: nil)
        if case .error = failing.contentState {
            #expect(failing.results.isEmpty)
        } else {
            Issue.record("Expected an error content state")
        }
    }

    private static func response(for request: URLRequest, statusCode: Int) -> HTTPURLResponse {
        HTTPURLResponse(
            url: request.url!,
            statusCode: statusCode,
            httpVersion: "HTTP/1.1",
            headerFields: nil
        )!
    }
}
