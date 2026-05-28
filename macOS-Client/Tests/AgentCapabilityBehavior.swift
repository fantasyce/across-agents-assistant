import Foundation

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

func testProfileNormalizesLegacyLocalAgent() {
    let profile = AgentCapabilityProfile.defaultProfile(agentId: "local")

    assert(profile.agentId == "openclaw", "Legacy local agent id should normalize to openclaw")
    assert(profile.enabledSkillIds.contains("general_execution"), "OpenClaw should keep default general execution skill")
}

func testProfileTogglesSkillsPluginsAndTools() {
    var profile = AgentCapabilityProfile.defaultProfile(agentId: "hermes")

    profile.setSkill("backend_api", enabled: true)
    profile.setPlugin("filesystem", enabled: true)
    profile.setTool("read_file", enabled: true)
    profile.setTool("read_file", enabled: true)
    profile.setSkill("frontend_design", enabled: false)

    assert(profile.enabledSkillIds.contains("backend_api"), "Enabled skill should be added")
    assert(!profile.enabledSkillIds.contains("frontend_design"), "Disabled skill should be removed")
    assert(profile.enabledPluginIds == ["filesystem"], "Plugin list should stay stable and deduped")
    assert(profile.enabledToolNames == ["read_file"], "Tool list should stay stable and deduped")
}

func testConfiguredCapabilityCountIsStable() {
    var profile = AgentCapabilityProfile.defaultProfile(agentId: "deepseek")
    profile.enabledPluginIds = ["sqlite"]
    profile.enabledToolNames = ["sqlite__sqlite_query", "read_file"]
    profile.customInstructions = "Prefer explicit schemas."

    assert(
        AgentCapabilityCatalog.configuredCapabilityCount(profile) == 7,
        "Summary count should include skills, plugins, tools, and custom instructions"
    )
}

func testSkillDefinitionMarksCustomSkills() throws {
    let json = """
    {
      "id": "custom_accessibility_review",
      "name": "Accessibility Review",
      "description": "Review keyboard and contrast behavior.",
      "prompt_hint": "Check accessibility acceptance criteria.",
      "tags": ["frontend", "quality"],
      "source": "custom"
    }
    """.data(using: .utf8)!

    let skill = try JSONDecoder().decode(AgentSkillDefinition.self, from: json)

    assert(skill.isCustom, "Skills from the custom source should be marked custom")
}

func testPreflightResponseFindsBestRecommendation() {
    let preflight = AgentCapabilityPreflightResponse(
        selectedAgentIds: ["hermes", "deepseek"],
        recommendedAgentIds: ["hermes"],
        agentSummaries: [
            AgentCapabilityPreflightAgentSummary(
                agentId: "hermes",
                score: 6,
                matchedSkillIds: ["frontend_design", "custom_accessibility_review"],
                configuredCount: 4,
                warnings: []
            ),
            AgentCapabilityPreflightAgentSummary(
                agentId: "deepseek",
                score: 1,
                matchedSkillIds: ["data_modeling"],
                configuredCount: 3,
                warnings: []
            )
        ],
        warnings: [],
        promptPreview: "- hermes: skills=Frontend product design"
    )

    assert(preflight.bestRecommendedAgentId == "hermes", "Preflight should expose the first recommended agent")
    assert(preflight.bestSummary?.matchedSkillIds.contains("custom_accessibility_review") == true, "Best summary should keep matched skills")
}

func testNativeSkillModelsDecodeAgentStateAndEncodeInstallRequest() throws {
    let json = """
    {
      "agent_id": "claude",
      "display_name": "Claude Code",
      "mode": "directory",
      "supports_create": true,
      "supports_install": true,
      "supports_uninstall": true,
      "supports_update": false,
      "supports_check": true,
      "skills": [
        {
          "id": "release-gate",
          "name": "Release Gate",
          "description": "Check release evidence.",
          "status": "unavailable",
          "availability": "unavailable",
          "unavailable_reason": "Missing requirements: bins: memo",
          "missing_requirements": ["bins: memo"],
          "source": "user",
          "managed_by_app": true,
          "supports_uninstall": true
        }
      ]
    }
    """.data(using: .utf8)!

    let state = try JSONDecoder().decode(NativeSkillAgentState.self, from: json)
    let request = NativeSkillInstallRequest(
        identifier: nil,
        name: "Release Gate",
        description: "Check release evidence.",
        body: "Confirm tests before release.",
        scope: "user",
        projectDir: nil,
        sourcePath: nil,
        version: nil,
        force: false
    )
    let encoded = try JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any]

    assert(state.agentId == "claude", "Native skill state should decode agent id")
    assert(state.skills.first?.managedByApp == true, "Native skill should expose app ownership")
    assert(state.skills.first?.availability == "unavailable", "Native skill should expose availability")
    assert(state.skills.first?.unavailableReason == "Missing requirements: bins: memo", "Native skill should decode unavailable reason")
    assert(state.skills.first?.missingRequirements == ["bins: memo"], "Native skill should decode missing requirements")
    assert(state.skills.first?.isActive == false, "Unavailable native skill should not count as active")
    assert(state.installedCount == 0, "Native skill state should count only available skills")
    assert(encoded?["project_dir"] == nil, "Nil optional fields should be omitted")
    assert(encoded?["scope"] as? String == "user", "Native install request should encode snake-case fields")
}

@main
struct AgentCapabilityBehavior {
    static func main() {
        testProfileNormalizesLegacyLocalAgent()
        testProfileTogglesSkillsPluginsAndTools()
        testConfiguredCapabilityCountIsStable()
        try! testSkillDefinitionMarksCustomSkills()
        testPreflightResponseFindsBestRecommendation()
        try! testNativeSkillModelsDecodeAgentStateAndEncodeInstallRequest()
        print("AgentCapabilityBehavior passed")
    }
}
