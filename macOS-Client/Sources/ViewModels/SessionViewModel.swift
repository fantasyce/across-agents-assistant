import Foundation
import Combine
import AVFoundation
import AppKit

struct AttachedFile: Identifiable, Codable, Equatable {
    let id = UUID()
    let name: String
    let path: String
    let isFolder: Bool
}

struct Message: Identifiable {
    let id = UUID()
    let content: String
    let isUser: Bool
    let timestamp: Date = Date()
    var attachedFiles: [AttachedFile] = []
}

struct ChatRequest: Codable {
    var text: String
    var context: ContextPack?
    var session_id: String?
    var agent_id: String?
}

struct ChatResponse: Codable {
    var text: String
    var session_id: String?
    var audio_path: String?
    var requires_approval: Bool?
    var approval_request: ApprovalRequest?
}

struct ApprovalDecisionRequest: Codable {
    let session_id: String
    let decision: String
    let tool_name: String
    let tool_args: [String: AnyCodableValue]?
    let agent_id: String
}

struct AgentModel: Identifiable {
    let id: String
    let name: String
    let iconName: String
    let color: String
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
    @Published var messages: [Message] = []
    @Published var isProcessing: Bool = false
    private var currentChatTask: URLSessionDataTask?
    @Published var pendingApproval: ApprovalRequest? = nil
    @Published var showPermissionAlert: Bool = false
    @Published var showMCPPreferences: Bool = false
    @Published var inputText: String = "" // Add inputText to ViewModel so we can modify it from here
    @Published var attachedFiles: [AttachedFile] = [] // Track files dropped into the input box
    @Published var showHiddenFiles: Bool = false
    
    // Input history state
    private struct HistoryItem: Equatable {
        let text: String
        let files: [AttachedFile]
    }
    private var inputHistory: [HistoryItem] = []
    private var historyIndex: Int = -1
    @Published var isMuted: Bool = false {
        didSet {
            if isMuted {
                TTSEngine.shared.stop()
            }
        }
    }
    
    @Published var selectedAgentId: String = "deepseek"
    let agents: [AgentModel] = [
        AgentModel(id: "openclaw", name: "OpenClaw", iconName: "agent.openclaw", color: "#CBA6F0"),
        AgentModel(id: "hermes", name: "Hermes", iconName: "agent.hermes", color: "#FF9F0A"),
        AgentModel(id: "claude", name: "Claude Code", iconName: "agent.claude", color: "#D9775A")
    ]
    
    @Published var fileTree: [FileItemModel] = [] {
        didSet {
            flatFileTree = flatten(nodes: fileTree, depth: 0)
        }
    }
    @Published var flatFileTree: [(node: FileItemModel, depth: Int)] = []
    @Published var selectedFileId: String? = nil
    
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
    
    // Callbacks to decouple UI operations from the ViewModel
    var onHidePanel: (() -> Void)?
    var onShowPanel: (() -> Void)?
    
    private var currentSessionId: String = "default-session"
    
    func requestManualScreenshot() {
        // 1. First check if we have screen recording permission
        if !ContextEngine.shared.hasScreenRecordingPermission() {
            // Hide the panel so the system prompt is visible
            onHidePanel?()
            
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
                // Trigger a modern, less scary screen recording prompt (SCShareableContent)
                // This ensures the app is added to the Privacy Settings list
                ContextEngine.shared.triggerScreenRecordingPrompt()
                
                // Show panel again and inform user
                DispatchQueue.main.async {
                    self.onShowPanel?()
                    if !self.inputText.isEmpty {
                        self.inputText += "\n"
                    }
                    self.inputText += "[提示：首次截图需要屏幕录制权限，请在弹出的系统提示中允许，或前往“系统设置 -> 隐私与安全性 -> 屏幕录制”中开启权限。授权后请重启应用]"
                }
            }
            return
        }
        
        // 2. We already have permission, hide panel and capture
        onHidePanel?()
        
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
            self.executeScreenshot()
        }
    }
    
    private func executeScreenshot() {
        ContextEngine.shared.performScreenshotAndOCR { [weak self] extractedText in
            guard let self = self else { return }
            
            self.onShowPanel?()
            
            if let text = extractedText {
                if !self.inputText.isEmpty {
                    self.inputText += "\n"
                }
                self.inputText += "【截图内容】:\n" + text + "\n"
            }
        }
    }
    
    init() {
        // Load history or greet
        loadChatHistory()
        loadHomeDirectory()
    }
    
    func loadHomeDirectory() {
        let homeUrl = FileManager.default.homeDirectoryForCurrentUser
        fileTree = [FileItemModel(name: homeUrl.lastPathComponent, path: homeUrl.path, isFolder: true, children: loadContents(of: homeUrl.path), isExpanded: true)]
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
        loadHomeDirectory()
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
        loadHomeDirectory()
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
        guard let url = URL(string: "http://127.0.0.1:8000/api/history/\(currentSessionId)") else { return }
        
        URLSession.shared.dataTask(with: url) { [weak self] data, response, error in
            guard let self = self, let data = data, error == nil else {
                self?.addGreeting()
                return
            }
            
            do {
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let msgs = json["messages"] as? [[String: Any]], !msgs.isEmpty {
                    
                    var loadedMessages: [Message] = []
                    var loadedHistory: [HistoryItem] = []
                    for m in msgs {
                        if let role = m["role"] as? String, let content = m["content"] as? String {
                            // "user", "assistant", "tool"
                            let isUser = (role == "user")
                            loadedMessages.append(Message(content: content, isUser: isUser))
                            if isUser {
                                // The backend now receives the inline path.
                                // We don't have to strip anything out, the path IS the text.
                                // However, if the old history format is loaded, we can still strip it for backward compatibility
                                var pureText = content
                                if let range = content.range(of: "<attached_files>") {
                                    pureText = String(content[..<range.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
                                } else if let range = content.range(of: "【附带的文件/目录】:\n") {
                                    pureText = String(content[..<range.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
                                }
                                loadedHistory.append(HistoryItem(text: pureText, files: []))
                            }
                        }
                    }
                    
                    DispatchQueue.main.async {
                        self.messages = loadedMessages
                        self.inputHistory = loadedHistory
                        self.historyIndex = loadedHistory.count
                    }
                } else {
                    self.addGreeting()
                }
            } catch {
                self.addGreeting()
            }
        }.resume()
    }
    
    private func addGreeting() {
        DispatchQueue.main.async {
            self.messages.append(Message(
                content: "Hello! I'm your Across Agents Copilot. Press Option+Tab anytime to chat with me.",
                isUser: false
            ))
        }
    }
    
    func sendMessage(_ text: String, attachedFiles: [AttachedFile] = []) {
        let displayTrimmedText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        
        guard !displayTrimmedText.isEmpty || !attachedFiles.isEmpty else { return }
        
        let userMsg = Message(content: displayTrimmedText, isUser: true, attachedFiles: attachedFiles)
        messages.append(userMsg)
        
        // Build the actual text to send to the backend
        // Instead of appending a block at the end, we replace the \u{FFFC} placeholders 
        // with the actual file paths inline!
        var backendText = ""
        let components = text.components(separatedBy: "\u{FFFC}")
        var fileIndex = 0
        
        for (i, component) in components.enumerated() {
            backendText += component
            if i < components.count - 1 && fileIndex < attachedFiles.count {
                let file = attachedFiles[fileIndex]
                backendText += "[\"\(file.path)\"]"
                fileIndex += 1
            }
        }
        
        // If there are leftover files that weren't represented by \u{FFFC} (e.g., dropped at the very end without typing anything after)
        while fileIndex < attachedFiles.count {
            let file = attachedFiles[fileIndex]
            if !backendText.isEmpty && !backendText.hasSuffix(" ") {
                backendText += " "
            }
            backendText += "[\"\(file.path)\"]"
            fileIndex += 1
        }
        
        backendText = backendText.trimmingCharacters(in: .whitespacesAndNewlines)
        
        // Add to history if different from the last sent message
        // We save the original text (with placeholders) to history so it can be restored perfectly
        let historyItem = HistoryItem(text: text, files: attachedFiles)
        if inputHistory.last != historyItem {
            inputHistory.append(historyItem)
        }
        historyIndex = inputHistory.count
        
        isProcessing = true
        
        // 1. Collect Tier 1 Context
        let context = ContextEngine.shared.collectTier1Context()
        
        // 2. Build Request
        let req = ChatRequest(
            text: backendText,
            context: context,
            session_id: currentSessionId,
            agent_id: selectedAgentId // Dynamically use the selected agent
        )
        
        guard let url = URL(string: "http://127.0.0.1:8000/api/chat") else {
            self.addError("API URL Invalid")
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 300 // 5 minutes timeout for slow LLM generations
        
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
                    self?.addError("网络错误: \(error.localizedDescription)")
                    return
                }
                
                guard let data = data else {
                    self?.addError("未收到数据")
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
                        self?.messages.append(Message(
                            content: chatResp.text,
                            isUser: false,
                            attachedFiles: []
                        ))
                        
                        // Play Native TTS if not muted
                        if self?.isMuted == false {
                            TTSEngine.shared.speak(chatResp.text)
                        }
                    }
                } catch {
                    self?.addError("解析响应失败: \(error.localizedDescription)")
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
        let cancelMsg = Message(content: "已停止生成", isUser: false, attachedFiles: [])
        messages.append(cancelMsg)
        
        // 3. Send the cancel signal to the backend
        guard let url = URL(string: "http://127.0.0.1:8000/api/chat/cancel") else { return }
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
                inputText = item.text
                attachedFiles = item.files
            }
        } else {
            if historyIndex < inputHistory.count - 1 {
                historyIndex += 1
                let item = inputHistory[historyIndex]
                inputText = item.text
                attachedFiles = item.files
            } else if historyIndex == inputHistory.count - 1 {
                historyIndex = inputHistory.count
                inputText = ""
                attachedFiles = []
            }
        }
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
        
        // Hide panel temporarily if the tool requires UI interaction (like screencapture)
        if (decision == "approve" || decision == "always_allow") && requestObj.tool_name == "take_screenshot_and_ocr" {
            DispatchQueue.main.async {
                self.onHidePanel?()
            }
        }
        
        self.pendingApproval = nil
        self.isProcessing = true // Keep processing true while we wait for the LLM's continuation response
        
        let decisionReq = ApprovalDecisionRequest(
            session_id: currentSessionId,
            decision: decision,
            tool_name: requestObj.tool_name,
            tool_args: requestObj.tool_args,
            agent_id: selectedAgentId
        )
        
        isProcessing = true
        
        guard let url = URL(string: "http://127.0.0.1:8000/api/approve") else {
            self.addError("API URL Invalid")
            return
        }
        
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = "POST"
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        urlRequest.timeoutInterval = 300 // 5 minutes timeout for slow LLM generations
        
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
                    self.addError("网络错误: \(error.localizedDescription)")
                    return
                }
                
                guard let data = data else {
                    self.addError("未收到数据")
                    return
                }
                
                do {
                    let chatResp = try JSONDecoder().decode(ChatResponse.self, from: data)
                    
                    DispatchQueue.main.async {
                        if (decisionReq.decision == "approve" || decisionReq.decision == "always_allow") && decisionReq.tool_name == "take_screenshot_and_ocr" {
                            self.onShowPanel?()
                        }
                        
                        let botMsg = Message(content: chatResp.text, isUser: false)
                        self.messages.append(botMsg)
                        
                        if !self.isMuted {
                            TTSEngine.shared.speak(chatResp.text)
                        }
                    }
                } catch {
                    DispatchQueue.main.async {
                        self.addError("解析失败: \(error.localizedDescription)")
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
                msgStr += "📎 附件: \(fileNames)\n\n"
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
            alert.messageText = "对话已复制"
            alert.informativeText = "对话内容已复制到剪贴板，但由于内容过长，早期的对话可能已被截断（最多保留约10万字符，优先保留最新内容）。"
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
