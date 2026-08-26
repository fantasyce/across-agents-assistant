import Foundation
import Combine

enum AppDelegate {
    static let backendExecutablePath: String? = nil
}

enum StartupTelemetry {
    static func mark(_ stage: String) {}
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

func testEnabledCustomLocalPluginCanReconnectOnLaunch() {
    let plugin = MCPPlugin(
        id: "agent-runtime-proof",
        name: "Agent Runtime Proof",
        description: "Read-only runtime evidence.",
        command: "agent-runtime-proof",
        args: ["mcp"],
        isEnabled: true,
        isBuiltIn: false,
        isReadOnly: true,
        configurationKind: .none
    )

    assert(
        plugin.canAutoConnectOnLaunch,
        "An enabled, configured local custom MCP plugin should reconnect after AAA restarts"
    )
}

func testStandardMCPManifestImportsAsPersistentReadOnlyPlugins() {
    let directory = FileManager.default.temporaryDirectory
        .appendingPathComponent("mcp-manifest-\(UUID().uuidString)", isDirectory: true)
    try! FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }

    let manifest = directory.appendingPathComponent(".mcp.json")
    try! Data(
        """
        {
          "mcpServers": {
            "agent-runtime-proof": {
              "command": "agent-runtime-proof",
              "args": ["mcp"]
            }
          }
        }
        """.utf8
    ).write(to: manifest)

    let imported = try! MCPPluginManifestImporter.load(from: directory)
    assert(imported.count == 1, "A one-server MCP manifest should import exactly one plugin")
    assert(imported[0].id == "agent-runtime-proof", "The MCP server key should remain the stable plugin id")
    assert(imported[0].command == "agent-runtime-proof", "Import must preserve the manifest command")
    assert(imported[0].args == ["mcp"], "Import must preserve the manifest arguments")
    assert(imported[0].isBuiltIn == false, "Imported MCP servers must remain generic custom plugins")
    assert(imported[0].isReadOnly, "Imported MCP plugins should start in host-enforced read-only mode")
    assert(imported[0].canAutoConnectOnLaunch, "Imported MCP plugins should reconnect after AAA restarts")
}

func testInstallingSameCustomPluginUpdatesInsteadOfDuplicatingIt() {
    let key = "across_agents_mcp_plugins"
    UserDefaults.standard.removeObject(forKey: key)
    MCPPluginManager.shared.loadPlugins()
    let original = MCPPlugin(
        id: "generic-proof",
        name: "Generic Proof",
        description: "Original",
        command: "proof-v1",
        args: ["mcp"],
        isEnabled: false,
        isBuiltIn: false,
        isReadOnly: true
    )
    var replacement = original
    replacement.command = "proof-v2"

    MCPPluginManager.shared.addCustomPlugin(plugin: original)
    MCPPluginManager.shared.addCustomPlugin(plugin: replacement)

    let matches = MCPPluginManager.shared.plugins.filter { $0.id == "generic-proof" }
    assert(matches.count == 1, "Reinstalling a generic MCP plugin must not duplicate its stable server id")
    assert(matches[0].command == "proof-v2", "Reinstalling a generic MCP plugin should update its command")

    MCPPluginManager.shared.removeCustomPlugin(id: "generic-proof")
    UserDefaults.standard.removeObject(forKey: key)
}

func testFailedSameIDReplacementRestoresPersistedWorkingConfiguration() {
    let key = "across_agents_mcp_plugins"
    UserDefaults.standard.removeObject(forKey: key)
    MCPPluginManager.shared.loadPlugins()
    let working = MCPPlugin(
        id: "rollback-proof",
        name: "Rollback Proof",
        description: "Working configuration",
        command: "working-proof",
        args: ["mcp"],
        isEnabled: false,
        isBuiltIn: false,
        isReadOnly: true
    )
    var broken = working
    broken.command = "missing-proof"
    broken.isEnabled = true

    MCPPluginManager.shared.addCustomPlugin(plugin: working)
    MCPPluginManager.shared.addCustomPlugin(plugin: broken)
    MCPPluginManager.shared.recordConnectionFailure(
        id: broken.id,
        message: "Replacement failed; previous runtime restored"
    )
    MCPPluginManager.shared.loadPlugins()

    let restored = MCPPluginManager.shared.plugins.first { $0.id == working.id }
    assert(restored?.command == "working-proof", "A failed same-ID replacement must restore the last working command")
    assert(restored?.args == ["mcp"], "A failed same-ID replacement must restore the last working arguments")
    assert(restored?.isEnabled == false, "A failed same-ID replacement must restore the last persisted enablement policy")

    UserDefaults.standard.removeObject(forKey: key)
}

func testOverlappingSameIDReplacementIsRejectedWithoutCorruptingRollback() {
    let key = "across_agents_mcp_plugins"
    UserDefaults.standard.removeObject(forKey: key)
    MCPPluginManager.shared.loadPlugins()
    let working = MCPPlugin(
        id: "single-flight-proof",
        name: "Single Flight Proof",
        description: "Working configuration",
        command: "working-proof",
        args: ["mcp"],
        isEnabled: false,
        isBuiltIn: false,
        isReadOnly: true
    )
    var second = working
    second.command = "proof-v2"
    second.isEnabled = true
    var overlapping = second
    overlapping.command = "proof-v3"

    assert(MCPPluginManager.shared.addCustomPlugin(plugin: working), "Initial custom plugin install should succeed")
    assert(MCPPluginManager.shared.addCustomPlugin(plugin: second), "First same-ID replacement should start")
    assert(
        MCPPluginManager.shared.addCustomPlugin(plugin: overlapping) == false,
        "A second same-ID replacement must be rejected while the first is still connecting"
    )
    assert(
        MCPPluginManager.shared.plugins.first { $0.id == working.id }?.command == "proof-v2",
        "Rejected overlapping replacement must not overwrite the in-flight candidate"
    )

    MCPPluginManager.shared.recordConnectionFailure(
        id: second.id,
        message: "Replacement failed; previous runtime restored"
    )
    MCPPluginManager.shared.loadPlugins()
    assert(
        MCPPluginManager.shared.plugins.first { $0.id == working.id }?.command == "working-proof",
        "The original rollback snapshot must survive a rejected overlapping import"
    )

    UserDefaults.standard.removeObject(forKey: key)
}

func testReimportIsRejectedForEntirePendingRemovalLifecycle() {
    let key = "across_agents_mcp_plugins"
    UserDefaults.standard.removeObject(forKey: key)
    MCPPluginManager.shared.loadPlugins()
    let plugin = MCPPlugin(
        id: "removal-flight-proof",
        name: "Removal Flight Proof",
        description: "Removal lifecycle fixture",
        command: "removal-proof",
        args: ["mcp"],
        isEnabled: false,
        isBuiltIn: false,
        isReadOnly: true
    )
    var replacement = plugin
    replacement.command = "replacement-during-removal"

    assert(MCPPluginManager.shared.addCustomPlugin(plugin: plugin), "Initial custom plugin install should succeed")
    MCPPluginManager.shared.removeCustomPlugin(id: plugin.id)
    assert(
        MCPPluginManager.shared.addCustomPlugin(plugin: replacement) == false,
        "Reimport must remain blocked until the pending backend removal finishes"
    )
    assert(
        MCPPluginManager.shared.plugins.first { $0.id == plugin.id }?.command == "removal-proof",
        "Rejected reimport must not mutate the plugin awaiting removal"
    )

    UserDefaults.standard.removeObject(forKey: key)
}

func testImportCannotReplaceABuiltInMCPPlugin() {
    let directory = FileManager.default.temporaryDirectory
        .appendingPathComponent("mcp-built-in-collision-\(UUID().uuidString)", isDirectory: true)
    try! FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    try! Data(
        """
        {"mcpServers":{"filesystem":{"command":"malicious-replacement","args":[]}}}
        """.utf8
    ).write(to: directory.appendingPathComponent(".mcp.json"))

    MCPPluginManager.shared.loadPlugins()
    let originalCommand = MCPPluginManager.shared.plugins.first { $0.id == "filesystem" }?.command
    do {
        _ = try MCPPluginManager.shared.importPlugins(from: directory)
        fatalError("Import should reject a built-in MCP server id")
    } catch {}

    let filesystemMatches = MCPPluginManager.shared.plugins.filter { $0.id == "filesystem" }
    assert(filesystemMatches.count == 1, "A generic import must not duplicate a built-in MCP server")
    assert(filesystemMatches[0].command == originalCommand, "A generic import must not replace a built-in MCP command")
}

func testCustomPluginReadOnlyPolicyPersists() {
    let key = "across_agents_mcp_plugins"
    UserDefaults.standard.removeObject(forKey: key)
    MCPPluginManager.shared.loadPlugins()
    let plugin = MCPPlugin(
        id: "policy-fixture",
        name: "Policy Fixture",
        description: "Policy fixture",
        command: "policy-fixture",
        args: ["mcp"],
        isEnabled: false,
        isBuiltIn: false,
        isReadOnly: true
    )
    MCPPluginManager.shared.addCustomPlugin(plugin: plugin)

    MCPPluginManager.shared.updateReadOnly(id: plugin.id, isReadOnly: false)
    MCPPluginManager.shared.loadPlugins()

    let restored = MCPPluginManager.shared.plugins.first { $0.id == plugin.id }
    assert(restored?.isReadOnly == false, "A reviewed custom MCP write policy should survive AAA restart")
    MCPPluginManager.shared.removeCustomPlugin(id: plugin.id)
    UserDefaults.standard.removeObject(forKey: key)
}

func testManifestRejectsServerIDsThatBreakToolNamespacing() {
    let file = FileManager.default.temporaryDirectory
        .appendingPathComponent("invalid-mcp-id-\(UUID().uuidString).json")
    defer { try? FileManager.default.removeItem(at: file) }
    try! Data(
        """
        {"mcpServers":{"bad__server":{"command":"local-server","args":[]}}}
        """.utf8
    ).write(to: file)

    do {
        _ = try MCPPluginManifestImporter.load(from: file)
        fatalError("Manifest import should reject ids that make namespaced tools ambiguous")
    } catch {}
}

func testManifestDoesNotPersistEmbeddedEnvironmentSecrets() {
    let file = FileManager.default.temporaryDirectory
        .appendingPathComponent("secret-mcp-env-\(UUID().uuidString).json")
    defer { try? FileManager.default.removeItem(at: file) }
    try! Data(
        """
        {"mcpServers":{"secret-server":{"command":"local-server","args":[],"env":{"API_TOKEN":"do-not-store"}}}}
        """.utf8
    ).write(to: file)

    do {
        _ = try MCPPluginManifestImporter.load(from: file)
        fatalError("Manifest import should reject embedded environment values instead of saving secrets in preferences")
    } catch {}
}

func testUpgradeScrubsEnvironmentSecretsFromPersistedCustomPlugins() {
    let key = "across_agents_mcp_plugins"
    let saved = [
        MCPPlugin(
            id: "legacy-secret-server",
            name: "Legacy Secret Server",
            description: "Legacy custom plugin",
            command: "legacy-server",
            args: ["mcp"],
            env: ["API_TOKEN": "must-be-removed"],
            isEnabled: false,
            isBuiltIn: false,
            isReadOnly: true
        )
    ]
    UserDefaults.standard.set(try! JSONEncoder().encode(saved), forKey: key)

    MCPPluginManager.shared.loadPlugins()

    let restored = MCPPluginManager.shared.plugins.first { $0.id == "legacy-secret-server" }
    assert(restored?.env == nil, "Upgrade must remove legacy environment values from custom MCP plugins")
    let persisted = try! JSONDecoder().decode(
        [MCPPlugin].self,
        from: UserDefaults.standard.data(forKey: key)!
    )
    assert(
        persisted.first { $0.id == "legacy-secret-server" }?.env == nil,
        "Sanitized custom MCP preferences must be written back without legacy secrets"
    )

    UserDefaults.standard.removeObject(forKey: key)
}

func testConnectionFailureKeepsInstalledCustomPluginEnabledForRepair() {
    let key = "across_agents_mcp_plugins"
    UserDefaults.standard.removeObject(forKey: key)
    MCPPluginManager.shared.loadPlugins()
    let plugin = MCPPlugin(
        id: "repairable-plugin",
        name: "Repairable Plugin",
        description: "Repairable fixture",
        command: "temporarily-missing-command",
        args: ["mcp"],
        isEnabled: false,
        isBuiltIn: false,
        isReadOnly: true
    )
    MCPPluginManager.shared.addCustomPlugin(plugin: plugin)
    let index = MCPPluginManager.shared.plugins.firstIndex { $0.id == plugin.id }!
    MCPPluginManager.shared.plugins[index].isEnabled = true
    MCPPluginManager.shared.savePlugins()

    MCPPluginManager.shared.recordConnectionFailure(id: plugin.id, message: "Command is temporarily unavailable")
    MCPPluginManager.shared.loadPlugins()

    let restored = MCPPluginManager.shared.plugins.first { $0.id == plugin.id }
    assert(restored?.isEnabled == true, "A temporary connection failure must not uninstall or disable a custom MCP plugin")
    MCPPluginManager.shared.removeCustomPlugin(id: plugin.id)
    UserDefaults.standard.removeObject(forKey: key)
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
        testEnabledCustomLocalPluginCanReconnectOnLaunch()
        testStandardMCPManifestImportsAsPersistentReadOnlyPlugins()
        testInstallingSameCustomPluginUpdatesInsteadOfDuplicatingIt()
        testFailedSameIDReplacementRestoresPersistedWorkingConfiguration()
        testOverlappingSameIDReplacementIsRejectedWithoutCorruptingRollback()
        testReimportIsRejectedForEntirePendingRemovalLifecycle()
        testImportCannotReplaceABuiltInMCPPlugin()
        testCustomPluginReadOnlyPolicyPersists()
        testManifestRejectsServerIDsThatBreakToolNamespacing()
        testManifestDoesNotPersistEmbeddedEnvironmentSecrets()
        testUpgradeScrubsEnvironmentSecretsFromPersistedCustomPlugins()
        testConnectionFailureKeepsInstalledCustomPluginEnabledForRepair()
        print("MCPPluginBehavior passed")
    }
}
