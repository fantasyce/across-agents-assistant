import Foundation
import Combine

private struct AgentDetectResult: Decodable {
    let found: Bool
    let available: Bool?
    let status: String?
    let displayName: String?
    let executable: String?
    let path: String?
    let version: String?
    let error: String?
    let configuredPath: String?
    let source: String?
    let detectionMethod: String?
    let candidatePaths: [String]?

    enum CodingKeys: String, CodingKey {
        case found
        case available
        case status
        case displayName = "display_name"
        case executable
        case path
        case version
        case error
        case configuredPath = "configured_path"
        case source
        case detectionMethod = "detection_method"
        case candidatePaths = "candidate_paths"
    }
}

private struct AgentConfigRequest: Encodable {
    let agentId: String
    let executablePath: String?

    enum CodingKeys: String, CodingKey {
        case agentId = "agent_id"
        case executablePath = "executable_path"
    }
}

private struct AgentConfigSaveResponse: Decodable {
    let status: String
    let agent: AgentDetectResult?
}

private struct KeysCheckResultItem: Decodable {
    let provider_id: String
    let status: String
    let error: String?

    init(provider_id: String, status: String, error: String?) {
        self.provider_id = provider_id
        self.status = status
        self.error = error
    }
}

private struct KeyValueResponse: Decodable {
    let providerId: String
    let apiKey: String?

    enum CodingKeys: String, CodingKey {
        case providerId = "provider_id"
        case apiKey = "api_key"
    }
}

enum AvailabilityBootstrapState: Equatable {
    case loading
    case empty
    case ready
}

enum AgentDetectionFeedback: Equatable {
    case idle
    case detecting
    case found(String?)
    case notFound(String?)
    case failed(String)
}

@MainActor
final class SettingsViewModel: ObservableObject {
    @Published var localAgents: [AgentConfig] = []
    @Published var cloudLLMs: [LLMConfig] = []
    @Published var isLoading: Bool = false
    @Published var isCheckingKeys: Bool = false
    @Published var checkResultMessages: [String] = []
    @Published var lastErrorMessage: String? = nil
    @Published var availabilityBootstrapState: AvailabilityBootstrapState = .loading
    @Published var localAgentDetectionFeedback: [String: AgentDetectionFeedback] = [:]
    @Published var startupDiagnostics: StartupDiagnosticsReport? = nil
    @Published var isLoadingStartupDiagnostics: Bool = false
    @Published var startupDiagnosticsError: String? = nil
    @Published var releaseVerificationReport: ReleaseVerificationReport? = nil
    @Published var isRunningReleaseVerification: Bool = false
    @Published var releaseVerificationError: String? = nil

    private var cancellables = Set<AnyCancellable>()
    @Published var apiKeyStatusCache: [String: String] = [:]

    private let backendBase = "http://backend"
    private let localAgentIds: Set<String> = [AgentIDs.openclaw, "hermes", "claude"]
    private let cloudLLMIds: Set<String> = ["deepseek", "minimax"]
    private var didStartBootstrap = false
    private var didCompleteAvailabilityBootstrap = false
    private var didRefreshLocalAgentsThisSession = false
    private var isRefreshingLocalAgents = false

    func isKeyConfigured(_ providerId: String) -> Bool {
        return apiKeyStatusCache[providerId] == "configured"
    }

    func isLocalAgentAvailable(_ agentId: String) -> Bool {
        let normalizedAgentId = AgentIDs.normalized(agentId) ?? agentId
        return availableLocalAgents.contains { AgentIDs.normalized($0.id) == normalizedAgentId }
    }

    func isAgentAvailable(_ agentId: String) -> Bool {
        let normalizedAgentId = AgentIDs.normalized(agentId) ?? agentId
        return isLocalAgentAvailable(normalizedAgentId) || isKeyConfigured(normalizedAgentId)
    }

    var availableLocalAgents: [AgentConfig] {
        localAgents.filter { $0.status == .installed }
    }

    var availableCloudLLMs: [LLMConfig] {
        cloudLLMs.filter { isKeyConfigured($0.id) }
    }

    var hasAvailableLocalAgents: Bool {
        !availableLocalAgents.isEmpty
    }

    var hasAvailableCloudLLMs: Bool {
        !availableCloudLLMs.isEmpty
    }

    var hasAnyAvailableAgents: Bool {
        hasAvailableLocalAgents || hasAvailableCloudLLMs
    }

    var shouldShowRightSidebar: Bool {
        availabilityBootstrapState == .ready && hasAnyAvailableAgents
    }

    var visibleAgentIds: [String] {
        availableLocalAgents.map(\.id) + availableCloudLLMs.map(\.id)
    }

    func applyBackendKeyStatuses(_ providers: [String: String]) {
        var nextCache = apiKeyStatusCache
        for (providerId, status) in providers {
            nextCache[providerId] = status
        }
        apiKeyStatusCache = nextCache
        refreshAvailabilityState()
    }

    func applyStartupDiagnosticsReport(_ report: StartupDiagnosticsReport) {
        startupDiagnostics = report
        startupDiagnosticsError = nil
    }

    func applyReleaseVerificationReport(_ report: ReleaseVerificationReport) {
        releaseVerificationReport = report
        startupDiagnostics = report.startup
        releaseVerificationError = nil
    }

    init(bootstrapOnInit: Bool = true, loadPersisted: Bool = true) {
        if loadPersisted {
            loadPersistedSettings()
        } else {
            localAgents = [.localAgent, .hermes, .claude]
            cloudLLMs = [.deepSeek, .miniMax]
            apiKeyStatusCache = [:]
        }

        if bootstrapOnInit {
            bootstrapFromPersistedSettings()
        } else {
            availabilityBootstrapState = .loading
        }
    }

    func preferredAgentId(current: String?) -> String? {
        if let current = AgentIDs.normalized(current), visibleAgentIds.contains(current) {
            return current
        }
        if let cloud = availableCloudLLMs.first {
            return cloud.id
        }
        return availableLocalAgents.first?.id
    }

    func bootstrapFromPersistedSettings() {
        guard !didStartBootstrap else {
            refreshAvailabilityState()
            return
        }
        didStartBootstrap = true

        loadPersistedSettings()
        beginAvailabilityBootstrap()

        Task {
            await performInitialBootstrap()
        }
    }

    func loadSettings() {
        loadPersistedSettings()
        beginAvailabilityBootstrap()

        Task {
            guard await ensureBackendReady() else {
                failAvailabilityBootstrap("Unable to connect to the backend. Please restart the app.")
                return
            }
            await refreshBackendKeyStatus()
            await detectAgentsFromBackend(force: false)
            await refreshStartupDiagnostics()
            completeAvailabilityBootstrap()
        }
    }

    func refreshStartupDiagnostics() async {
        await MainActor.run {
            isLoadingStartupDiagnostics = true
            startupDiagnosticsError = nil
        }
        do {
            let url = URL(string: "\(backendBase)/api/diagnostics/startup")!
            let (data, response) = try await URLSession.shared.data(from: url)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                throw URLError(.badServerResponse)
            }
            let report = try JSONDecoder().decode(StartupDiagnosticsReport.self, from: data)
            await MainActor.run {
                applyStartupDiagnosticsReport(report)
                isLoadingStartupDiagnostics = false
            }
        } catch {
            await MainActor.run {
                startupDiagnosticsError = "Unable to load startup diagnostics: \(error.localizedDescription)"
                isLoadingStartupDiagnostics = false
            }
        }
    }

    func runReleaseVerification() async {
        await MainActor.run {
            isRunningReleaseVerification = true
            releaseVerificationError = nil
        }
        do {
            let url = URL(string: "\(backendBase)/api/release/verification")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                throw URLError(.badServerResponse)
            }
            let report = try JSONDecoder().decode(ReleaseVerificationReport.self, from: data)
            await MainActor.run {
                applyReleaseVerificationReport(report)
                isRunningReleaseVerification = false
            }
        } catch {
            await MainActor.run {
                releaseVerificationError = "Unable to run release verification: \(error.localizedDescription)"
                isRunningReleaseVerification = false
            }
        }
    }

    func fetchKeyStatus() {
        // Query backend for current key status (from credential store).
        // Reads only the backend-owned credentials file status.
        Task {
            await refreshKeyStatusFromBackend()
            refreshAvailabilityState()
        }
    }

    /// Send API keys to backend to populate its in-memory cache and environment variables.
    @discardableResult
    private func sendKeysToBackend(_ keys: [String: String]) async -> Bool {
        do {
            let url = URL(string: "\(backendBase)/api/keys")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(keys)
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                return false
            }
            return (200...299).contains(httpResponse.statusCode)
        } catch {
            print("Failed to sync keys to backend: \(error)")
            return false
        }
    }

    func saveAgentConfig(_ config: AgentConfig) {
        if let index = localAgents.firstIndex(where: { $0.id == config.id }) {
            localAgents[index] = config
        }
        persistLocalAgentSettings()
        refreshAvailabilityState()

        Task {
            await saveAgentConfigToBackend(config)
        }
    }

    func autoDetectAgent(_ agentId: String) {
        Task {
            localAgentDetectionFeedback[agentId] = .detecting
            let feedback = await detectSingleAgentFromBackend(agentId)
            localAgentDetectionFeedback[agentId] = feedback
            refreshAvailabilityState()
        }
    }

    /// Detect all local agents via backend API (has full PATH, unlike GUI app).
    @discardableResult
    private func detectAgentsFromBackend(force: Bool = false) async -> Bool {
        do {
            let suffix = force ? "?force=true" : ""
            let url = URL(string: "\(backendBase)/api/agents/detect\(suffix)")!
            let (data, response) = try await URLSession.shared.data(from: url)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                return false
            }
            let results = try JSONDecoder().decode([String: AgentDetectResult].self, from: data)

            for (agentId, result) in results {
                applyAgentDetectionResult(result, agentId: AgentIDs.normalized(agentId) ?? agentId)
            }
            didRefreshLocalAgentsThisSession = true
            persistLocalAgentSettings()
            refreshAvailabilityState()
            return true
        } catch {
            print("Failed to detect agents from backend: \(error)")
            return false
        }
    }

    private func refreshLocalAgentsAfterStartup() async {
        guard !isRefreshingLocalAgents else { return }
        isRefreshingLocalAgents = true
        let detected = await detectAgentsFromBackend(force: true)
        isRefreshingLocalAgents = false
        if !detected && !hasAnyAvailableAgents {
            lastErrorMessage = "Unable to refresh local agents. Please restart the app or open Model Settings."
        }
    }

    func ensureBackendReady(maxAttempts: Int = 30, retryDelayNanoseconds: UInt64 = 500_000_000) async -> Bool {
        for attempt in 0..<maxAttempts {
            if await pingBackend() {
                return true
            }
            if attempt < maxAttempts - 1 {
                try? await Task.sleep(nanoseconds: retryDelayNanoseconds)
            }
        }
        return false
    }

    func ensureChatAgentReady(agentId: String) async -> String? {
        guard hasAnyAvailableAgents else {
            return "No available Agent or LLM. Open Model Settings to configure one first."
        }

        guard await ensureBackendReady() else {
            return "The backend is not ready yet. Please try again shortly."
        }

        if cloudLLMIds.contains(agentId) {
            guard isKeyConfigured(agentId) else {
                return "The selected cloud model is not configured. Open Model Settings first."
            }
            let synced = await ensureBackendKeySyncIfNeeded(agentId)
            return synced ? nil : "The cloud model configuration has not synced to the backend yet. Please try again shortly."
        }

        let normalizedAgentId = AgentIDs.normalized(agentId) ?? agentId
        if localAgentIds.contains(normalizedAgentId) {
            return await ensureLocalAgentReadyIfNeeded(normalizedAgentId)
        }

        return nil
    }

    func ensureTaskSubmissionReady(ownerAgentId: String, subtaskAgentIds: [String] = []) async -> String? {
        guard hasAnyAvailableAgents else {
            return "No available Agent or LLM. Open Model Settings to configure one first."
        }

        guard await ensureBackendReady() else {
            return "The backend is not ready yet. Please try again shortly."
        }

        if ownerAgentId == "auto" {
            _ = await detectAgentsFromBackend(force: false)
            for llm in availableCloudLLMs {
                _ = await ensureBackendKeySyncIfNeeded(llm.id)
            }
            refreshAvailabilityState()
            return hasAnyAvailableAgents ? nil : "No available Agent or LLM. Open Model Settings to configure one first."
        }

        for agentId in subtaskAgentIds where cloudLLMIds.contains(agentId) {
            guard isKeyConfigured(agentId) else {
                return "The selected subtask cloud model is not configured. Open Model Settings first."
            }
            let synced = await ensureBackendKeySyncIfNeeded(agentId)
            if !synced {
                return "The selected subtask cloud model has not synced to the backend yet. Please try again shortly."
            }
        }

        if cloudLLMIds.contains(ownerAgentId) {
            guard isKeyConfigured(ownerAgentId) else {
                return "The selected cloud model is not configured. Open Model Settings first."
            }
            let synced = await ensureBackendKeySyncIfNeeded(ownerAgentId)
            return synced ? nil : "The selected cloud model has not synced to the backend yet. Please try again shortly."
        }

        let normalizedOwnerAgentId = AgentIDs.normalized(ownerAgentId) ?? ownerAgentId
        if localAgentIds.contains(normalizedOwnerAgentId) {
            return await ensureLocalAgentReadyIfNeeded(normalizedOwnerAgentId)
        }

        return nil
    }

    /// Refresh All: re-detect local agents, check only unconfigured cloud LLM keys.
    func checkAll() {
        guard !isCheckingKeys else { return }
        isCheckingKeys = true
        checkResultMessages = []
        lastErrorMessage = nil

        Task { [weak self] in
            guard let self = self else { return }
            await self.refreshKeyStatusFromBackend()
            await self.detectAgentsFromBackend(force: true)

            let cloudResults = await self.checkUnconfiguredProviders()

            var messages = cloudResults
            for agent in self.localAgents {
                let name = self.agentDisplayName(agent.id, fallback: agent.name)
                switch agent.status {
                case .installed:
                    messages.append("\(name): \(agent.version ?? "v?.?.?")")
                case .notInstalled:
                    messages.append("\(name): Not found")
                case .notAuthenticated:
                    messages.append("\(name): Not authenticated")
                case .unavailable:
                    messages.append("\(name): Installed but unavailable")
                case .invalidPath:
                    messages.append("\(name): Invalid path")
                }
            }
            self.checkResultMessages = messages
            self.isCheckingKeys = false
            self.completeAvailabilityBootstrap()
        }
    }

    // MARK: - Private

    private func loadPersistedSettings() {
        // Decode PersistedLLMConfig (no apiKey) from UserDefaults
        if let data = UserDefaults.standard.data(forKey: "cloudLLMs"),
           let saved = try? JSONDecoder().decode([PersistedLLMConfig].self, from: data) {
            cloudLLMs = saved.map { LLMConfig(from: $0) }
        } else {
            cloudLLMs = [.deepSeek, .miniMax]
        }

        // apiKeyStatusCache is built from backend status, NOT from persisted settings.
        // Querying backend will populate it from the backend-owned credential file.
        apiKeyStatusCache = [:]

        if let data = UserDefaults.standard.data(forKey: "localAgents"),
           let saved = try? JSONDecoder().decode([AgentConfig].self, from: data) {
            localAgents = mergeLocalAgentDefaults(saved)
            persistLocalAgentSettings()
        } else {
            localAgents = [.localAgent, .hermes, .claude]
        }

        // Rewrite any legacy persisted cloud settings in the current secret-free format.
        // This scrubs old `apiKey` fields from pre-migration UserDefaults payloads.
        persistCloudSettings()
    }

    private func performInitialBootstrap() async {
        let backendIsReady = await ensureBackendReady()
        guard backendIsReady else {
            failAvailabilityBootstrap("Unable to connect to the backend. Please restart the app.")
            return
        }

        // Query backend-owned credential state first; this is enough to let the
        // main UI leave startup loading when a cloud provider is configured.
        await refreshBackendKeyStatus()
        completeBackendReadyAvailabilityBootstrap()
        await refreshStartupDiagnostics()

        Task { [weak self] in
            await self?.refreshLocalAgentsAfterStartup()
        }

        if !apiKeyStatusCache.values.contains("configured") {
            // No configured providers from backend or elsewhere.
            // The UI will show "not configured" until the user saves a key.
        }
    }

    /// Query backend for current cloud LLM key status (from credential store).
    private func refreshKeyStatusFromBackend() async {
        do {
            let url = URL(string: "\(backendBase)/api/keys/status")!
            let (data, response) = try await URLSession.shared.data(from: url)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                return
            }
            if let statuses = try? JSONDecoder().decode([String: [String: String]].self, from: data),
               let providers = statuses["providers"] {
                applyBackendKeyStatuses(providers)
            }
        } catch {
            // Backend status query is best-effort; local cache may be stale.
        }
    }

    private func backendReportsProviderConfigured(_ providerId: String) async -> Bool {
        await refreshKeyStatusFromBackend()
        return apiKeyStatusCache[providerId] == "configured"
    }

    func refreshBackendKeyStatus() async {
        await checkBackendKeys()
        await refreshKeyStatusFromBackend()
        refreshAvailabilityState()
    }

    private func checkBackendKeys() async {
        guard let url = URL(string: "\(backendBase)/api/keys/check") else { return }
        do {
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                return
            }
        } catch {
            // Key check is best-effort; the follow-up status request still updates UI state.
        }
    }

    func loadAPIKeyFromBackend(_ providerId: String) async -> String? {
        guard let escapedProviderId = providerId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed),
              let url = URL(string: "\(backendBase)/api/keys/value/\(escapedProviderId)") else {
            return nil
        }

        do {
            let (data, response) = try await URLSession.shared.data(from: url)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                return nil
            }
            let result = try JSONDecoder().decode(KeyValueResponse.self, from: data)
            guard result.providerId == providerId,
                  let key = result.apiKey?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !key.isEmpty else {
                return nil
            }
            setBackendKeyStatus(providerId, status: "configured")
            if let index = cloudLLMs.firstIndex(where: { $0.id == providerId }) {
                cloudLLMs[index].apiKey = key
            }
            refreshAvailabilityState()
            return key
        } catch {
            print("Failed to load API key from backend: \(error)")
            return nil
        }
    }

    private func refreshAvailabilityState() {
        guard didCompleteAvailabilityBootstrap else {
            availabilityBootstrapState = .loading
            return
        }
        availabilityBootstrapState = hasAnyAvailableAgents ? .ready : .empty
    }

    func completeBackendReadyAvailabilityBootstrap() {
        completeAvailabilityBootstrap()
    }

    private func beginAvailabilityBootstrap() {
        didCompleteAvailabilityBootstrap = false
        didRefreshLocalAgentsThisSession = false
        availabilityBootstrapState = .loading
    }

    private func completeAvailabilityBootstrap() {
        didCompleteAvailabilityBootstrap = true
        refreshAvailabilityState()
    }

    private func failAvailabilityBootstrap(_ message: String) {
        didCompleteAvailabilityBootstrap = true
        lastErrorMessage = message
        availabilityBootstrapState = .empty
    }

    private func saveAgentConfigToBackend(_ config: AgentConfig) async {
        do {
            let url = URL(string: "\(backendBase)/api/agents/config")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(AgentConfigRequest(agentId: config.id, executablePath: config.configuredPath))
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                return
            }
            let result = try JSONDecoder().decode(AgentConfigSaveResponse.self, from: data)
            if let agent = result.agent {
                applyAgentDetectionResult(agent, agentId: config.id)
                persistLocalAgentSettings()
                refreshAvailabilityState()
            }
        } catch {
            print("Failed to save local agent config: \(error)")
        }
    }

    private func detectSingleAgentFromBackend(_ agentId: String) async -> AgentDetectionFeedback {
        guard let escaped = agentId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed),
              let url = URL(string: "\(backendBase)/api/agents/\(escaped)/detect") else {
            return .failed("Unable to build detection request.")
        }

        do {
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                let statusCode = (response as? HTTPURLResponse)?.statusCode ?? -1
                return .failed("Detection failed with HTTP \(statusCode).")
            }
            let result = try JSONDecoder().decode(AgentDetectResult.self, from: data)
            applyAgentDetectionResult(result, agentId: agentId)
            persistLocalAgentSettings()
            if result.found {
                return .found(result.path)
            }
            return .notFound(result.error)
        } catch {
            print("Failed to detect local agent \(agentId): \(error)")
            return .failed("Detection failed. Make sure the backend is running.")
        }
    }

    private func applyAgentDetectionResult(_ result: AgentDetectResult, agentId: String) {
        let normalizedAgentId = AgentIDs.normalized(agentId) ?? agentId
        guard let index = localAgents.firstIndex(where: { AgentIDs.normalized($0.id) == normalizedAgentId }) else { return }
        var updated = localAgents[index]
        if let displayName = result.displayName, !displayName.isEmpty {
            updated.name = displayName
        }
        updated.executablePath = result.path
        updated.version = result.version
        updated.configuredPath = result.configuredPath
        updated.source = result.source
        updated.detectionMethod = result.detectionMethod
        updated.error = result.error
        updated.candidatePaths = result.candidatePaths

        if result.found, result.available ?? result.found, result.path != nil {
            updated.status = .installed
        } else if result.status == "not_authenticated" {
            updated.status = .notAuthenticated
        } else if result.status == "invalid_path" {
            updated.status = .invalidPath
        } else if result.found {
            updated.status = .unavailable
        } else {
            updated.status = .notInstalled
        }
        localAgents[index] = updated
    }

    private func mergeLocalAgentDefaults(_ saved: [AgentConfig]) -> [AgentConfig] {
        let defaults: [AgentConfig] = [.localAgent, .hermes, .claude]
        return defaults.map { defaultAgent in
            guard var savedAgent = saved.first(where: { AgentIDs.normalized($0.id) == defaultAgent.id }) else {
                return defaultAgent
            }
            if savedAgent.id != defaultAgent.id {
                var migrated = defaultAgent
                migrated.executablePath = savedAgent.executablePath
                migrated.version = savedAgent.version
                migrated.status = savedAgent.status
                migrated.configuredPath = savedAgent.configuredPath
                migrated.source = savedAgent.source
                migrated.detectionMethod = savedAgent.detectionMethod
                migrated.error = savedAgent.error
                migrated.candidatePaths = savedAgent.candidatePaths
                savedAgent = migrated
            }
            if savedAgent.name.isEmpty {
                savedAgent.name = defaultAgent.name
            }
            return savedAgent
        }
    }

    private func pingBackend() async -> Bool {
        guard let url = URL(string: "\(backendBase)/api/health") else { return false }
        do {
            let (_, response) = try await URLSession.shared.data(from: url)
            guard let httpResponse = response as? HTTPURLResponse else {
                return false
            }
            return (200...299).contains(httpResponse.statusCode)
        } catch {
            return false
        }
    }

    private func ensureBackendKeySyncIfNeeded(_ providerId: String) async -> Bool {
        if await backendReportsProviderConfigured(providerId) {
            setBackendKeyStatus(providerId, status: "configured")
            return true
        }
        guard isKeyConfigured(providerId),
              let llm = cloudLLMs.first(where: { $0.id == providerId }),
              let key = llm.apiKey?.trimmingCharacters(in: .whitespacesAndNewlines),
              !key.isEmpty else {
            return false
        }
        let synced = await sendKeysToBackend([providerId: key])
        if synced {
            setBackendKeyStatus(providerId, status: "configured")
        }
        return synced
    }

    private func ensureLocalAgentReadyIfNeeded(_ agentId: String) async -> String? {
        if let cachedAgent = localAgents.first(where: { $0.id == agentId }),
           didRefreshLocalAgentsThisSession,
           cachedAgent.status == .installed {
            return nil
        }

        let detected = await detectAgentsFromBackend(force: false)
        refreshAvailabilityState()

        guard detected else {
            return "Unable to confirm local agent status. Please try again shortly."
        }

        guard let agent = localAgents.first(where: { $0.id == agentId }) else {
            return "The selected local agent does not exist."
        }

        switch agent.status {
        case .installed:
            return nil
        case .notInstalled:
            return "\(agent.name) is not installed or not executable. Configure it in your environment first."
        case .notAuthenticated:
            return "\(agent.name) is not authenticated. Complete authorization in the terminal first."
        case .unavailable:
            return "\(agent.name) is installed but failed the health check. Confirm it is running, logged in, and can complete a non-interactive task."
        case .invalidPath:
            return "\(agent.name) has an invalid executable path. Open Model Settings and choose a valid executable."
        }
    }

    private func agentDisplayName(_ id: String, fallback: String) -> String {
        switch id {
        case "openclaw", "local": return "OpenClaw"
        case "hermes": return "Hermes"
        case "claude": return "Claude"
        default: return fallback
        }
    }

    private func providerDisplayName(_ id: String) -> String {
        return id == "deepseek" ? "Deepseek" : "MiniMax"
    }

    private func checkUnconfiguredProviders() async -> [String] {
        var results: [String] = []
        for llm in cloudLLMs {
            let name = providerDisplayName(llm.id)
            if isKeyConfigured(llm.id) {
                results.append("\(name): Configured")
            } else {
                let result = await checkBackendProviderStatus(llm.id)
                switch result.status {
                case "configured": results.append("\(name): Configured")
                case "not_configured": results.append("\(name): Not configured")
                default: results.append("\(name): \(result.error ?? "Error")")
                }
            }
        }
        return results
    }

    private func checkBackendProviderStatus(_ providerId: String) async -> KeysCheckResultItem {
        // Backend-only provider status check (credential store, env, cache).
        // Safe for startup/refresh/status paths.
        do {
            let url = URL(string: "\(backendBase)/api/keys/check/\(providerId)")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
                return KeysCheckResultItem(provider_id: providerId, status: "error", error: "Backend error")
            }

            let result = try JSONDecoder().decode(KeysCheckResultItem.self, from: data)
            if result.status == "configured" {
                self.setBackendKeyStatus(providerId, status: "configured")
                return result
            }
            return result
        } catch {
            return KeysCheckResultItem(provider_id: providerId, status: "error", error: "Network error")
        }
    }

    func saveLLMConfig(_ config: LLMConfig) {
        if let index = cloudLLMs.firstIndex(where: { $0.id == config.id }) {
            cloudLLMs[index] = config
        }
        persistCloudSettings()

        if let apiKey = config.apiKey, !apiKey.isEmpty {
            // Persist secrets only through the backend-owned credential file
            // (~/.across_agents/credentials.json).
            Task {
                let saved = await sendKeysToBackend([config.id: apiKey])
                if saved {
                    self.setBackendKeyStatus(config.id, status: "configured")
                } else {
                    self.refreshAvailabilityState()
                }
            }
        } else {
            setBackendKeyStatus(config.id, status: nil)
        }
    }

    func deleteLLMConfig(_ providerId: String) {
        guard let index = cloudLLMs.firstIndex(where: { $0.id == providerId }) else { return }

        // Reset config to default (clear apiKey, endpoint, model)
        var defaultConfig: LLMConfig
        switch providerId {
        case "deepseek":
            defaultConfig = .deepSeek
        case "minimax":
            defaultConfig = .miniMax
        default:
            return
        }
        defaultConfig.apiKey = nil
        defaultConfig.endpoint = nil
        defaultConfig.model = nil
        cloudLLMs[index] = defaultConfig
        persistCloudSettings()

        // Clear local cache
        setBackendKeyStatus(providerId, status: nil)

        // Sync deletion to backend
        Task {
            await deleteKeyFromBackend(providerId)
        }
    }

    private func deleteKeyFromBackend(_ providerId: String) async {
        do {
            let url = URL(string: "\(backendBase)/api/keys/delete")!
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(["provider_id": providerId])
            let (_, _) = try await URLSession.shared.data(for: request)
        } catch {
            print("Failed to delete key from backend: \(error)")
        }
    }

    private func persistCloudSettings() {
        // Persist only non-secret config — apiKey is NOT included.
        let persisted = cloudLLMs.map { PersistedLLMConfig(from: $0) }
        if let data = try? JSONEncoder().encode(persisted) {
            UserDefaults.standard.set(data, forKey: "cloudLLMs")
        }
    }

    private func setBackendKeyStatus(_ providerId: String, status: String?) {
        var nextCache = apiKeyStatusCache
        if let status {
            nextCache[providerId] = status
        } else {
            nextCache.removeValue(forKey: providerId)
        }
        apiKeyStatusCache = nextCache
        refreshAvailabilityState()
    }

    private func persistLocalAgentSettings() {
        if let data = try? JSONEncoder().encode(localAgents) {
            UserDefaults.standard.set(data, forKey: "localAgents")
        }
    }
}
