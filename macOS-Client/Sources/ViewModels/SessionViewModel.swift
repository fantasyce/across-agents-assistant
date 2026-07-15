import Foundation
import Combine
import AVFoundation
import AppKit

private let legacyAttachmentMarker = "\u{3010}\u{9644}\u{5E26}\u{7684}\u{6587}\u{4EF6}/\u{76EE}\u{5F55}\u{3011}:\n"

struct AttachedFile: Identifiable, Codable, Equatable {
    var id = UUID()
    let name: String
    let path: String
    let isFolder: Bool
    var kind: String = "file"
    var mimeType: String? = nil

    init(
        id: UUID = UUID(),
        name: String,
        path: String,
        isFolder: Bool,
        kind: String = "file",
        mimeType: String? = nil
    ) {
        self.id = id
        self.name = name
        self.path = path
        self.isFolder = isFolder
        self.kind = kind
        self.mimeType = mimeType
    }

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case path
        case isFolder
        case kind
        case mimeType
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
        name = try container.decode(String.self, forKey: .name)
        path = try container.decode(String.self, forKey: .path)
        isFolder = try container.decode(Bool.self, forKey: .isFolder)
        kind = try container.decodeIfPresent(String.self, forKey: .kind) ?? "file"
        mimeType = try container.decodeIfPresent(String.self, forKey: .mimeType)
    }

    var isImageAttachment: Bool {
        AttachmentImageSupport.isDisplayableImage(mimeType: mimeType, fileName: name)
    }
}

struct Message: Identifiable {
    let id = UUID()
    let content: String
    let isUser: Bool
    let timestamp: Date = Date()
    var attachedFiles: [AttachedFile] = []
}

struct SpeechPlaybackSettings {
    var autoReadReplies: Bool = true
    var voiceSource: AppVoiceSource = .followSystem
    var chosenVoiceIdentifier: String? = nil
    var fallbackLanguage: String = Locale.preferredLanguages.first ?? "zh-CN"
    var speechRate: Double = 0.48
    var speechVolume: Double = 1.0

    static let `default` = SpeechPlaybackSettings()
}

struct ChatAttachment: Codable {
    let name: String
    let path: String
    let isFolder: Bool
    let kind: String
    let mimeType: String?

    init(file: AttachedFile) {
        name = file.name
        path = file.path
        isFolder = file.isFolder
        kind = file.kind
        mimeType = file.mimeType
    }

    enum CodingKeys: String, CodingKey {
        case name
        case path
        case isFolder = "is_folder"
        case kind
        case mimeType = "mime_type"
    }
}

struct ChatRequest: Codable {
    var text: String
    var context: ContextPack?
    var session_id: String?
    var agent_id: String?
    var project_id: String?
    var project_dir: String?
    var attachments: [ChatAttachment]?
}

struct ChatResponse: Codable {
    var text: String
    var session_id: String?
    var audio_path: String?
    var requires_approval: Bool?
    var approval_request: ApprovalRequest?
}

struct SessionInfo: Identifiable, Codable {
    var id: String { session_id }
    let session_id: String
    let created_at: String
    let updated_at: String
    let message_count: Int
    let name: String?
    let preview: String?
    let project_id: String?
    let project_dir: String?
    let is_pinned: Bool
    let pinned_at: String?
}

struct SessionListResponse: Codable {
    let sessions: [SessionInfo]
    let total: Int?
    let limit: Int?
    let offset: Int?
    let has_more: Bool?
}

struct ProjectInfo: Identifiable, Codable, Equatable {
    let id: String
    let name: String
    let path: String
    let kind: String
    let is_pinned: Bool
    let pinned_at: String?
    let created_at: String
    let updated_at: String
    let last_opened_at: String?
    let sessions: [SessionInfo]

    static func == (lhs: ProjectInfo, rhs: ProjectInfo) -> Bool {
        lhs.id == rhs.id
            && lhs.name == rhs.name
            && lhs.path == rhs.path
            && lhs.is_pinned == rhs.is_pinned
            && lhs.sessions.map { "\($0.session_id):\($0.is_pinned)" } == rhs.sessions.map { "\($0.session_id):\($0.is_pinned)" }
    }
}

struct ProjectListResponse: Codable {
    let projects: [ProjectInfo]
}

struct CreateBlankProjectRequest: Codable {
    let name: String
}

struct CreateFolderProjectRequest: Codable {
    let path: String
    let name: String?
}

struct ChatMessage: Codable {
    let id: Int?
    let role: String
    let content: String?
    let tool_call_id: String?
    let tool_calls: String?
    let created_at: String?
}

struct ChatHistoryResponse: Codable {
    let session_id: String
    let messages: [ChatMessage]
    let total: Int?
    let has_more: Bool?
}

struct ApprovalDecisionRequest: Codable {
    let session_id: String
    let decision: String
    let tool_name: String
    let tool_args: [String: AnyCodableValue]?
    let agent_id: String
    let tool_call_id: String?
}

enum AgentType: String {
    case local
    case cloudLLM
}

struct AgentModel: Identifiable {
    let id: String
    let name: String
    let iconName: String
    let color: String
    let type: AgentType
}

struct FileItemModel: Identifiable, Equatable {
    var id: String { path }
    let name: String
    let path: String
    let isFolder: Bool
    var children: [FileItemModel]?
    var isExpanded: Bool = false
}

class SessionViewModel: ObservableObject {
    static let longRunningAgentRequestTimeout: TimeInterval = 900

    @Published var messages: [Message] = []
    @Published var isProcessing: Bool = false
    private var currentChatTask: URLSessionDataTask?
    @Published var pendingApproval: ApprovalRequest? = nil
    @Published var showPermissionAlert: Bool = false
    @Published var showMCPPreferences: Bool = false
    @Published var inputText: String = "" // Add inputText to ViewModel so we can modify it from here
    @Published var attachedFiles: [AttachedFile] = [] // Track files dropped into the input box
    @Published var showHiddenFiles: Bool = false
    @Published var activeMCPContexts: [MCPContextInfo] = []
    @Published var projects: [ProjectInfo] = []
    @Published var projectsLoading: Bool = false
    @Published var activeProjectId: String? = nil
    @Published var activeProjectPath: String? = nil
    @Published var activeProjectName: String? = nil
    @Published var sessions: [SessionInfo] = []
    @Published var sessionsLoading: Bool = false
    @Published var sessionsHasMore: Bool = false
    @Published var sessionsTotal: Int = 0
    private let sessionPageSize: Int = 50

    struct MCPContextInfo: Identifiable, Codable {
        let id: String
        let name: String
        let status: String
        let dbPath: String?
    }

    // Input history state
    private struct HistoryItem: Equatable {
        let text: String
        let files: [AttachedFile]
    }
    private var inputHistory: [HistoryItem] = []
    private var historyIndex: Int = -1
    var speechPlaybackSettings: SpeechPlaybackSettings = .default
    var includeActiveAppContext: Bool = true
    var shouldRememberSelectedAgent: Bool = true
    var screenshotOCRPermissionTip: String = "[Tip: The first screenshot requires Screen Recording permission. Allow it in the system prompt, or enable it in System Settings -> Privacy & Security -> Screen Recording. Restart the app after granting permission.]"
    var screenshotAttachmentPermissionTip: String = "[Tip: Screenshot attachment requires Screen Recording permission. Allow it in System Settings -> Privacy & Security -> Screen Recording, then try again.]"
    var screenshotClipboardPermissionTip: String = "[Tip: Copy screenshot requires Screen Recording permission. Allow it in System Settings -> Privacy & Security -> Screen Recording, then try again.]"
    var screenshotCopiedNotice: String = "Screenshot copied to clipboard."
    var screenshotCancelledNotice: String = "Screenshot cancelled."
    var screenshotCopyFailedNotice: String = "Could not copy screenshot to clipboard."
    @Published var transientInputNotice: String? = nil
    private var transientInputNoticeToken = UUID()
    @Published var isMuted: Bool = false {
        didSet {
            if isMuted {
                TTSEngine.shared.stop()
            }
        }
    }

    @Published var selectedAgentId: String = AgentIDs.normalized(AppUserDefaults.current.string(forKey: "lastSelectedAgentId")) ?? "deepseek" {
        didSet {
            let normalizedSelectedAgentId = AgentIDs.normalized(selectedAgentId) ?? selectedAgentId
            if shouldRememberSelectedAgent {
                AppUserDefaults.current.set(normalizedSelectedAgentId, forKey: "lastSelectedAgentId")
            } else {
                AppUserDefaults.current.removeObject(forKey: "lastSelectedAgentId")
            }
            // Tell backend about the active agent
            guard let url = URL(string: "http://backend/api/active_agent") else { return }
            var request = URLRequest(url: url)
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            let payload: [String: String] = ["agent_id": normalizedSelectedAgentId]
            if let body = try? JSONEncoder().encode(payload) {
                request.httpBody = body
                URLSession.shared.dataTask(with: request).resume()
            }
        }
    }

    let agents: [AgentModel] = [
        // Local Agents
        AgentModel(id: AgentIDs.openclaw, name: "OpenClaw", iconName: "agent.openclaw", color: "#d97757", type: .local),
        AgentModel(id: "hermes", name: "Hermes", iconName: "agent.hermes", color: "#d97757", type: .local),
        AgentModel(id: "claude", name: "Claude Code", iconName: "agent.claude", color: "#d97757", type: .local),
        AgentModel(id: AgentIDs.claudeDesktop, name: "Claude Desktop", iconName: "agent.claude-desktop", color: "#d97757", type: .local),
        AgentModel(id: "codex", name: "Codex", iconName: "agent.codex", color: "#d97757", type: .local),
        AgentModel(id: AgentIDs.kimi, name: "Kimi Code", iconName: "agent.kimi", color: "#d97757", type: .local),
        AgentModel(id: "opencode", name: "OpenCode", iconName: "agent.opencode", color: "#d97757", type: .local),
        AgentModel(id: "cursor", name: "Cursor Agent", iconName: "agent.cursor", color: "#d97757", type: .local),
        // Cloud LLMs
        AgentModel(id: "openai", name: "OpenAI", iconName: "agent.openai", color: "#4d6bfe", type: .cloudLLM),
        AgentModel(id: "anthropic", name: "Anthropic", iconName: "agent.anthropic", color: "#4d6bfe", type: .cloudLLM),
        AgentModel(id: "deepseek", name: "DeepSeek", iconName: "agent.deepseek", color: "#4d6bfe", type: .cloudLLM),
        AgentModel(id: "minimax", name: "MiniMax", iconName: "agent.minimax", color: "#4d6bfe", type: .cloudLLM),
        AgentModel(id: "agnes", name: "Agnes", iconName: "agent.agnes", color: "#4d6bfe", type: .cloudLLM),
        AgentModel(id: "bailian", name: "Alibaba Bailian / Qwen", iconName: "agent.bailian", color: "#4d6bfe", type: .cloudLLM),
        AgentModel(id: "moonshot", name: "Moonshot / Kimi", iconName: "agent.moonshot", color: "#4d6bfe", type: .cloudLLM),
        AgentModel(id: "zhipu", name: "Zhipu GLM", iconName: "agent.zhipu", color: "#4d6bfe", type: .cloudLLM),
        AgentModel(id: "volcengine", name: "Volcengine Ark / Doubao", iconName: "agent.volcengine", color: "#4d6bfe", type: .cloudLLM),
        AgentModel(id: "google", name: "Google Gemini", iconName: "agent.google", color: "#4d6bfe", type: .cloudLLM),
        AgentModel(id: "xai", name: "xAI", iconName: "agent.xai", color: "#4d6bfe", type: .cloudLLM),
        AgentModel(id: "mistral", name: "Mistral AI", iconName: "agent.mistral", color: "#4d6bfe", type: .cloudLLM),
        AgentModel(id: "groq", name: "Groq", iconName: "agent.groq", color: "#4d6bfe", type: .cloudLLM),
        AgentModel(id: "cohere", name: "Cohere", iconName: "agent.cohere", color: "#4d6bfe", type: .cloudLLM),
        AgentModel(id: "openrouter", name: "OpenRouter", iconName: "agent.openrouter", color: "#4d6bfe", type: .cloudLLM),
        AgentModel(id: "together", name: "Together AI", iconName: "agent.together", color: "#4d6bfe", type: .cloudLLM),
        AgentModel(id: "fireworks", name: "Fireworks AI", iconName: "agent.fireworks", color: "#4d6bfe", type: .cloudLLM)
    ]

    @Published var fileTree: [FileItemModel] = [] {
        didSet {
            flatFileTree = flatten(nodes: fileTree, depth: 0)
        }
    }
    @Published var flatFileTree: [(node: FileItemModel, depth: Int)] = []
    @Published var selectedFileId: String? = nil
    @Published var currentFileTreeRootName: String? = nil
    @Published var currentFileTreeRootPath: String? = nil

    private func flatten(nodes: [FileItemModel], depth: Int) -> [(node: FileItemModel, depth: Int)] {
        var flat: [(node: FileItemModel, depth: Int)] = []
        for node in nodes {
            flat.append((node, depth))
            if node.isFolder && node.isExpanded, let children = node.children {
                flat.append(contentsOf: flatten(nodes: children, depth: depth + 1))
            }
        }
        return flat
    }

    @Published var currentSessionId: String = "default-session"
    private var isFirstSessionFetch = false
    private var isFirstProjectFetch = true
    private var didStartInitialDataLoad = false
    private var hasLoadedHistory = false
    private let historyPageSize = 30
    private var historyOffset = 0
    @Published var hasMoreHistory: Bool = false
    @Published var isLoadingMoreHistory: Bool = false

    private func showApp() {
        NSApp.unhide(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    func requestManualScreenshot() {
        // 1. First check if we have screen recording permission
        if !ContextEngine.shared.hasScreenRecordingPermission() {
            NSApp.hide(nil)

            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
                ContextEngine.shared.triggerScreenRecordingPrompt()

                DispatchQueue.main.async {
                    self.showApp()
                    if !self.inputText.isEmpty {
                        self.inputText += "\n"
                    }
                    self.inputText += self.screenshotOCRPermissionTip
                }
            }
            return
        }

        // 2. We already have permission, hide and capture
        NSApp.hide(nil)

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
            self.executeScreenshot()
        }
    }

    func requestScreenshotAttachment() {
        if !ContextEngine.shared.hasScreenRecordingPermission() {
            NSApp.hide(nil)

            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
                ContextEngine.shared.triggerScreenRecordingPrompt()

                DispatchQueue.main.async {
                    self.showApp()
                    if !self.inputText.isEmpty {
                        self.inputText += "\n"
                    }
                    self.inputText += self.screenshotAttachmentPermissionTip
                }
            }
            return
        }

        NSApp.hide(nil)

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
            ContextEngine.shared.captureScreenshotImage { [weak self] fileURL in
                guard let self else { return }
                self.showApp()

                guard let fileURL else { return }
                self.attachedFiles.append(AttachedFile(
                    name: fileURL.lastPathComponent,
                    path: fileURL.path,
                    isFolder: false,
                    kind: "screenshot",
                    mimeType: "image/png"
                ))
            }
        }
    }

    func requestFileAttachment() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = true
        panel.treatsFilePackagesAsDirectories = false
        panel.title = "Attach Files or Folders"
        panel.prompt = "Attach"

        guard panel.runModal() == .OK else { return }
        attachFiles(from: panel.urls)
    }

    func attachFiles(from urls: [URL]) {
        let files = urls.map { url in
            let standardizedUrl = url.standardizedFileURL
            let isDir = (try? standardizedUrl.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) ?? false
            let name = standardizedUrl.lastPathComponent
            let isImage = AttachmentImageSupport.isDisplayableImage(mimeType: nil, fileName: name)
            return AttachedFile(
                name: name,
                path: standardizedUrl.path,
                isFolder: isDir,
                kind: isDir ? "folder" : (isImage ? "image" : "file"),
                mimeType: nil
            )
        }

        attachedFiles.append(contentsOf: files)
    }

    func requestScreenshotToClipboard() {
        let result = ScreenshotClipboardService.shared.copyInteractiveWindowSelectionToClipboard()
        switch result {
        case .permissionRequired:
            showTransientInputNotice(screenshotClipboardPermissionTip)
        case .launchFailed:
            showTransientInputNotice(screenshotCopyFailedNotice)
        case .alreadyRunning, .started:
            break
        }
    }

    private func showTransientInputNotice(_ text: String) {
        let token = UUID()
        transientInputNoticeToken = token
        transientInputNotice = text

        DispatchQueue.main.asyncAfter(deadline: .now() + 2.6) { [weak self] in
            guard let self, self.transientInputNoticeToken == token else { return }
            self.transientInputNotice = nil
        }
    }

    private func executeScreenshot() {
        ContextEngine.shared.performScreenshotAndOCR { [weak self] extractedText in
            guard let self = self else { return }

            self.showApp()

            if let text = extractedText {
                if !self.inputText.isEmpty {
                    self.inputText += "\n"
                }
                self.inputText += "[Screenshot Text]:\n" + text + "\n"
            }
        }
    }

    func startNewSession() {
        guard let project = activeProject ?? projects.first else {
            fetchProjects()
            return
        }
        startNewSession(in: project)
    }

    func startNewSession(in project: ProjectInfo) {
        let newSessionId = UUID().uuidString
        activeProjectId = project.id
        activeProjectName = project.name
        activeProjectPath = project.path
        currentSessionId = newSessionId
        messages.removeAll()
        inputText = ""
        attachedFiles = []
        hasLoadedHistory = false
        historyOffset = 0
        hasMoreHistory = false
        isLoadingMoreHistory = false

        let systemWelcome = Message(
            content: "New chat in \(project.name).",
            isUser: false
        )
        messages.append(systemWelcome)
    }

    var activeProject: ProjectInfo? {
        guard let activeProjectId else { return nil }
        return projects.first(where: { $0.id == activeProjectId })
    }

    @discardableResult
    func activateProject(matchingDirectory directory: String?) -> Bool {
        guard let directory else { return false }
        let taskPath = normalizedProjectPath(directory)
        guard !taskPath.isEmpty else { return false }

        let project = projects
            .filter { candidate in
                let projectPath = normalizedProjectPath(candidate.path)
                return taskPath == projectPath || taskPath.hasPrefix(projectPath + "/")
            }
            .max { lhs, rhs in
                normalizedProjectPath(lhs.path).count < normalizedProjectPath(rhs.path).count
            }

        guard let project else { return false }
        activeProjectId = project.id
        activeProjectName = project.name
        activeProjectPath = project.path
        return true
    }

    private func normalizedProjectPath(_ path: String) -> String {
        URL(fileURLWithPath: path)
            .standardizedFileURL
            .resolvingSymlinksInPath()
            .path
    }

    func switchToSession(_ session: SessionInfo, in project: ProjectInfo? = nil) {
        if let project {
            activeProjectId = project.id
            activeProjectName = project.name
            activeProjectPath = project.path
        } else if let projectId = session.project_id,
                  let matched = projects.first(where: { $0.id == projectId }) {
            activeProjectId = matched.id
            activeProjectName = matched.name
            activeProjectPath = matched.path
        } else if let projectDir = session.project_dir {
            activeProjectPath = projectDir
        }
        switchToSession(session.session_id)
    }

    func switchToSession(_ sessionId: String) {
        guard sessionId != currentSessionId else { return }
        currentSessionId = sessionId
        messages.removeAll()
        inputText = ""
        attachedFiles = []
        hasLoadedHistory = false
        historyOffset = 0
        hasMoreHistory = false
        isLoadingMoreHistory = false
        loadChatHistory()
    }

    func deleteSession(_ sessionId: String) {
        guard let encoded = sessionId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed),
              let url = URL(string: "http://backend/api/sessions/\(encoded)") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"

        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            DispatchQueue.main.async {
                guard let self = self else { return }
                if error == nil {
                    self.sessions.removeAll { $0.session_id == sessionId }
                    self.fetchProjects()
                    if self.currentSessionId == sessionId {
                        if let mostRecent = self.sessions.first {
                            self.switchToSession(mostRecent.session_id)
                        } else {
                            self.startNewSession()
                        }
                    }
                }
            }
        }.resume()
    }

    func renameSession(_ sessionId: String, to name: String) {
        guard let encoded = sessionId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed),
              let url = URL(string: "http://backend/api/sessions/\(encoded)/rename") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["name": name])

        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            DispatchQueue.main.async {
                guard let self = self else { return }
                if error == nil, let idx = self.sessions.firstIndex(where: { $0.session_id == sessionId }) {
                    let updated = SessionInfo(
                        session_id: self.sessions[idx].session_id,
                        created_at: self.sessions[idx].created_at,
                        updated_at: self.sessions[idx].updated_at,
                        message_count: self.sessions[idx].message_count,
                        name: name,
                        preview: self.sessions[idx].preview,
                        project_id: self.sessions[idx].project_id,
                        project_dir: self.sessions[idx].project_dir,
                        is_pinned: self.sessions[idx].is_pinned,
                        pinned_at: self.sessions[idx].pinned_at
                    )
                    self.sessions[idx] = updated
                    self.fetchProjects()
                }
            }
        }.resume()
    }

    func setProjectPinned(_ projectId: String, pinned: Bool) {
        guard let encoded = projectId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed),
              let url = URL(string: "http://backend/api/projects/\(encoded)/pin") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["is_pinned": pinned])

        URLSession.shared.dataTask(with: request) { [weak self] _, _, error in
            guard error == nil else { return }
            DispatchQueue.main.async {
                self?.fetchProjects()
            }
        }.resume()
    }

    func setSessionPinned(_ sessionId: String, pinned: Bool) {
        guard let encoded = sessionId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed),
              let url = URL(string: "http://backend/api/sessions/\(encoded)/pin") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["is_pinned": pinned])

        URLSession.shared.dataTask(with: request) { [weak self] _, _, error in
            guard error == nil else { return }
            DispatchQueue.main.async {
                self?.fetchProjects()
                self?.fetchSessions()
            }
        }.resume()
    }

    func deleteSessions(_ sessionIds: Set<String>) {
        let group = DispatchGroup()
        for id in sessionIds {
            guard let encoded = id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed),
                  let url = URL(string: "http://backend/api/sessions/\(encoded)") else { continue }
            var request = URLRequest(url: url)
            request.httpMethod = "DELETE"
            group.enter()
            URLSession.shared.dataTask(with: request) { _, _, _ in
                group.leave()
            }.resume()
        }
        group.notify(queue: .main) { [weak self] in
            guard let self = self else { return }
            self.sessions.removeAll { sessionIds.contains($0.session_id) }
            self.fetchProjects()
            if sessionIds.contains(self.currentSessionId) {
                if let mostRecent = self.sessions.first {
                    self.switchToSession(mostRecent.session_id)
                } else {
                    self.startNewSession()
                }
            }
        }
    }

    init() {
        loadDefaultWorkspaceDirectory()
    }

    func loadInitialDataIfNeeded() {
        guard !didStartInitialDataLoad else { return }
        didStartInitialDataLoad = true
        fetchMCPContexts()
        fetchProjects()
        fetchSessions()
    }

    func fetchMCPContexts() {
        guard let url = URL(string: "http://backend/api/mcp/contexts") else { return }

        URLSession.shared.dataTask(with: url) { [weak self] data, _, _ in
            guard let data = data else { return }
            if let contexts = try? JSONDecoder().decode([MCPContextInfo].self, from: data) {
                DispatchQueue.main.async {
                    self?.activeMCPContexts = contexts
                }
            }
        }.resume()
    }

    func fetchProjects(retries: Int = 10) {
        guard let url = URL(string: "http://backend/api/projects?session_limit=50") else { return }
        if retries == 10 { projectsLoading = true }
        var request = URLRequest(url: url, timeoutInterval: 10)
        request.httpMethod = "GET"
        URLSession.shared.dataTask(with: request) { [weak self] data, _, error in
            guard let self else { return }
            guard let data, error == nil else {
                if retries > 0 {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                        self.fetchProjects(retries: retries - 1)
                    }
                } else {
                    DispatchQueue.main.async {
                        self.projectsLoading = false
                    }
                }
                return
            }
            do {
                let response = try JSONDecoder().decode(ProjectListResponse.self, from: data)
                DispatchQueue.main.async {
                    self.projects = response.projects
                    self.projectsLoading = false
                    self.ensureActiveProject()
                }
            } catch {
                print("[fetchProjects] decode error: \(error)")
                DispatchQueue.main.async {
                    self.projectsLoading = false
                }
            }
        }.resume()
    }

    private func ensureActiveProject() {
        if let activeProjectId,
           let project = projects.first(where: { $0.id == activeProjectId }) {
            activeProjectName = project.name
            activeProjectPath = project.path
            return
        }
        guard let project = projects.first else { return }
        activeProjectId = project.id
        activeProjectName = project.name
        activeProjectPath = project.path
        if isFirstProjectFetch {
            isFirstProjectFetch = false
            if let firstSession = project.sessions.first {
                switchToSession(firstSession, in: project)
            } else {
                startNewSession(in: project)
            }
            loadProjectDirectory(project)
        }
    }

    func createBlankProjectPrompt() {
        let alert = NSAlert()
        alert.messageText = "New Blank Project"
        alert.informativeText = "Create a project directory under ~/.across/data/across-agents-assistant/workspace."
        alert.addButton(withTitle: "Create")
        alert.addButton(withTitle: "Cancel")
        let input = NSTextField(frame: NSRect(x: 0, y: 0, width: 260, height: 24))
        input.placeholderString = "Project name"
        alert.accessoryView = input
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        let name = input.stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return }
        createBlankProject(name: name)
    }

    func createBlankProject(name: String) {
        guard let url = URL(string: "http://backend/api/projects/blank") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONEncoder().encode(CreateBlankProjectRequest(name: name))
        URLSession.shared.dataTask(with: request) { [weak self] data, _, error in
            guard let self, let data, error == nil else { return }
            do {
                let project = try JSONDecoder().decode(ProjectInfo.self, from: data)
                DispatchQueue.main.async {
                    self.upsertProject(project)
                    self.startNewSession(in: project)
                    self.loadProjectDirectory(project)
                }
            } catch {
                print("[createBlankProject] decode error: \(error)")
            }
        }.resume()
    }

    func chooseExistingProjectFolder() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.title = "Use Existing Folder"
        panel.prompt = "Use Folder"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        createFolderProject(path: url.path, name: url.lastPathComponent)
    }

    func createFolderProject(path: String, name: String?) {
        guard let url = URL(string: "http://backend/api/projects/from-folder") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONEncoder().encode(CreateFolderProjectRequest(path: path, name: name))
        URLSession.shared.dataTask(with: request) { [weak self] data, _, error in
            guard let self, let data, error == nil else { return }
            do {
                let project = try JSONDecoder().decode(ProjectInfo.self, from: data)
                DispatchQueue.main.async {
                    self.upsertProject(project)
                    self.startNewSession(in: project)
                    self.loadProjectDirectory(project)
                }
            } catch {
                print("[createFolderProject] decode error: \(error)")
            }
        }.resume()
    }

    private func upsertProject(_ project: ProjectInfo) {
        if let index = projects.firstIndex(where: { $0.id == project.id }) {
            projects[index] = project
        } else {
            projects.insert(project, at: 0)
        }
        activeProjectId = project.id
        activeProjectName = project.name
        activeProjectPath = project.path
    }

    func fetchSessions(retries: Int = 10, offset: Int = 0, append: Bool = false) {
        guard let url = URL(string: "http://backend/api/sessions?limit=\(sessionPageSize)&offset=\(offset)") else { return }
        if retries == 10 { sessionsLoading = true }
        var request = URLRequest(url: url, timeoutInterval: 10)
        request.httpMethod = "GET"
        URLSession.shared.dataTask(with: request) { [weak self] data, _, error in
            guard let data = data, error == nil else {
                if retries > 0 {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
                        self?.fetchSessions(retries: retries - 1, offset: offset, append: append)
                    }
                } else {
                    DispatchQueue.main.async { [weak self] in
                        self?.sessionsLoading = false
                    }
                }
                return
            }
            do {
                let response = try JSONDecoder().decode(SessionListResponse.self, from: data)
                DispatchQueue.main.async { [weak self] in
                    guard let self else { return }
                    self.sessions = append ? self.sessions + response.sessions : response.sessions
                    self.sessionsTotal = response.total ?? self.sessions.count
                    self.sessionsHasMore = response.has_more ?? false
                    self.sessionsLoading = false
                    if self.isFirstSessionFetch && !append {
                        self.isFirstSessionFetch = false
                        if let mostRecent = response.sessions.first {
                            if self.currentSessionId == mostRecent.session_id {
                                // Already pointing to the right session, just load its history
                                self.loadChatHistory()
                            } else {
                                self.switchToSession(mostRecent.session_id)
                            }
                        } else {
                            self.addGreeting()
                        }
                    }
                }
            } catch {
                if retries > 0 {
                    let delay = 5 - retries >= 2 ? 3.0 : 1.0
                    DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
                        self?.fetchSessions(retries: retries - 1, offset: offset, append: append)
                    }
                } else {
                    DispatchQueue.main.async { [weak self] in
                        self?.sessionsLoading = false
                    }
                }
            }
        }.resume()
    }

    func fetchMoreSessions() {
        guard sessionsHasMore, !sessionsLoading else { return }
        fetchSessions(offset: sessions.count, append: true)
    }

    func loadDefaultWorkspaceDirectory() {
        let workspaceURL = LocalAppPaths.root.appendingPathComponent("workspace", isDirectory: true)
        try? FileManager.default.createDirectory(at: workspaceURL, withIntermediateDirectories: true)
        loadDirectoryTree(path: workspaceURL.path, name: workspaceURL.lastPathComponent)
    }

    func loadProjectDirectory(_ project: ProjectInfo) {
        loadDirectoryTree(path: project.path, name: project.name)
    }

    private func loadDirectoryTree(path: String, name: String) {
        let expandedPath = (path as NSString).expandingTildeInPath
        let url = URL(fileURLWithPath: expandedPath)
        currentFileTreeRootPath = url.path
        currentFileTreeRootName = name.isEmpty ? url.lastPathComponent : name
        fileTree = [FileItemModel(
            name: currentFileTreeRootName ?? url.lastPathComponent,
            path: url.path,
            isFolder: true,
            children: loadContents(of: url.path),
            isExpanded: true
        )]
    }

    func loadHomeDirectory() {
        if let rootPath = currentFileTreeRootPath {
            loadDirectoryTree(path: rootPath, name: currentFileTreeRootName ?? URL(fileURLWithPath: rootPath).lastPathComponent)
        } else {
            loadDefaultWorkspaceDirectory()
        }
    }

    func toggleFolderExpansion(for item: FileItemModel) {
        var updatedTree = fileTree
        _ = updateTreeExpansion(&updatedTree, targetId: item.id)
        fileTree = updatedTree
    }

    private func updateTreeExpansion(_ nodes: inout [FileItemModel], targetId: String) -> Bool {
        for i in 0..<nodes.count {
            if nodes[i].id == targetId {
                nodes[i].isExpanded.toggle()
                if nodes[i].isExpanded && (nodes[i].children == nil || nodes[i].children!.isEmpty) {
                    nodes[i].children = loadContents(of: nodes[i].path)
                }
                return true
            }
            if nodes[i].children != nil {
                if updateTreeExpansion(&nodes[i].children!, targetId: targetId) {
                    return true
                }
            }
        }
        return false
    }

    private func loadContents(of path: String) -> [FileItemModel] {
        let options: FileManager.DirectoryEnumerationOptions = showHiddenFiles ? [] : [.skipsHiddenFiles]
        guard let urls = try? FileManager.default.contentsOfDirectory(at: URL(fileURLWithPath: path), includingPropertiesForKeys: [.isDirectoryKey], options: options) else {
            return []
        }

        var items: [FileItemModel] = []
        for url in urls {
            let isDir = (try? url.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) ?? false
            // Don't add .DS_Store
            if url.lastPathComponent == ".DS_Store" { continue }
            items.append(FileItemModel(name: url.lastPathComponent, path: url.path, isFolder: isDir, children: isDir ? [] : nil, isExpanded: false))
        }

        // Sort: folders first, then alphabetically
        items.sort { a, b in
            if a.isFolder == b.isFolder {
                return a.name.localizedCaseInsensitiveCompare(b.name) == .orderedAscending
            }
            return a.isFolder && !b.isFolder
        }

        return items
    }

    func collapseAllFolders() {
        var updatedTree = fileTree
        collapseNodes(&updatedTree)
        fileTree = updatedTree
    }

    private func collapseNodes(_ nodes: inout [FileItemModel]) {
        for i in 0..<nodes.count {
            nodes[i].isExpanded = false
            if nodes[i].children != nil {
                collapseNodes(&nodes[i].children!)
            }
        }
    }

    func toggleHiddenFiles() {
        showHiddenFiles.toggle()

        // If we are hiding files, ensure the selected file falls back to a visible ancestor
        if !showHiddenFiles, let selected = selectedFileId {
            let url = URL(fileURLWithPath: selected)
            let components = url.pathComponents
            var visiblePath = ""

            for component in components {
                if component.hasPrefix(".") && component != "." && component != ".." {
                    break
                }
                if visiblePath.isEmpty {
                    visiblePath = component
                } else if visiblePath == "/" {
                    visiblePath += component
                } else {
                    visiblePath += "/" + component
                }
            }

            if visiblePath != selected {
                selectedFileId = visiblePath
            }
        }

        // Force an immediate root reload, then re-apply expansions
        let currentTree = fileTree
        loadDefaultWorkspaceDirectory()
        if var newTree = fileTree.first, let oldRoot = currentTree.first {
            newTree.isExpanded = oldRoot.isExpanded
            if oldRoot.isExpanded {
                newTree.children = mergeChildren(old: oldRoot.children ?? [], new: loadContents(of: newTree.path))
            }
            fileTree = [newTree]
        }
    }

    private func rebuildNodeWithHiddenFiles(_ nodes: inout [FileItemModel]) {
        for i in 0..<nodes.count {
            if nodes[i].isFolder {
                if nodes[i].isExpanded {
                    let newContents = loadContents(of: nodes[i].path)
                    nodes[i].children = mergeChildren(old: nodes[i].children ?? [], new: newContents)
                } else if nodes[i].children != nil {
                    // Even if not expanded, rebuild children if they exist to keep data fresh
                    rebuildNodeWithHiddenFiles(&nodes[i].children!)
                }
            }
        }
    }
    func refreshFileTree() {
        if let selectedId = selectedFileId {
            var updatedTree = fileTree
            if refreshNode(&updatedTree, targetId: selectedId) {
                fileTree = updatedTree
                return
            }
        }
        // Fallback to refresh root if nothing selected or not found
        if let rootPath = currentFileTreeRootPath {
            loadDirectoryTree(path: rootPath, name: currentFileTreeRootName ?? URL(fileURLWithPath: rootPath).lastPathComponent)
        } else {
            loadDefaultWorkspaceDirectory()
        }
    }

    private func refreshNode(_ nodes: inout [FileItemModel], targetId: String) -> Bool {
        for i in 0..<nodes.count {
            if nodes[i].id == targetId {
                if nodes[i].isFolder {
                    let newContents = loadContents(of: nodes[i].path)
                    // Merge new contents with old to preserve expanded states
                    nodes[i].children = mergeChildren(old: nodes[i].children ?? [], new: newContents)
                }
                return true
            }
            if nodes[i].children != nil {
                if refreshNode(&nodes[i].children!, targetId: targetId) {
                    return true
                }
            }
        }
        return false
    }

    private func mergeChildren(old: [FileItemModel], new: [FileItemModel]) -> [FileItemModel] {
        var merged = new
        for i in 0..<merged.count {
            if let oldMatch = old.first(where: { $0.path == merged[i].path }) {
                merged[i].isExpanded = oldMatch.isExpanded
                if oldMatch.isExpanded && oldMatch.children != nil {
                    merged[i].children = mergeChildren(old: oldMatch.children!, new: loadContents(of: merged[i].path))
                }
            }
        }
        return merged
    }

    private func loadChatHistory() {
        guard !hasLoadedHistory else { return }
        hasLoadedHistory = true
        historyOffset = 0
        loadHistoryPage()
    }

    private func loadHistoryPage() {
        let urlStr = "http://backend/api/history/\(currentSessionId)?limit=\(historyPageSize)&offset=\(historyOffset)"
        guard let url = URL(string: urlStr) else { return }

        URLSession.shared.dataTask(with: url) { [weak self] data, _, error in
            guard let self = self, let data = data, error == nil else {
                DispatchQueue.main.async { self?.addGreeting() }
                return
            }

            do {
                let historyResponse = try JSONDecoder().decode(ChatHistoryResponse.self, from: data)
                let msgs = historyResponse.messages

                guard !msgs.isEmpty else {
                    DispatchQueue.main.async { self.addGreeting() }
                    return
                }

                var loadedMessages: [Message] = []
                var loadedHistory: [HistoryItem] = []
                for m in msgs {
                    let isUser = (m.role == "user")
                    loadedMessages.append(Message(content: m.content ?? "", isUser: isUser))
                    if isUser {
                        var pureText = m.content ?? ""
                        if let range = pureText.range(of: "<attached_files>") {
                            pureText = String(pureText[..<range.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
                        } else if let range = pureText.range(of: legacyAttachmentMarker) {
                            pureText = String(pureText[..<range.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
                        }
                        loadedHistory.append(HistoryItem(text: pureText, files: []))
                    }
                }

                DispatchQueue.main.async {
                    let isFirstPage = self.historyOffset == 0
                    if isFirstPage {
                        self.messages = loadedMessages
                        self.inputHistory = loadedHistory
                        self.historyIndex = loadedHistory.count
                    } else {
                        self.messages.insert(contentsOf: loadedMessages, at: 0)
                        self.inputHistory.insert(contentsOf: loadedHistory, at: 0)
                        self.historyIndex += loadedHistory.count
                    }
                    self.historyOffset += self.historyPageSize
                    self.hasMoreHistory = historyResponse.has_more ?? false
                    self.isLoadingMoreHistory = false
                    let total = historyResponse.total ?? loadedMessages.count
                    print("[loadHistory] page=\(isFirstPage ? "first" : "more") offset=\(self.historyOffset) loaded=\(loadedMessages.count) total=\(total) hasMore=\(self.hasMoreHistory)")
                }
            } catch {
                print("[loadChatHistory] decode error: \(error)")
                DispatchQueue.main.async {
                    self.isLoadingMoreHistory = false
                    self.addGreeting()
                }
            }
        }.resume()
    }

    func loadMoreHistory() {
        guard hasMoreHistory, !isLoadingMoreHistory else { return }
        isLoadingMoreHistory = true
        loadHistoryPage()
    }

    private func addGreeting() {
        DispatchQueue.main.async {
            self.messages.append(Message(
                content: "Hello! I'm your Across Agents Assistant. Press Option+Tab anytime to chat with me.",
                isUser: false
            ))
        }
    }

    func sendMessage(_ text: String, attachedFiles: [AttachedFile] = []) {
        let cleanText = sanitizeAttachmentPlaceholders(in: text)
        let displayTrimmedText = cleanText.trimmingCharacters(in: .whitespacesAndNewlines)

        guard !displayTrimmedText.isEmpty || !attachedFiles.isEmpty else { return }

        let userMsg = Message(content: displayTrimmedText, isUser: true, attachedFiles: attachedFiles)
        messages.append(userMsg)

        var backendText = displayTrimmedText

        // Non-image files still need path context for local agents/tools. Image attachments are
        // sent through the structured attachments payload so vision-capable models receive pixels.
        for file in attachedFiles where !file.isImageAttachment {
            if !backendText.isEmpty && !backendText.hasSuffix(" ") {
                backendText += " "
            }
            backendText += "[\"\(file.path)\"]"
        }

        backendText = backendText.trimmingCharacters(in: .whitespacesAndNewlines)

        // Add to history if different from the last sent message
        let historyItem = HistoryItem(text: displayTrimmedText, files: attachedFiles)
        if inputHistory.last != historyItem {
            inputHistory.append(historyItem)
        }
        historyIndex = inputHistory.count

        isProcessing = true

        // 1. Collect Tier 1 Context
        let context = ContextEngine.shared.collectTier1Context(
            includeActiveAppContext: includeActiveAppContext
        )

        // 2. Build Request
        let req = ChatRequest(
            text: backendText,
            context: context,
            session_id: currentSessionId,
            agent_id: AgentIDs.normalized(selectedAgentId) ?? selectedAgentId,
            project_id: activeProjectId,
            project_dir: activeProjectPath,
            attachments: attachedFiles.isEmpty ? nil : attachedFiles.map(ChatAttachment.init(file:))
        )

        guard let url = URL(string: "http://backend/api/chat") else {
            self.addError("API URL Invalid")
            return
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        // Local CLI agents can legitimately run close to the backend's
        // ACROSS_AGENTS_AGENT_TIMEOUT default (600s). Keep the client open
        // long enough to receive the final delivery instead of timing out
        // while the backend process continues and loses the UI response.
        request.timeoutInterval = Self.longRunningAgentRequestTimeout

        do {
            request.httpBody = try JSONEncoder().encode(req)
        } catch {
            self.addError("Failed to encode request")
            return
        }

        // 3. Send HTTP Request
        currentChatTask = URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            DispatchQueue.main.async {
                // If it was cancelled intentionally, don't show an error
                if let nsError = error as NSError?, nsError.code == NSURLErrorCancelled {
                    self?.isProcessing = false
                    self?.currentChatTask = nil
                    return
                }

                self?.isProcessing = false
                self?.currentChatTask = nil

                if let error = error {
                    self?.addError("Network error: \(error.localizedDescription)")
                    return
                }

                guard let data = data else {
                    self?.addError("No data received")
                    return
                }

                do {
                    let chatResp = try JSONDecoder().decode(ChatResponse.self, from: data)

                    if let sessionId = chatResp.session_id {
                        self?.currentSessionId = sessionId
                    }

                    if chatResp.requires_approval == true, let request = chatResp.approval_request {
                        self?.pendingApproval = request
                    } else {
                        // Backend can return 200 with empty text; MainPanelView hides empty assistant bubbles,
                        // which looks like "no reply" — surface a visible placeholder instead.
                        let raw = chatResp.text.trimmingCharacters(in: .whitespacesAndNewlines)
                        let display = raw.isEmpty
                            ? "(The model returned no visible text. Check the API key or network, or try another model.)"
                            : chatResp.text
                        self?.messages.append(Message(
                            content: display,
                            isUser: false,
                            attachedFiles: []
                        ))

                        // Play Native TTS if enabled and not muted
                        if let self, !self.isMuted, self.speechPlaybackSettings.autoReadReplies {
                            let settings = self.speechPlaybackSettings
                            TTSEngine.shared.speak(
                                display,
                                voiceSource: settings.voiceSource,
                                chosenVoiceIdentifier: settings.chosenVoiceIdentifier,
                                fallbackLanguage: settings.fallbackLanguage,
                                rate: settings.speechRate,
                                volume: settings.speechVolume
                            )
                        }
                    }
                    self?.fetchProjects()
                    self?.fetchSessions()
                } catch {
                    self?.addError("Failed to parse response: \(error.localizedDescription)")
                }
            }
        }

        isProcessing = true
        currentChatTask?.resume()
    }

    func cancelGeneration() {
        guard isProcessing else { return }

        // 1. Cancel the local URLSession request
        currentChatTask?.cancel()
        currentChatTask = nil
        isProcessing = false

        // 2. Add a visual indication to the UI
        let cancelMsg = Message(content: "Generation stopped", isUser: false, attachedFiles: [])
        messages.append(cancelMsg)

        // 3. Send the cancel signal to the backend
        guard let url = URL(string: "http://backend/api/chat/cancel") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let payload: [String: String] = ["session_id": currentSessionId]

        if let body = try? JSONEncoder().encode(payload) {
            request.httpBody = body
            URLSession.shared.dataTask(with: request).resume() // Fire and forget
        }
    }

    func navigateHistory(up: Bool) {
        if inputHistory.isEmpty { return }

        if up {
            if historyIndex > 0 {
                historyIndex -= 1
                let item = inputHistory[historyIndex]
                inputText = sanitizeAttachmentPlaceholders(in: item.text)
                attachedFiles = item.files
            }
        } else {
            if historyIndex < inputHistory.count - 1 {
                historyIndex += 1
                let item = inputHistory[historyIndex]
                inputText = sanitizeAttachmentPlaceholders(in: item.text)
                attachedFiles = item.files
            } else if historyIndex == inputHistory.count - 1 {
                historyIndex = inputHistory.count
                inputText = ""
                attachedFiles = []
            }
        }
    }

    private func sanitizeAttachmentPlaceholders(in text: String) -> String {
        text.replacingOccurrences(of: "\u{FFFC}", with: " ")
    }

    func submitDecision(decision: String) {
        guard let requestObj = pendingApproval else { return }

        // Check permissions for high-risk tools before submitting decision
        if (decision == "approve" || decision == "always_allow") {
            let toolName = requestObj.tool_name
            // Tools that require Accessibility/Automation permissions
            if ["get_active_browser_url", "get_finder_context"].contains(toolName) {
                if !ContextEngine.shared.hasAccessibilityPermission() {
                    // Show our beautiful permission alert instead of submitting
                    DispatchQueue.main.async {
                        self.showPermissionAlert = true
                    }
                    return
                }
            }
        }

        // Hide app temporarily if the tool requires UI interaction (like screencapture)
        if (decision == "approve" || decision == "always_allow") && requestObj.tool_name == "take_screenshot_and_ocr" {
            DispatchQueue.main.async {
                NSApp.hide(nil)
            }
        }

        self.pendingApproval = nil
        self.isProcessing = true // Keep processing true while we wait for the LLM's continuation response

        let decisionReq = ApprovalDecisionRequest(
            session_id: currentSessionId,
            decision: decision,
            tool_name: requestObj.tool_name,
            tool_args: requestObj.tool_args,
            agent_id: AgentIDs.normalized(selectedAgentId) ?? selectedAgentId,
            tool_call_id: requestObj.tool_call_id
        )

        isProcessing = true

        guard let url = URL(string: "http://backend/api/approve") else {
            self.addError("API URL Invalid")
            return
        }

        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.timeoutInterval = Self.longRunningAgentRequestTimeout

        do {
            urlRequest.httpBody = try JSONEncoder().encode(decisionReq)
        } catch {
            self.addError("Failed to encode decision")
            return
        }

        URLSession.shared.dataTask(with: urlRequest) { data, response, error in
            DispatchQueue.main.async {
                self.isProcessing = false

                if let error = error {
                    self.addError("Network error: \(error.localizedDescription)")
                    return
                }

                guard let data = data else {
                    self.addError("No data received")
                    return
                }

                do {
                    let chatResp = try JSONDecoder().decode(ChatResponse.self, from: data)

                    DispatchQueue.main.async {
                        if (decisionReq.decision == "approve" || decisionReq.decision == "always_allow") && decisionReq.tool_name == "take_screenshot_and_ocr" {
                            self.showApp()
                        }

                        let botMsg = Message(content: chatResp.text, isUser: false)
                        self.messages.append(botMsg)

                        if !self.isMuted {
                            TTSEngine.shared.speak(chatResp.text)
                        }
                    }
                } catch {
                    DispatchQueue.main.async {
                        self.addError("Parse failed: \(error.localizedDescription)")
                    }
                }
            }
        }.resume()
    }

    private func addError(_ message: String) {
        isProcessing = false
        messages.append(Message(
            content: "⚠️ \(message)",
            isUser: false,
            attachedFiles: []
        ))
    }

    func showErrorMessage(_ message: String) {
        addError(message)
    }

    func copyFullConversation() {
        let maxCharacters = 100000 // 100k characters limit
        var copiedText = ""
        var currentLength = 0
        var isTruncated = false

        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd HH:mm:ss"

        // Reverse iterate to prioritize latest messages
        for msg in messages.reversed() {
            let role = msg.isUser ? "User" : "Agent"
            let timeStr = dateFormatter.string(from: msg.timestamp)
            var msgStr = "[\(timeStr)] \(role):\n\(msg.content)\n\n"

            if !msg.attachedFiles.isEmpty {
                let fileNames = msg.attachedFiles.map { $0.name }.joined(separator: ", ")
                msgStr += "📎 Attachments: \(fileNames)\n\n"
            }

            if currentLength + msgStr.count > maxCharacters {
                isTruncated = true
                break
            }

            // Prepend because we are iterating backwards
            copiedText = msgStr + copiedText
            currentLength += msgStr.count
        }

        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(copiedText, forType: .string)

        if isTruncated {
            // Optional: You can also show an NSAlert here or rely on a toast UI
            let alert = NSAlert()
            alert.messageText = "Conversation Copied"
            alert.informativeText = "The conversation was copied to the clipboard. Because it is long, earlier messages may have been truncated. The latest content is preserved first, up to about 100,000 characters."
            alert.alertStyle = .warning
            alert.runModal()
        } else {
            // Show a simple success feedback if possible
            // Let's just do a small non-blocking notification or nothing
        }
    }

    func openAccessibilitySettings() {
        ContextEngine.shared.promptForAccessibilityPermission()

        let urlString = "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
        if let url = URL(string: urlString) {
            NSWorkspace.shared.open(url)
        }

        // After opening settings, cancel the pending request to avoid blocking
        self.submitDecision(decision: "reject")
        self.showPermissionAlert = false
    }
}
