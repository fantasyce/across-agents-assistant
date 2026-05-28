import Foundation
import Combine

private struct AgentCapabilitySaveResponse: Decodable {
    let status: String
    let profile: AgentCapabilityProfile
}

@MainActor
final class AgentCapabilityViewModel: ObservableObject {
    @Published var skillCatalog: [AgentSkillDefinition] = []
    @Published var profiles: [String: AgentCapabilityProfile] = [:]
    @Published var availableTools: [AgentCapabilityToolSchema] = []
    @Published var nativeSkillAgents: [String: NativeSkillAgentState] = [:]
    @Published var isLoading = false
    @Published var isSaving = false
    @Published var isNativeSkillWorking = false
    @Published var errorMessage: String?
    @Published var nativeSkillMessage: String?
    @Published var lastSavedAgentId: String?

    private let backendBase = "http://backend"

    func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            guard let url = URL(string: "\(backendBase)/api/agent-capabilities") else {
                return
            }
            let (data, response) = try await URLSession.shared.data(from: url)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                throw URLError(.badServerResponse)
            }
            let decoded = try JSONDecoder().decode(AgentCapabilityListResponse.self, from: data)
            skillCatalog = decoded.skills
            profiles = decoded.profiles
            availableTools = decoded.availableTools.sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
            await loadNativeSkills()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func profile(for agentId: String) -> AgentCapabilityProfile {
        let normalized = AgentIDs.normalized(agentId) ?? agentId
        return profiles[normalized] ?? AgentCapabilityProfile.defaultProfile(agentId: normalized)
    }

    func nativeSkillState(for agentId: String) -> NativeSkillAgentState? {
        let normalized = AgentIDs.normalized(agentId) ?? agentId
        return nativeSkillAgents[normalized]
    }

    func setSkill(_ skillId: String, enabled: Bool, for agentId: String) {
        mutateProfile(for: agentId) { profile in
            profile.setSkill(skillId, enabled: enabled)
        }
    }

    func setPlugin(_ pluginId: String, enabled: Bool, for agentId: String) {
        mutateProfile(for: agentId) { profile in
            profile.setPlugin(pluginId, enabled: enabled)
        }
    }

    func setTool(_ toolName: String, enabled: Bool, for agentId: String) {
        mutateProfile(for: agentId) { profile in
            profile.setTool(toolName, enabled: enabled)
        }
    }

    func setCustomInstructions(_ value: String, for agentId: String) {
        mutateProfile(for: agentId) { profile in
            profile.customInstructions = value
        }
    }

    func setStrictToolScope(_ value: Bool, for agentId: String) {
        mutateProfile(for: agentId) { profile in
            profile.strictToolScope = value
        }
    }

    func resetProfile(for agentId: String) {
        let normalized = AgentIDs.normalized(agentId) ?? agentId
        profiles[normalized] = AgentCapabilityProfile.defaultProfile(agentId: normalized)
    }

    func saveProfile(for agentId: String) async {
        let normalized = AgentIDs.normalized(agentId) ?? agentId
        let profile = profile(for: normalized)
        isSaving = true
        errorMessage = nil
        defer { isSaving = false }

        do {
            guard let escaped = normalized.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed),
                  let url = URL(string: "\(backendBase)/api/agent-capabilities/\(escaped)") else {
                return
            }
            var request = URLRequest(url: url)
            request.httpMethod = "PUT"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(AgentCapabilityUpdateRequest(profile: profile))

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                throw URLError(.badServerResponse)
            }
            let decoded = try JSONDecoder().decode(AgentCapabilitySaveResponse.self, from: data)
            profiles[decoded.profile.agentId] = decoded.profile
            lastSavedAgentId = decoded.profile.agentId
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func createCustomSkill(
        name: String,
        description: String,
        promptHint: String,
        tags: [String]
    ) async {
        isSaving = true
        errorMessage = nil
        defer { isSaving = false }

        do {
            guard let url = URL(string: "\(backendBase)/api/agent-capabilities/skills") else {
                return
            }
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONEncoder().encode(
                AgentCapabilitySkillRequest(
                    id: nil,
                    name: name,
                    description: description,
                    promptHint: promptHint,
                    tags: tags
                )
            )

            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                throw URLError(.badServerResponse)
            }
            let decoded = try JSONDecoder().decode(AgentCapabilitySkillSaveResponse.self, from: data)
            skillCatalog.removeAll { $0.id == decoded.skill.id }
            skillCatalog.append(decoded.skill)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func deleteCustomSkill(_ skillId: String) async {
        isSaving = true
        errorMessage = nil
        defer { isSaving = false }

        do {
            guard let escaped = skillId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed),
                  let url = URL(string: "\(backendBase)/api/agent-capabilities/skills/\(escaped)") else {
                return
            }
            var request = URLRequest(url: url)
            request.httpMethod = "DELETE"

            let (_, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                throw URLError(.badServerResponse)
            }
            skillCatalog.removeAll { $0.id == skillId }
            profiles = profiles.mapValues { profile in
                var updated = profile
                updated.enabledSkillIds.removeAll { $0 == skillId }
                return updated
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadNativeSkills() async {
        do {
            guard let url = URL(string: "\(backendBase)/api/native-skills") else {
                return
            }
            let (data, response) = try await URLSession.shared.data(from: url)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                throw URLError(.badServerResponse)
            }
            let decoded = try JSONDecoder().decode(NativeSkillListResponse.self, from: data)
            nativeSkillAgents = decoded.agents
        } catch {
            nativeSkillMessage = error.localizedDescription
        }
    }

    func installNativeSkill(
        for agentId: String,
        request: NativeSkillInstallRequest
    ) async {
        await mutateNativeSkill(
            for: agentId,
            path: "install",
            method: "POST",
            body: request
        )
    }

    func uninstallNativeSkill(_ skillId: String, for agentId: String) async {
        let normalized = AgentIDs.normalized(agentId) ?? agentId
        guard let escapedAgent = normalized.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed),
              let escapedSkill = skillId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed),
              let url = URL(string: "\(backendBase)/api/native-skills/\(escapedAgent)/\(escapedSkill)") else {
            return
        }
        await runNativeSkillMutation(url: url, method: "DELETE", body: Optional<NativeSkillInstallRequest>.none)
    }

    func updateNativeSkill(_ skillId: String, for agentId: String) async {
        let normalized = AgentIDs.normalized(agentId) ?? agentId
        guard let escapedAgent = normalized.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed),
              let escapedSkill = skillId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed),
              let url = URL(string: "\(backendBase)/api/native-skills/\(escapedAgent)/\(escapedSkill)/update") else {
            return
        }
        await runNativeSkillMutation(url: url, method: "POST", body: NativeSkillInstallRequest.empty)
    }

    private func mutateProfile(
        for agentId: String,
        _ mutate: (inout AgentCapabilityProfile) -> Void
    ) {
        let normalized = AgentIDs.normalized(agentId) ?? agentId
        var profile = profiles[normalized] ?? AgentCapabilityProfile.defaultProfile(agentId: normalized)
        mutate(&profile)
        profiles[normalized] = profile
    }

    private func mutateNativeSkill(
        for agentId: String,
        path: String,
        method: String,
        body: NativeSkillInstallRequest
    ) async {
        let normalized = AgentIDs.normalized(agentId) ?? agentId
        guard let escapedAgent = normalized.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed),
              let url = URL(string: "\(backendBase)/api/native-skills/\(escapedAgent)/\(path)") else {
            return
        }
        await runNativeSkillMutation(url: url, method: method, body: body)
    }

    private func runNativeSkillMutation<T: Encodable>(
        url: URL,
        method: String,
        body: T?
    ) async {
        isNativeSkillWorking = true
        nativeSkillMessage = nil
        defer { isNativeSkillWorking = false }

        do {
            var request = URLRequest(url: url)
            request.httpMethod = method
            if let body {
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.httpBody = try JSONEncoder().encode(body)
            }
            let (_, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  (200...299).contains(httpResponse.statusCode) else {
                throw URLError(.badServerResponse)
            }
            await loadNativeSkills()
        } catch {
            nativeSkillMessage = error.localizedDescription
        }
    }
}

private extension NativeSkillInstallRequest {
    static let empty = NativeSkillInstallRequest(
        identifier: nil,
        name: nil,
        description: nil,
        body: nil,
        scope: "user",
        projectDir: nil,
        sourcePath: nil,
        version: nil,
        force: false
    )
}
