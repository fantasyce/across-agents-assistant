import Foundation

struct LLMConfig: Identifiable {
    let id: String
    var name: String
    var apiKey: String?
    var endpoint: String?
    var model: String?
    var temperature: Double = 0.7
    var maxTokens: Int = 8192

    var iconName: String {
        "agent.\(id.lowercased())"
    }

    static let deepSeek = LLMConfig(
        id: "deepseek",
        name: "DeepSeek",
        endpoint: "https://api.deepseek.com",
        model: "deepseek-chat"
    )

    static let miniMax = LLMConfig(
        id: "minimax",
        name: "MiniMax",
        endpoint: "https://api.minimaxi.com/v1",
        model: "MiniMax-M2.7"
    )
}


// MARK: - Persisted LLM config (no apiKey — secrets live in backend-owned credentials file)

struct PersistedLLMConfig: Codable {
    let id: String
    var name: String
    var endpoint: String?
    var model: String?
    var temperature: Double
    var maxTokens: Int

    init(from config: LLMConfig) {
        self.id = config.id
        self.name = config.name
        self.endpoint = config.endpoint
        self.model = config.model
        self.temperature = config.temperature
        self.maxTokens = config.maxTokens
    }
}

extension LLMConfig {
    init(from persisted: PersistedLLMConfig) {
        self.id = persisted.id
        self.name = persisted.name
        self.apiKey = nil  // Secrets are not persisted in UserDefaults
        self.endpoint = persisted.endpoint
        self.model = persisted.model
        self.temperature = persisted.temperature
        self.maxTokens = persisted.maxTokens
    }
}