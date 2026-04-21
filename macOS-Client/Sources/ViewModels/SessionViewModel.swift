import Foundation

struct Message: Identifiable {
    let id = UUID()
    let content: String
    let isUser: Bool
    let timestamp: Date = Date()
}

class SessionViewModel: ObservableObject {
    @Published var messages: [Message] = []
    @Published var isProcessing: Bool = false
    
    init() {
        // Initial greeting
        messages.append(Message(content: "你好！我是 Across Agents Assistant 桌面副驾。按 Cmd+Option+Space 随时唤醒我。", isUser: false))
    }
    
    func submitMessage(_ text: String) {
        guard !text.isEmpty else { return }
        
        let userMsg = Message(content: text, isUser: true)
        messages.append(userMsg)
        
        isProcessing = true
        
        // TODO: In Phase 2, this will send an HTTP request to the Python backend
        // For Phase 1, we just mock the response
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            self.isProcessing = false
            let botMsg = Message(content: "这是 Swift 原生壳层收到的消息: \"\(text)\"\n\n在接下来的阶段，我会将这条消息发给 Python 后端，并带上你当前的屏幕上下文！", isUser: false)
            self.messages.append(botMsg)
        }
    }
}
