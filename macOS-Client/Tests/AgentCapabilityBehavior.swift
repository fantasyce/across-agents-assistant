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
                matchedNativeSkillIds: ["swiftui-layout-review"],
                unavailableNativeSkillIds: [],
                nativeSkillRepairSuggestions: [],
                configuredCount: 4,
                warnings: []
            ),
            AgentCapabilityPreflightAgentSummary(
                agentId: "deepseek",
                score: 1,
                matchedSkillIds: ["data_modeling"],
                matchedNativeSkillIds: [],
                unavailableNativeSkillIds: ["apple-notes"],
                nativeSkillRepairSuggestions: ["Install required binary `memo` and make it available on PATH."],
                configuredCount: 3,
                warnings: []
            )
        ],
        warnings: [],
        promptPreview: "- hermes: skills=Frontend product design"
    )

    assert(preflight.bestRecommendedAgentId == "hermes", "Preflight should expose the first recommended agent")
    assert(preflight.bestSummary?.matchedSkillIds.contains("custom_accessibility_review") == true, "Best summary should keep matched skills")
    assert(preflight.bestSummary?.matchedNativeSkillIds.contains("swiftui-layout-review") == true, "Best summary should keep matched native skills")
    assert(preflight.agentSummaries[1].nativeSkillRepairSuggestions.count == 1, "Preflight should keep native skill repair guidance")
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
          "repair_suggestions": ["Install required binary `memo` and make it available on PATH."],
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
    assert(state.skills.first?.repairSuggestions == ["Install required binary `memo` and make it available on PATH."], "Native skill should decode repair suggestions")
    assert(state.skills.first?.isActive == false, "Unavailable native skill should not count as active")
    assert(state.installedCount == 0, "Native skill state should count only available skills")
    assert(encoded?["project_dir"] == nil, "Nil optional fields should be omitted")
    assert(encoded?["scope"] as? String == "user", "Native install request should encode snake-case fields")
}

func testReleaseEvaluationSummaryDecodesBackendPayload() throws {
    let json = """
    {
      "release_readiness": "attention",
      "evaluated_task_count": 2,
      "terminal_task_count": 3,
      "passed_task_count": 1,
      "blocked_task_count": 0,
      "manual_task_count": 1,
      "skipped_task_count": 0,
      "pass_rate": 0.5,
      "average_final_quality_score": 78,
      "total_remediation_count": 2,
      "recommendation": "Manual gate requires review.",
      "top_risks": [
        {"kind": "manual_or_skipped_gate", "severity": "medium", "count": 1, "message": "Manual gate requires review."}
      ],
      "recent_evaluations": [
        {"task_id": "task-release", "description": "Build release evidence", "status": "completed", "quality_gate": "passed", "final_quality_score": 88}
      ]
    }
    """.data(using: .utf8)!

    let summary = try JSONDecoder().decode(ReleaseEvaluationSummary.self, from: json)

    assert(summary.releaseReadiness == "attention", "Release readiness should decode from snake case")
    assert(summary.evaluatedTaskCount == 2, "Evaluated count should decode")
    assert(summary.topRisks.first?.kind == "manual_or_skipped_gate", "Top risks should decode")
    assert(summary.recentEvaluations.first?.taskId == "task-release", "Recent evaluations should decode")
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
        try! testReleaseEvaluationSummaryDecodesBackendPayload()
        print("AgentCapabilityBehavior passed")
    }
}
