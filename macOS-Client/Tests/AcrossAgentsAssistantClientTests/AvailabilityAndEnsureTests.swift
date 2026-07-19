import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

@MainActor
@Suite(.serialized)
struct AvailabilityAndEnsureTests {
    private actor BackendKeyStub {
        private var providers: [String: String]

        init(configuredProviders: Set<String> = []) {
            providers = [
                "deepseek": configuredProviders.contains("deepseek") ? "configured" : "not_configured",
                "minimax": configuredProviders.contains("minimax") ? "configured" : "not_configured",
            ]
        }

        func load(_ request: URLRequest) throws -> (Data, URLResponse) {
            let url = try #require(request.url)
            let method = request.httpMethod ?? "GET"
            let statusCode: Int
            let data: Data

            switch (method, url.path) {
            case ("GET", "/api/health"):
                statusCode = 200
                data = Data(#"{"status":"ok"}"#.utf8)
            case ("GET", "/api/keys/status"):
                statusCode = 200
                data = try JSONEncoder().encode(["providers": providers])
            case ("POST", "/api/keys"):
                let keys = try JSONDecoder().decode([String: String].self, from: request.httpBody ?? Data())
                for (provider, key) in keys where !key.isEmpty {
                    providers[provider] = "configured"
                }
                statusCode = 200
                data = Data(#"{"status":"ok"}"#.utf8)
            default:
                statusCode = 404
                data = Data(#"{"detail":"not found"}"#.utf8)
            }

            let response = try #require(HTTPURLResponse(
                url: url,
                statusCode: statusCode,
                httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"]
            ))
            return (data, response)
        }

        func status(for provider: String) -> String? {
            providers[provider]
        }
    }

    private func makeViewModel(backend: BackendKeyStub = BackendKeyStub()) -> SettingsViewModel {
        let vm = SettingsViewModel(
            bootstrapOnInit: false,
            loadPersisted: false,
            backendBase: "http://isolated-backend",
            backendDataLoader: { request in try await backend.load(request) }
        )
        vm.localAgents = [.localAgent, .hermes, .claude, .codex]
        vm.cloudLLMs = [.deepSeek, .miniMax]
        vm.apiKeyStatusCache = [:]
        vm.availabilityBootstrapState = .empty
        return vm
    }

    private func refreshAvailabilityState(for vm: SettingsViewModel) {
        vm.availabilityBootstrapState = vm.hasAnyAvailableAgents ? .ready : .empty
    }

    @Test
    func emptyStateWhenNothingAvailable() {
        let vm = makeViewModel()

        refreshAvailabilityState(for: vm)

        #expect(vm.availabilityBootstrapState == .empty)
        #expect(!vm.hasAnyAvailableAgents)
        #expect(!vm.shouldShowRightSidebar)
        #expect(vm.availableLocalAgents.isEmpty)
        #expect(vm.availableCloudLLMs.isEmpty)
        #expect(vm.preferredAgentId(current: "deepseek") == nil)
    }

    @Test
    func localOnlyAvailability() {
        let vm = makeViewModel()
        vm.localAgents[0].status = .installed
        vm.localAgents[1].status = .notInstalled
        vm.localAgents[2].status = .notInstalled
        vm.localAgents[3].status = .notInstalled

        refreshAvailabilityState(for: vm)

        #expect(AgentIDs.normalized("openclaw") == "openclaw")
        #expect(AgentIDs.normalized("local") == "local")
        #expect(vm.availabilityBootstrapState == .ready)
        #expect(vm.hasAvailableLocalAgents)
        #expect(!vm.hasAvailableCloudLLMs)
        #expect(vm.availableLocalAgents.map(\.id) == ["openclaw"])
        #expect(vm.availableLocalAgents.map(\.name) == ["OpenClaw"])
        #expect(vm.visibleAgentIds == ["openclaw"])
        #expect(vm.preferredAgentId(current: nil) == "openclaw")
    }

    @Test
    func cloudOnlyAvailability() {
        let vm = makeViewModel()
        vm.cloudLLMs[0].apiKey = "deepseek-test-key"
        vm.apiKeyStatusCache["deepseek"] = "configured"

        refreshAvailabilityState(for: vm)

        #expect(vm.availabilityBootstrapState == .ready)
        #expect(!vm.hasAvailableLocalAgents)
        #expect(vm.hasAvailableCloudLLMs)
        #expect(vm.availableCloudLLMs.map(\.id) == ["deepseek"])
        #expect(vm.visibleAgentIds == ["deepseek"])
        #expect(vm.preferredAgentId(current: nil) == "deepseek")
    }

    @Test
    func preferredAgentFallsBackToCloudThenLocal() {
        let vm = makeViewModel()
        vm.localAgents[2].status = .installed
        vm.cloudLLMs[1].apiKey = "minimax-test-key"
        vm.apiKeyStatusCache["minimax"] = "configured"

        refreshAvailabilityState(for: vm)

        #expect(vm.preferredAgentId(current: "unknown") == "minimax")
        #expect(vm.preferredAgentId(current: "claude") == "claude")
    }

    @Test
    func ensureTaskSubmissionFailsFastWhenNothingAvailable() async {
        let vm = makeViewModel()

        let result = await vm.ensureTaskSubmissionReady(ownerAgentId: "auto")

        #expect(result == "No available Agent or LLM. Open Model Settings to configure one first.")
    }

    @Test
    func ensureChatAgentReadySyncsConfiguredCloudProviderToBackend() async throws {
        let backend = BackendKeyStub()
        let vm = makeViewModel(backend: backend)
        vm.cloudLLMs[0].apiKey = "deepseek-test-key"
        vm.apiKeyStatusCache["deepseek"] = "configured"
        refreshAvailabilityState(for: vm)

        let result = await vm.ensureChatAgentReady(agentId: "deepseek")

        #expect(result == nil)

        #expect(await backend.status(for: "deepseek") == "configured")
    }

    @Test
    func ensureTaskSubmissionReadyAllowsBackendConfiguredCloudProviderWithoutLocalApiKey() async {
        let vm = makeViewModel(backend: BackendKeyStub(configuredProviders: ["deepseek"]))
        vm.cloudLLMs[0].apiKey = nil
        vm.apiKeyStatusCache["deepseek"] = "configured"
        refreshAvailabilityState(for: vm)

        let result = await vm.ensureTaskSubmissionReady(ownerAgentId: "deepseek")

        #expect(result == nil)
    }

    @Test
    func ensureChatAgentReadyAllowsBackendConfiguredCloudProviderWithoutLocalApiKey() async {
        let vm = makeViewModel(backend: BackendKeyStub(configuredProviders: ["deepseek"]))
        vm.cloudLLMs[0].apiKey = nil
        vm.apiKeyStatusCache["deepseek"] = "configured"
        refreshAvailabilityState(for: vm)

        let result = await vm.ensureChatAgentReady(agentId: "deepseek")

        #expect(result == nil)
    }

    @Test
    func chatRequestTimeoutOutlivesDefaultLocalAgentTimeout() {
        #expect(SessionViewModel.longRunningAgentRequestTimeout >= 600)
    }

}
