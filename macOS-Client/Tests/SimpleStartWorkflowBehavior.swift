import Foundation

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

func testPresetCatalog() {
    assert(
        SimpleStartWorkflowPreset.allCases.map(\.id) == [
            "repository-quality-copilot",
            "plugin-compatibility-lab",
            "release-captain"
        ],
        "Simple Start should expose the three flagship workflows in a stable order"
    )
    for preset in SimpleStartWorkflowPreset.allCases {
        assert(
            preset.deliveryTaskTypes == [.artifact, .functional],
            "\(preset.id) should request functional and artifact delivery gates"
        )
        assert(
            !preset.titleKey.isEmpty && !preset.subtitleKey.isEmpty && !preset.actionKey.isEmpty,
            "\(preset.id) should provide localization keys"
        )
    }
}

func testRepositoryQualityDraft() {
    let draft = SimpleStartWorkflowPreset.repositoryQuality.makeDraft(
        projectDirectory: "/tmp/across"
    )
    assert(draft.projectDirectory == "/tmp/across", "Repository Quality should preserve the selected project directory")
    assert(draft.taskTypeValues == ["artifact", "functional"], "Repository Quality should submit both delivery task types")
    assert(draft.taskDescription.contains("Repository Quality Copilot"), "Repository Quality draft should name the workflow")
    assert(draft.taskDescription.contains("release-readiness"), "Repository Quality draft should include release readiness evidence")
    assert(draft.taskDescription.contains("redacted pending memory"), "Repository Quality draft should preserve memory redaction boundaries")
}

func testPluginCompatibilityDraft() {
    let draft = SimpleStartWorkflowPreset.pluginCompatibility.makeDraft(
        target: "https://github.com/acme/example-mcp",
        projectDirectory: "  /tmp/plugin-lab  "
    )
    assert(draft.projectDirectory == "/tmp/plugin-lab", "Plugin Compatibility should trim the project directory")
    assert(draft.taskDescription.contains("Plugin Compatibility Lab v2"), "Plugin Compatibility draft should name the workflow")
    assert(draft.taskDescription.contains("https://github.com/acme/example-mcp"), "Plugin Compatibility draft should include the candidate target")
    assert(draft.taskDescription.contains("MCP Tasks"), "Plugin Compatibility draft should include MCP Tasks projection evidence")
    assert(draft.taskDescription.contains("LF A2A v2"), "Plugin Compatibility draft should include LF A2A v2 projection evidence")
    assert(draft.taskDescription.contains("AG-UI"), "Plugin Compatibility draft should include AG-UI projection evidence")
    assert(draft.taskDescription.contains("Remote MCP/OAuth"), "Plugin Compatibility draft should include remote MCP OAuth evidence")
    assert(draft.taskDescription.contains("OTel export"), "Plugin Compatibility draft should include OTel evidence")
    assert(draft.taskDescription.contains("redacted pending memory"), "Plugin Compatibility draft should preserve memory redaction boundaries")
}

func testReleaseCaptainDraft() {
    let draft = SimpleStartWorkflowPreset.releaseCaptain.makeDraft()
    assert(draft.projectDirectory == nil, "Release Captain should allow the project directory to be selected later")
    assert(draft.taskDescription.contains("Release Captain"), "Release Captain draft should name the workflow")
    assert(draft.taskDescription.contains("producer pins"), "Release Captain draft should include producer pin checks")
    assert(draft.taskDescription.contains("Live E2E readiness"), "Release Captain draft should include Live E2E readiness")
    assert(draft.taskDescription.contains("human-review attention"), "Release Captain draft should stop at human-review attention items")
}

@main
struct SimpleStartWorkflowBehavior {
    static func main() {
        testPresetCatalog()
        testRepositoryQualityDraft()
        testPluginCompatibilityDraft()
        testReleaseCaptainDraft()
        print("SimpleStartWorkflowBehavior passed")
    }
}
