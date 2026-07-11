import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct RepositoryAccessTests {
    @MainActor
    @Test func missingBookmarkStartsUnselected() throws {
        let suite = "RepositoryAccessTests.missing.\(UUID().uuidString)"
        let defaults = try #require(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let store = SecurityScopedRepositoryStore(defaults: defaults, bookmarkKey: "bookmark")

        store.restore()

        #expect(store.state == .unselected)
        #expect(store.selectedPath == nil)
        #expect(!store.isAccessing)
    }

    @MainActor
    @Test func invalidBookmarkRequiresExplicitReselection() throws {
        let suite = "RepositoryAccessTests.invalid.\(UUID().uuidString)"
        let defaults = try #require(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        defaults.set(Data("invalid-bookmark".utf8), forKey: "bookmark")
        let store = SecurityScopedRepositoryStore(defaults: defaults, bookmarkKey: "bookmark")

        store.restore()

        #expect(store.state.requiresReselection)
        #expect(store.selectedPath == nil)
        #expect(!store.beginAccess())
    }

    @MainActor
    @Test func activeSecurityScopeProducesMetadataWithoutBookmarkBytes() throws {
        let access = AgentWorkspaceRepoAccess(
            mode: "security_scoped",
            securityScopeActive: true,
            grantId: "grant-1"
        )
        let encoded = try JSONEncoder().encode(access)
        let body = try #require(JSONSerialization.jsonObject(with: encoded) as? [String: Any])

        #expect(body["mode"] as? String == "security_scoped")
        #expect(body["security_scope_active"] as? Bool == true)
        #expect(body["grant_id"] as? String == "grant-1")
        #expect(body["bookmark"] == nil)
        #expect(body["bookmark_data"] == nil)
    }

    @Test func repositoryValidationAcceptsDirectoriesAndRejectsFiles() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let file = root.appendingPathComponent("file.txt")
        try Data().write(to: file)

        #expect(SecurityScopedRepositoryStore.isDirectory(root))
        #expect(!SecurityScopedRepositoryStore.isDirectory(file))
    }
}
