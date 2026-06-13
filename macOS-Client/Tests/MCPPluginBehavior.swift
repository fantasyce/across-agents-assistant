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
    assert(plugins["filesystem"]?.canAutoConnectOnLaunch == true, "Filesystem should use the managed Across workspace by default")
    assert(plugins["sqlite"]?.canAutoConnectOnLaunch == true, "SQLite should use the managed Across app database by default")
    assert(plugins["local_kb"]?.canAutoConnectOnLaunch == true, "Local knowledge base should use the managed Across knowledge directory by default")
    assert(plugins["filesystem"]?.args.last?.contains("/.across/data/across-agents-assistant/workspace") == true, "Filesystem default path should stay under the unified Across data directory")
    assert(plugins["sqlite"]?.args.last?.contains("/.across/data/across-agents-assistant/assistant.db") == true, "SQLite default path should stay under the unified Across data directory")
    assert(plugins["local_kb"]?.args.last?.contains("/.across/data/across-agents-assistant/local-knowledge") == true, "Local knowledge base default path should stay under the unified Across data directory")

    var configuredFilesystem = plugins["filesystem"]!
    configuredFilesystem.args[configuredFilesystem.args.count - 1] = "/tmp"
    assert(configuredFilesystem.canAutoConnectOnLaunch == true, "Configured built-in filesystem should auto-connect on launch")

    var configuredSQLite = plugins["sqlite"]!
    configuredSQLite.args[configuredSQLite.args.count - 1] = "/tmp/assistant.db"
    assert(configuredSQLite.canAutoConnectOnLaunch == true, "Configured built-in SQLite should auto-connect on launch")

    var configuredLocalKB = plugins["local_kb"]!
    configuredLocalKB.args[configuredLocalKB.args.count - 1] = "/tmp/wiki"
    assert(configuredLocalKB.canAutoConnectOnLaunch == true, "Configured built-in local knowledge base should auto-connect on launch")

    var configuredExternalRAG = plugins["external_rag"]!
    configuredExternalRAG.args[configuredExternalRAG.args.count - 1] = "http://127.0.0.1:8080"
    assert(configuredExternalRAG.canAutoConnectOnLaunch == false, "External RAG should remain manual to avoid launch-time network calls")
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

func testSavedBuiltInPathsInObsoleteAcrossHiddenDirsUseManagedDefaults() {
    let key = "across_agents_mcp_plugins"
    let migrationKey = "across_agents_mcp_plugins_default_enabled_migration_v044"
    UserDefaults.standard.removeObject(forKey: migrationKey)
    let oldRoot = NSHomeDirectory() + "/.across_agents"
    let saved = [
        MCPPlugin(
            id: "sqlite",
            name: "SQLite Database",
            description: "Saved old SQLite path.",
            command: "python3",
            args: ["-m", "mcp_sqlite", "--db-path", oldRoot + "/assistant.db"],
            isEnabled: true,
            isBuiltIn: true,
            configurationKind: .file
        ),
        MCPPlugin(
            id: "filesystem",
            name: "Local Filesystem",
            description: "Saved old filesystem path.",
            command: "python3",
            args: ["-m", "mcp_filesystem", NSHomeDirectory() + "/.across-orchestrator"],
            isEnabled: true,
            isBuiltIn: true,
            configurationKind: .directory
        )
    ]
    let data = try! JSONEncoder().encode(saved)
    UserDefaults.standard.set(data, forKey: key)

    MCPPluginManager.shared.loadPlugins()

    let plugins = Dictionary(uniqueKeysWithValues: MCPPluginManager.shared.plugins.map { ($0.id, $0) })
    assert(plugins["sqlite"]?.args.last?.contains("/.across/data/across-agents-assistant/assistant.db") == true, "Saved SQLite path inside an obsolete Across hidden directory should be replaced by the managed app database")
    assert(plugins["filesystem"]?.args.last?.contains("/.across/data/across-agents-assistant/workspace") == true, "Saved filesystem path inside an obsolete Across hidden directory should be replaced by the managed workspace")

    UserDefaults.standard.removeObject(forKey: key)
    UserDefaults.standard.removeObject(forKey: migrationKey)
}

func testEmptySavedBuiltInPathsUseManagedDefaults() {
    let key = "across_agents_mcp_plugins"
    let migrationKey = "across_agents_mcp_plugins_default_enabled_migration_v044"
    UserDefaults.standard.removeObject(forKey: migrationKey)
    let saved = [
        MCPPlugin(
            id: "local_kb",
            name: "Local Knowledge Base",
            description: "Saved empty knowledge path.",
            command: "python3",
            args: ["-m", "mcp_local_kb", "--dir", ""],
            isEnabled: true,
            isBuiltIn: true,
            configurationKind: .directory
        ),
        MCPPlugin(
            id: "sqlite",
            name: "SQLite Database",
            description: "Saved empty SQLite path.",
            command: "python3",
            args: ["-m", "mcp_sqlite", "--db-path", ""],
            isEnabled: true,
            isBuiltIn: true,
            configurationKind: .file
        ),
        MCPPlugin(
            id: "filesystem",
            name: "Local Filesystem",
            description: "Saved empty filesystem path.",
            command: "python3",
            args: ["-m", "mcp_filesystem", ""],
            isEnabled: true,
            isBuiltIn: true,
            configurationKind: .directory
        )
    ]
    let data = try! JSONEncoder().encode(saved)
    UserDefaults.standard.set(data, forKey: key)

    MCPPluginManager.shared.loadPlugins()

    let plugins = Dictionary(uniqueKeysWithValues: MCPPluginManager.shared.plugins.map { ($0.id, $0) })
    assert(plugins["local_kb"]?.args.last?.contains("/.across/data/across-agents-assistant/local-knowledge") == true, "Empty local knowledge path should be replaced by the managed knowledge directory")
    assert(plugins["sqlite"]?.args.last?.contains("/.across/data/across-agents-assistant/assistant.db") == true, "Empty SQLite path should be replaced by the managed app database")
    assert(plugins["filesystem"]?.args.last?.contains("/.across/data/across-agents-assistant/workspace") == true, "Empty filesystem path should be replaced by the managed workspace")

    UserDefaults.standard.removeObject(forKey: key)
    UserDefaults.standard.removeObject(forKey: migrationKey)
}

func testSavedBuiltInDocumentsDefaultsUseManagedDefaults() {
    let key = "across_agents_mcp_plugins"
    let migrationKey = "across_agents_mcp_plugins_default_enabled_migration_v044"
    UserDefaults.standard.removeObject(forKey: migrationKey)
    let documents = NSHomeDirectory() + "/Documents"
    let saved = [
        MCPPlugin(
            id: "local_kb",
            name: "Local Knowledge Base",
            description: "Saved old Documents knowledge path.",
            command: "python3",
            args: ["-m", "mcp_local_kb", "--dir", documents + "/mywiki"],
            isEnabled: true,
            isBuiltIn: true,
            configurationKind: .directory
        ),
        MCPPlugin(
            id: "filesystem",
            name: "Local Filesystem",
            description: "Saved old Documents filesystem path.",
            command: "python3",
            args: ["-m", "mcp_filesystem", documents],
            isEnabled: true,
            isBuiltIn: true,
            configurationKind: .directory
        )
    ]
    let data = try! JSONEncoder().encode(saved)
    UserDefaults.standard.set(data, forKey: key)

    MCPPluginManager.shared.loadPlugins()

    let plugins = Dictionary(uniqueKeysWithValues: MCPPluginManager.shared.plugins.map { ($0.id, $0) })
    assert(plugins["local_kb"]?.args.last?.contains("/.across/data/across-agents-assistant/local-knowledge") == true, "Old Documents local knowledge default should be replaced by the managed knowledge directory")
    assert(plugins["filesystem"]?.args.last?.contains("/.across/data/across-agents-assistant/workspace") == true, "Old Documents filesystem default should be replaced by the managed workspace")

    UserDefaults.standard.removeObject(forKey: key)
    UserDefaults.standard.removeObject(forKey: migrationKey)
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

    plugin.implementationMode = "standard_mcp"
    assert(plugin.implementationLabelKey == "mcp.implementation.standard", "Standard MCP plugins should use the standard MCP label")

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
        testSavedBuiltInPathsInObsoleteAcrossHiddenDirsUseManagedDefaults()
        testEmptySavedBuiltInPathsUseManagedDefaults()
        testSavedBuiltInDocumentsDefaultsUseManagedDefaults()
        testAcrossContextImplementationLabelsAreStable()
        print("MCPPluginBehavior passed")
    }
}
