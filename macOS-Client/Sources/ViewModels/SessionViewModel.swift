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
    var session_id: String
    var decision: String
    var tool_name: String
    var tool_args: [String: AnyCodableValue]?
}

class SessionViewModel: ObservableObject {
    @Published var messages: [Message] = []
    @Published var isProcessing: Bool = false
    @Published var pendingApproval: ApprovalRequest? = nil
    @Published var inputText: String = "" // Add inputText to ViewModel so we can modify it from here
    
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
            agent_id: "openclaw" // Using default
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
        URLSession.shared.dataTask(with: request) { data, response, error in
            DispatchQueue.main.async {
                self.isProcessing = false
                
                // Show the panel again if we hid it for screenshot
                if let decisionStr = (request.httpBody.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }?["decision"] as? String),
                   let toolName = (request.httpBody.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }?["tool_name"] as? String) {
                    if decisionStr == "approve" && toolName == "take_screenshot_and_ocr" {
                        self.onShowPanel?()
                    }
                }
                
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
                    if let sessionId = chatResp.session_id {
                        self.currentSessionId = sessionId
                    }
                    let botMsg = Message(content: chatResp.text, isUser: false)
                    self.messages.append(botMsg)
                    
                    // Trigger Native TTS
                    TTSEngine.shared.speak(chatResp.text)
                    
                    // Handle Phase 3: Security Approval Flow
                    if chatResp.requires_approval == true, let request = chatResp.approval_request {
                        self.pendingApproval = request
                    } else {
                        // If the user only has default voices, show a gentle tip in the UI once
                        if !TTSEngine.shared.hasHighQualityVoice && self.messages.filter({ !$0.isUser }).count == 2 {
                            let tipMsg = Message(content: "💡 提示：为了让我说话更自然，请在 Mac 的「系统设置 -> 辅助功能 -> 朗读内容 -> 管理声音」中下载【Tingting(增强/高级)】或【Siri】的中文语音包哦~", isUser: false)
                            self.messages.append(tipMsg)
                        }
                    }
                    
                } catch {
                    self.addError("解析失败: \(error.localizedDescription)\n返回数据: \(String(data: data, encoding: .utf8) ?? "")")
                }
            }
        }.resume()
    }
    
    func submitDecision(decision: String) {
        guard let request = pendingApproval else { return }
        
        // Hide panel temporarily if the tool requires UI interaction (like screencapture)
        if (decision == "approve" || decision == "always_allow") && request.tool_name == "take_screenshot_and_ocr" {
            DispatchQueue.main.async {
                self.onHidePanel?()
            }
        }
        
        self.pendingApproval = nil
        
        let decisionReq = ApprovalDecisionRequest(
            session_id: currentSessionId,
            decision: decision,
            tool_name: request.tool_name,
            tool_args: request.tool_args
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
                    let botMsg = Message(content: chatResp.text, isUser: false)
                    self.messages.append(botMsg)
                    TTSEngine.shared.speak(chatResp.text)
                } catch {
                    self.addError("解析失败: \(error.localizedDescription)")
                }
            }
        }.resume()
    }
    
    private func addError(_ text: String) {
        isProcessing = false
        messages.append(Message(content: "⚠️ " + text, isUser: false))
    }
}
