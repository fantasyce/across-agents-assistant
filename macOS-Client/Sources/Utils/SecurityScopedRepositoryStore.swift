import AppKit
import Combine
import Foundation

enum RepositoryBookmarkState: Equatable {
    case unselected
    case ready(path: String)
    case stale(path: String?)
    case failed(message: String)

    var requiresReselection: Bool {
        if case .stale = self { return true }
        if case .failed = self { return true }
        return false
    }
}

@MainActor
final class SecurityScopedRepositoryStore: ObservableObject {
    static let shared = SecurityScopedRepositoryStore()

    @Published private(set) var selectedURL: URL?
    @Published private(set) var state: RepositoryBookmarkState = .unselected
    @Published private(set) var isAccessing = false
    @Published private(set) var grantId: String?

    private let defaults: UserDefaults
    private let bookmarkKey: String
    private var accessOwners: Set<String> = []

    init(
        defaults: UserDefaults = AppUserDefaults.current,
        bookmarkKey: String = "operations.securityScopedRepositoryBookmark"
    ) {
        self.defaults = defaults
        self.bookmarkKey = bookmarkKey
    }

    var selectedPath: String? { selectedURL?.path }
    var workspaceAccess: AgentWorkspaceRepoAccess? {
        guard isAccessing else { return nil }
        return AgentWorkspaceRepoAccess(mode: "security_scoped", securityScopeActive: true, grantId: grantId)
    }

    func restore() {
        if selectedURL != nil { return }
        guard let data = defaults.data(forKey: bookmarkKey) else {
            selectedURL = nil
            grantId = nil
            state = .unselected
            return
        }

        var isStale = false
        do {
            let url = try URL(
                resolvingBookmarkData: data,
                options: [.withSecurityScope, .withoutUI],
                relativeTo: nil,
                bookmarkDataIsStale: &isStale
            ).standardizedFileURL
            guard !isStale else {
                selectedURL = nil
                state = .stale(path: url.path)
                return
            }
            guard Self.isDirectory(url) else {
                selectedURL = nil
                state = .failed(message: "The saved repository is no longer available. Select it again.")
                return
            }
            selectedURL = url
            grantId = defaults.string(forKey: grantKey)
            if grantId == nil {
                grantId = UUID().uuidString
                defaults.set(grantId, forKey: grantKey)
            }
            state = .ready(path: url.path)
        } catch {
            selectedURL = nil
            state = .failed(message: "The saved repository permission could not be restored. Select it again.")
        }
    }

    @discardableResult
    func chooseRepository(
        title: String = "Select Repository",
        message: String = "Choose the repository folder Across may inspect and modify in an isolated workspace.",
        prompt: String = "Choose Repository"
    ) -> URL? {
        let panel = NSOpenPanel()
        panel.title = title
        panel.message = message
        panel.prompt = prompt
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.canCreateDirectories = false
        panel.resolvesAliases = true
        if let selectedURL { panel.directoryURL = selectedURL }

        guard panel.runModal() == .OK, let url = panel.url?.standardizedFileURL else { return nil }
        do {
            try persist(url)
            return url
        } catch {
            selectedURL = nil
            state = .failed(message: "Across could not save permission for this repository. Select another folder.")
            return nil
        }
    }

    @discardableResult
    func beginAccess(owner: String = "default") -> Bool {
        guard let selectedURL else {
            state = .failed(message: "Select a repository before continuing.")
            return false
        }
        if !isAccessing {
            guard selectedURL.startAccessingSecurityScopedResource() else {
                state = .failed(message: "Repository access was denied or expired. Select the folder again.")
                return false
            }
            isAccessing = true
        }
        accessOwners.insert(owner)
        state = .ready(path: selectedURL.path)
        return true
    }

    func endAccess(owner: String = "default") {
        accessOwners.remove(owner)
        guard accessOwners.isEmpty, isAccessing, let selectedURL else { return }
        selectedURL.stopAccessingSecurityScopedResource()
        isAccessing = false
    }

    func clear() {
        stopAllAccess()
        defaults.removeObject(forKey: bookmarkKey)
        defaults.removeObject(forKey: grantKey)
        selectedURL = nil
        grantId = nil
        state = .unselected
    }

    private func persist(_ url: URL) throws {
        guard Self.isDirectory(url) else {
            throw CocoaError(.fileReadNoSuchFile)
        }
        let owners = accessOwners
        stopAllAccess()
        let data = try url.bookmarkData(
            options: [.withSecurityScope],
            includingResourceValuesForKeys: [.isDirectoryKey],
            relativeTo: nil
        )
        defaults.set(data, forKey: bookmarkKey)
        grantId = UUID().uuidString
        defaults.set(grantId, forKey: grantKey)
        selectedURL = url
        state = .ready(path: url.path)
        for owner in owners {
            _ = beginAccess(owner: owner)
        }
    }

    nonisolated static func isDirectory(_ url: URL) -> Bool {
        (try? url.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true
    }

    private var grantKey: String { "\(bookmarkKey).grantID" }

    private func stopAllAccess() {
        if isAccessing, let selectedURL {
            selectedURL.stopAccessingSecurityScopedResource()
        }
        isAccessing = false
        accessOwners.removeAll()
    }
}
