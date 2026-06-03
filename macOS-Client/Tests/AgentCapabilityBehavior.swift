import Foundation

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

func testProfileDoesNotNormalizeLegacyLocalAgentAlias() {
    let profile = AgentCapabilityProfile.defaultProfile(agentId: "local")

    assert(profile.agentId == "local", "Legacy local agent id should remain separate")
    assert(profile.enabledSkillIds.isEmpty, "Legacy local should not inherit OpenClaw defaults")
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
      "generated_at": 1710000000,
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
      "gate_breakdown": {"passed": 1, "manual_required": 1},
      "probe_coverage": {
        "passed": {"browser_e2e": 1, "static_web_smoke": 1},
        "failed": {},
        "skipped": {},
        "manual_required": {"documentation": 1},
        "unknown": {},
        "required_probe_types": ["api_service", "browser_e2e", "cli_generic", "static_web_smoke"],
        "missing_required_probe_types": ["api_service", "cli_generic"],
        "satisfies_release_probe_coverage": false
      },
      "stack_coverage": {"web": 2, "api": 1},
      "agent_coverage": {"hermes": 2, "deepseek": 1},
      "recent_evaluations": [
        {
          "task_id": "task-release",
          "description": "Build release evidence",
          "status": "completed",
          "quality_gate": "passed",
          "final_quality_score": 88,
          "benchmark_status": "passed",
          "probe_summary": {"passed": ["browser_e2e"], "failed": [], "manual_required": [], "skipped": [], "unknown": []},
          "agent_mix": {"actual_agents": ["hermes", "openclaw", "deepseek"], "local_agents": ["hermes", "openclaw"], "cloud_agents": ["deepseek"]},
          "audit_trace": {"quality_gate": "passed", "final_quality_score": 88, "remediation_count": 1, "required_failed_count": 0, "manual_required_count": 0, "skipped_required_count": 0, "passed_probe_count": 4, "failed_probe_count": 0}
        }
      ]
    }
    """.data(using: .utf8)!

    let summary = try JSONDecoder().decode(ReleaseEvaluationSummary.self, from: json)

    assert(summary.releaseReadiness == "attention", "Release readiness should decode from snake case")
    assert(summary.evaluatedTaskCount == 2, "Evaluated count should decode")
    assert(summary.topRisks.first?.kind == "manual_or_skipped_gate", "Top risks should decode")
    assert(summary.recentEvaluations.first?.taskId == "task-release", "Recent evaluations should decode")
    assert(summary.generatedAt == 1710000000, "Generation time should decode")
    assert(summary.gateBreakdown["manual_required"] == 1, "Gate breakdown should decode")
    assert(summary.probeCoverage?.passed["browser_e2e"] == 1, "Probe coverage should decode passed probes")
    assert(summary.probeCoverage?.missingRequiredProbeTypes == ["api_service", "cli_generic"], "Missing release probes should decode")
    assert(summary.stackCoverage["web"] == 2, "Stack coverage should decode")
    assert(summary.agentCoverage["hermes"] == 2, "Agent coverage should decode")
    assert(summary.recentEvaluations.first?.auditTrace?.passedProbeCount == 4, "Recent audit trace should decode")
}

func testTaskEvidenceBundleAndBenchmarkDecodeForReleaseCenter() throws {
    let json = """
    {
      "schema_version": "1.0",
      "app_version": "0.3.1",
      "generated_at": 1710000123,
      "task_id": "task-d68f8fa8",
      "description": "Release E2E",
      "task_status": "completed",
      "task_types": ["functional", "artifact"],
      "delivery_mode": "composite",
      "project_dir": "/tmp/across-e2e",
      "owner_agent": "claude",
      "allowed_subtask_agents": ["hermes", "openclaw", "deepseek"],
      "delivery_contract": {"contract_id": "contract-release"},
      "requirement_manifest": {"requirements": [{"id": "req-web"}]},
      "quality_health": {"quality_gate": "passed", "delivery_quality": "passed"},
      "delivery_report": {"quality_gate": "passed", "final_status": "completed"},
      "benchmark": {
        "benchmark_id": "task-task-d68f8fa8-evidence-0.3.1",
        "benchmark_version": "1.0",
        "app_version": "0.3.1",
        "status": "passed",
        "summary": {"scenario_count": 1, "passed_scenarios": 1, "failed_scenarios": 0, "min_quality_score": 88, "max_remediation_attempts": 1},
        "scenarios": [
          {
            "task_id": "task-d68f8fa8",
            "status": "passed",
            "quality_gate": "passed",
            "final_status": "completed",
            "quality_score": 88,
            "remediation_attempts": 1,
            "produced_files": ["README.md", "web/index.html"],
            "checks": {"task_completed": true, "browser_e2e_passed": true},
            "failures": []
          }
        ]
      },
      "audit": {
        "read_only": true,
        "repair_or_resume_triggered": false,
        "secrets_redacted": true,
        "expected_files": ["README.md", "web/index.html"],
        "required_probes": ["browser_e2e"]
      }
    }
    """.data(using: .utf8)!

    let bundle = try JSONDecoder().decode(TaskEvidenceBundle.self, from: json)

    assert(bundle.taskId == "task-d68f8fa8", "Evidence bundle should decode task id")
    assert(bundle.audit.readOnly, "Evidence audit should expose read-only state")
    assert(bundle.audit.secretsRedacted, "Evidence audit should expose redaction state")
    assert(bundle.benchmark.status == "passed", "Nested benchmark should decode")
    assert(bundle.benchmark.scenarios.first?.checks["browser_e2e_passed"] == true, "Benchmark checks should decode")
    assert(bundle.releaseReadinessSummary == "passed · score 88 · 1 repair", "Evidence summary should be compact and stable")
    assert(TaskEvidenceBundle.exportFileName(taskId: "task-d68f8fa8") == "task-d68f8fa8-evidence-bundle.json", "Evidence export filename should be deterministic")
    assert(TaskEvidenceBundle.releaseE2EExpectedFiles == ["README.md", "web/index.html", "web/styles.css", "web/app.js", "api/server.mjs", "cli/quality-check.mjs", "tests/e2e-smoke.mjs"], "Release E2E evidence should use the exact manifest")
    assert(TaskEvidenceBundle.releaseE2ERequiredProbes == ["static_web_smoke", "browser_e2e", "api_service", "cli_generic"], "Release E2E UI evidence should request benchmark probe ids, not gate ids")
}

@main
struct AgentCapabilityBehavior {
    static func main() {
        testProfileDoesNotNormalizeLegacyLocalAgentAlias()
        testProfileTogglesSkillsPluginsAndTools()
        testConfiguredCapabilityCountIsStable()
        try! testSkillDefinitionMarksCustomSkills()
        testPreflightResponseFindsBestRecommendation()
        try! testNativeSkillModelsDecodeAgentStateAndEncodeInstallRequest()
        try! testReleaseEvaluationSummaryDecodesBackendPayload()
        try! testTaskEvidenceBundleAndBenchmarkDecodeForReleaseCenter()
        print("AgentCapabilityBehavior passed")
    }
}
