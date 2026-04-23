import Foundation
import Combine
import AVFoundation
import AppKit

struct Message: Identifiable {
    let id = UUID()
    let content: String
    let isUser: Bool
    let timestamp: Date = Date()
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
    let id = UUID()
    let name: String
    let path: String
    let isFolder: Bool
    var children: [FileItemModel]?
    var isExpanded: Bool = false
    
    static func == (lhs: FileItemModel, rhs: FileItemModel) -> Bool {
        return lhs.id == rhs.id && lhs.isExpanded == rhs.isExpanded && lhs.children?.count == rhs.children?.count
    }
}

class SessionViewModel: ObservableObject {
    @Published var messages: [Message] = []
    @Published var isProcessing: Bool = false
    @Published var pendingApproval: ApprovalRequest? = nil
    @Published var showPermissionAlert: Bool = false
    @Published var inputText: String = "" // Add inputText to ViewModel so we can modify it from here
    @Published var isMuted: Bool = false {
        didSet {
            if isMuted {
                TTSEngine.shared.stop()
            }
        }
    }
    
    @Published var selectedAgentId: String = "openclaw"
    let agents: [AgentModel] = [
        AgentModel(id: "openclaw", name: "OpenClaw", iconName: "agent.openclaw", color: "#CBA6F0"),
        AgentModel(id: "hermes", name: "Hermes", iconName: "agent.hermes", color: "#FF9F0A"),
        AgentModel(id: "claude", name: "Trae Solo", iconName: "agent.claude", color: "#D9775A")
    ]
    
    @Published var fileTree: [FileItemModel] = []
    @Published var selectedFileId: UUID? = nil
    
    // Callbacks to decouple UI operations from the ViewModel
    var onHidePanel: (() -> Void)?
    var onShowPanel: (() -> Void)?
    
    private var currentSessionId: String = "default-session"
    
    func requestManualScreenshot() {
        onHidePanel?()
        
        // We MUST yield the main thread to allow the RunLoop to actually process the window hide event
        // before we launch the screencapture process. A slight delay ensures the window shadow and fade-out complete.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
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
    }
    
    init() {
        // Load history or greet
        loadChatHistory()
        loadHomeDirectory()
    }
    
    func loadHomeDirectory() {
        let homeUrl = FileManager.default.homeDirectoryForCurrentUser
        fileTree = [FileItemModel(name: homeUrl.lastPathComponent, path: homeUrl.path, isFolder: true, children: [], isExpanded: false)]
    }
    
    func toggleFolderExpansion(for item: FileItemModel) {
        var updatedTree = fileTree
        _ = updateTreeExpansion(&updatedTree, targetId: item.id)
        fileTree = updatedTree
    }
    
    private func updateTreeExpansion(_ nodes: inout [FileItemModel], targetId: UUID) -> Bool {
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
        guard let urls = try? FileManager.default.contentsOfDirectory(at: URL(fileURLWithPath: path), includingPropertiesForKeys: [.isDirectoryKey], options: [.skipsHiddenFiles]) else {
            return []
        }
        
        var items: [FileItemModel] = []
        for url in urls {
            let isDir = (try? url.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) ?? false
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
    
    private func refreshNode(_ nodes: inout [FileItemModel], targetId: UUID) -> Bool {
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
                    for m in msgs {
                        if let role = m["role"] as? String, let content = m["content"] as? String {
                            // "user", "assistant", "tool"
                            let isUser = (role == "user")
                            loadedMessages.append(Message(content: content, isUser: isUser))
                        }
                    }
                    
                    DispatchQueue.main.async {
                        self.messages = loadedMessages
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
                content: "Hello! I'm your Across Agents Copilot. Press Cmd+Option+Space anytime to chat with me.",
                isUser: false
            ))
        }
    }
    
    func submitMessage(_ text: String) {
        guard !text.isEmpty else { return }
        
        let userMsg = Message(content: text, isUser: true)
        messages.append(userMsg)
        
        isProcessing = true
        
        // 1. Collect Tier 1 Context
        let context = ContextEngine.shared.collectTier1Context()
        
        // 2. Build Request
        let req = ChatRequest(
            text: text,
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
        
        do {
            request.httpBody = try JSONEncoder().encode(req)
        } catch {
            self.addError("Failed to encode request")
            return
        }
        
        // 3. Send HTTP Request
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            DispatchQueue.main.async {
                self?.isProcessing = false
                
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
                    
                    DispatchQueue.main.async {
                        if let sessionId = chatResp.session_id {
                            self?.currentSessionId = sessionId
                        }
                        
                        // Use the correct text property from chatResp
                        let botMsg = Message(content: chatResp.text, isUser: false)
                        self?.messages.append(botMsg)
                        
                        // Trigger Native TTS
                        if self?.isMuted == false {
                            TTSEngine.shared.speak(chatResp.text)
                        }
                        
                        // Handle Phase 3: Security Approval Flow
                        if chatResp.requires_approval == true, let request = chatResp.approval_request {
                            self?.pendingApproval = request
                        } else {
                            // If the user only has default voices, show a gentle tip in the UI once
                            if !TTSEngine.shared.hasHighQualityVoice && self?.messages.filter({ !$0.isUser }).count == 2 {
                                let tipMsg = Message(content: "💡 提示：为了让我说话更自然，请在 Mac 的「系统设置 -> 辅助功能 -> 朗读内容 -> 管理声音」中下载【Tingting(增强/高级)】或【Siri】的中文语音包哦~", isUser: false)
                                self?.messages.append(tipMsg)
                            }
                        }
                    }
                } catch {
                    DispatchQueue.main.async {
                        self?.addError("解析失败: \(error.localizedDescription)\n返回数据: \(String(data: data, encoding: .utf8) ?? "")")
                    }
                }
            }
        }.resume()
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
    
    private func addError(_ text: String) {
        isProcessing = false
        messages.append(Message(content: "⚠️ " + text, isUser: false))
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
