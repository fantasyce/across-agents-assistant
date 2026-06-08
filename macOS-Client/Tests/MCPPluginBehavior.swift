import Foundation
import Combine

enum AppDelegate {
    static let backendExecutablePath: String? = nil
}

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

func testAcrossContextPluginDoesNotRequireConfiguration() {
    let plugin = MCPPlugin(
        id: "across_context",
        name: "Across Context",
        description: "Shared memory for every agent.",
        command: "across-context",
        args: ["mcp"],
        env: nil,
        isEnabled: false,
        isBuiltIn: true,
        isReadOnly: false,
        configurationKind: .none
    )

    assert(plugin.requiresConfiguration == false, "Across Context should connect without a path or endpoint")
    assert(plugin.configurationPlaceholderKey == "mcp.noConfigurationRequired", "No-config plugins should use the no-config label")
    assert(plugin.configurationValue == nil, "Across Context should not expose a path-style configuration value")
}

func testPathPluginsStillRequireConfiguration() {
    let plugin = MCPPlugin(
        id: "filesystem",
        name: "Filesystem",
        description: "Scoped local file access.",
        command: "python3",
        args: ["-m", "mcp_filesystem", ""],
        env: nil,
        isEnabled: false,
        isBuiltIn: true,
        isReadOnly: false,
        configurationKind: .directory
    )

    assert(plugin.requiresConfiguration, "Filesystem should still require an explicit directory")
    assert(plugin.configurationPlaceholderKey == "mcp.noPath", "Directory plugins should use the path placeholder")
    assert(plugin.configurationValue == "", "Directory plugins should expose their last arg as the configuration value")
    assert(plugin.isConfigurationComplete == false, "Directory plugins with no selected path should not be connection-ready")
    assert(plugin.canAutoConnectOnLaunch == false, "Directory plugins without a selected path should not auto-connect")
}

func testBuiltInPluginsDefaultEnabledAndConfiguredBuiltInsAutoConnect() {
    UserDefaults.standard.removeObject(forKey: "across_agents_mcp_plugins")
    UserDefaults.standard.removeObject(forKey: "across_agents_mcp_plugins_default_enabled_migration_v044")
    MCPPluginManager.shared.loadPlugins()

    let plugins = Dictionary(uniqueKeysWithValues: MCPPluginManager.shared.plugins.map { ($0.id, $0) })
    for id in ["local_kb", "external_rag", "sqlite", "filesystem", "across_context"] {
        assert(plugins[id]?.isEnabled == true, "\(id) should be enabled by default")
    }
    assert(plugins["across_context"]?.canAutoConnectOnLaunch == true, "Across Context should auto-connect on launch")
    assert(plugins["filesystem"]?.canAutoConnectOnLaunch == false, "Filesystem should wait until a folder is configured")
    assert(plugins["sqlite"]?.isConfigurationComplete == false, "SQLite should wait for an explicit database file before connecting")

    var configuredFilesystem = plugins["filesystem"]!
    configuredFilesystem.args[configuredFilesystem.args.count - 1] = "/tmp"
    assert(configuredFilesystem.canAutoConnectOnLaunch == false, "Configured built-in filesystem should wait for a manual connect to avoid protected-directory prompts on launch")

    var configuredSQLite = plugins["sqlite"]!
    configuredSQLite.args[configuredSQLite.args.count - 1] = "/tmp/assistant.db"
    assert(configuredSQLite.canAutoConnectOnLaunch == false, "Configured built-in SQLite should wait for a manual connect to avoid protected-file prompts on launch")
}

func testAcrossContextDefaultsToExternalPluginMode() {
    UserDefaults.standard.removeObject(forKey: "across_agents_mcp_plugins")
    UserDefaults.standard.removeObject(forKey: "across_agents_mcp_plugins_default_enabled_migration_v044")
    MCPPluginManager.shared.loadPlugins()

    let acrossContext = MCPPluginManager.shared.plugins.first { $0.id == "across_context" }

    assert(acrossContext != nil, "Across Context should be a built-in MCP plugin")
    assert(acrossContext?.isEnabled == true, "Across Context should be enabled by default so shared memory is available on launch")
    assert(acrossContext?.canAutoConnectOnLaunch == true, "Across Context can auto-connect because it is an external plugin and does not require a user-selected protected directory")
    assert(
        acrossContext?.env?["ACROSS_AGENTS_ACROSS_CONTEXT_MODE"] == "external",
        "Across Context should default to the external MCP plugin so shared memory remains a pluggable module"
    )
}

func testAcrossContextImplementationLabelsAreStable() {
    var plugin = MCPPlugin(
        id: "across_context",
        name: "Across Context",
        description: "Shared memory for every agent.",
        command: "across-context",
        args: ["mcp"],
        env: nil,
        isEnabled: true,
        isBuiltIn: true,
        isReadOnly: false,
        configurationKind: .none
    )

    plugin.implementationMode = "external"
    assert(plugin.implementationLabelKey == "mcp.implementation.external", "External Across Context should be labeled as the plugin implementation")

    plugin.implementationMode = "builtin_compatibility"
    assert(plugin.implementationLabelKey == "mcp.implementation.builtinCompatibility", "Fallback should be labeled as built-in compatibility")

    plugin.implementationMode = nil
    assert(plugin.implementationLabelKey == nil, "Disconnected plugins should not show a stale implementation label")
}

@main
struct MCPPluginBehavior {
    static func main() {
        testAcrossContextPluginDoesNotRequireConfiguration()
        testPathPluginsStillRequireConfiguration()
        testBuiltInPluginsDefaultEnabledAndConfiguredBuiltInsAutoConnect()
        testAcrossContextDefaultsToExternalPluginMode()
        testAcrossContextImplementationLabelsAreStable()
        print("MCPPluginBehavior passed")
    }
}
