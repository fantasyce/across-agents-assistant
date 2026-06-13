import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

@MainActor
@Suite(.serialized)
struct AvailabilityAndEnsureTests {
    private func makeViewModel() -> SettingsViewModel {
        UnixSocketProtocol.register()
        let vm = SettingsViewModel(bootstrapOnInit: false, loadPersisted: false)
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
        let vm = makeViewModel()
        vm.cloudLLMs[0].apiKey = "deepseek-test-key"
        vm.apiKeyStatusCache["deepseek"] = "configured"
        refreshAvailabilityState(for: vm)

        let result = await vm.ensureChatAgentReady(agentId: "deepseek")

        #expect(result == nil)

        let status = try await fetchBackendKeyStatus()
        #expect(status["deepseek"] == "configured")
    }

    @Test
    func ensureTaskSubmissionReadyAllowsBackendConfiguredCloudProviderWithoutLocalApiKey() async {
        let vm = makeViewModel()
        vm.cloudLLMs[0].apiKey = nil
        vm.apiKeyStatusCache["deepseek"] = "configured"
        refreshAvailabilityState(for: vm)

        let result = await vm.ensureTaskSubmissionReady(ownerAgentId: "deepseek")

        #expect(result == nil)
    }

    @Test
    func ensureChatAgentReadyAllowsBackendConfiguredCloudProviderWithoutLocalApiKey() async {
        let vm = makeViewModel()
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

    private func fetchBackendKeyStatus() async throws -> [String: String] {
        let url = URL(string: "http://backend/api/keys/status")!
        let (data, response) = try await URLSession.shared.data(from: url)
        let httpResponse = try #require(response as? HTTPURLResponse)
        #expect(httpResponse.statusCode == 200)

        struct Response: Decodable {
            let providers: [String: String]
        }

        let decoded = try JSONDecoder().decode(Response.self, from: data)
        return decoded.providers
    }
}
