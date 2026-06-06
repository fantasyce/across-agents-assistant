import Foundation

struct LLMConfig: Identifiable {
    let id: String
    var name: String
    var apiKey: String?
    var endpoint: String?
    var model: String?
    var providerType: String = "openai_compatible"
    var modelsEndpoint: String? = nil
    var availableModels: [String]? = nil
    var temperature: Double = 0.7
    var maxTokens: Int = 8192

    var iconName: String {
        "agent.\(id.lowercased())"
    }

    static let deepSeek = LLMConfig(
        id: "deepseek",
        name: "DeepSeek",
        endpoint: "https://api.deepseek.com/v1",
        model: "deepseek-v4-pro",
        modelsEndpoint: "https://api.deepseek.com/v1/models",
        availableModels: ["deepseek-v4-pro", "deepseek-v4-flash"]
    )

    static let miniMax = LLMConfig(
        id: "minimax",
        name: "MiniMax",
        endpoint: "https://api.minimaxi.com/v1",
        model: "MiniMax-M3",
        modelsEndpoint: "https://api.minimaxi.com/v1/models",
        availableModels: ["MiniMax-M3", "MiniMax-M2.7", "MiniMax-M2.7-highspeed", "MiniMax-M2.5", "MiniMax-M2.5-highspeed"]
    )

    static let allDefaults: [LLMConfig] = [
        LLMConfig(id: "openai", name: "OpenAI", endpoint: "https://api.openai.com/v1", model: "gpt-5.5", modelsEndpoint: "https://api.openai.com/v1/models", availableModels: ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano"]),
        LLMConfig(id: "anthropic", name: "Anthropic", endpoint: "https://api.anthropic.com/v1", model: "claude-opus-4-8", providerType: "anthropic", modelsEndpoint: "https://api.anthropic.com/v1/models", availableModels: ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]),
        .deepSeek,
        .miniMax,
        LLMConfig(id: "bailian", name: "Alibaba Bailian / Qwen", endpoint: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen3.7-max", modelsEndpoint: "https://dashscope.aliyuncs.com/compatible-mode/v1/models", availableModels: ["qwen3.7-max", "qwen3.7-plus", "qwen3.6-flash", "qwen-plus-latest", "qwen-max-latest"]),
        LLMConfig(id: "moonshot", name: "Moonshot / Kimi", endpoint: "https://api.moonshot.ai/v1", model: "kimi-k2.6", modelsEndpoint: "https://api.moonshot.ai/v1/models", availableModels: ["kimi-k2.6", "kimi-k2-thinking-turbo", "moonshot-v1-128k"]),
        LLMConfig(id: "zhipu", name: "Zhipu GLM", endpoint: "https://open.bigmodel.cn/api/paas/v4", model: "glm-5.1", modelsEndpoint: "https://open.bigmodel.cn/api/paas/v4/models", availableModels: ["glm-5.1", "glm-5"]),
        LLMConfig(id: "volcengine", name: "Volcengine Ark / Doubao", endpoint: "https://ark.cn-beijing.volces.com/api/v3", model: "doubao-seed-2.0-mini", modelsEndpoint: "https://ark.cn-beijing.volces.com/api/v3/models", availableModels: ["doubao-seed-2.0-mini", "doubao-seed-1-8-251228", "doubao-seed-1-6-thinking-250715", "doubao-seed-1-6-flash-250828"]),
        LLMConfig(id: "google", name: "Google Gemini", endpoint: "https://generativelanguage.googleapis.com/v1beta/openai", model: "gemini-3.1-pro", modelsEndpoint: "https://generativelanguage.googleapis.com/v1beta/openai/models", availableModels: ["gemini-3.1-pro", "gemini-3.5-flash", "gemini-3-flash", "gemini-3.1-flash-lite"]),
        LLMConfig(id: "xai", name: "xAI", endpoint: "https://api.x.ai/v1", model: "grok-4.3", modelsEndpoint: "https://api.x.ai/v1/models", availableModels: ["grok-4.3", "grok-4.3-latest", "grok-build-0.1"]),
        LLMConfig(id: "mistral", name: "Mistral AI", endpoint: "https://api.mistral.ai/v1", model: "mistral-large-latest", modelsEndpoint: "https://api.mistral.ai/v1/models", availableModels: ["mistral-large-latest", "mistral-medium-latest", "magistral-medium-latest", "devstral-latest", "codestral-latest"]),
        LLMConfig(id: "groq", name: "Groq", endpoint: "https://api.groq.com/openai/v1", model: "openai/gpt-oss-120b", modelsEndpoint: "https://api.groq.com/openai/v1/models", availableModels: ["openai/gpt-oss-120b", "llama-3.3-70b-versatile", "groq/compound", "openai/gpt-oss-20b"]),
        LLMConfig(id: "cohere", name: "Cohere", endpoint: "https://api.cohere.com/compatibility/v1", model: "command-a-plus-05-2026", modelsEndpoint: "https://api.cohere.com/compatibility/v1/models", availableModels: ["command-a-plus-05-2026", "command-a-reasoning-08-2025", "command-a-vision-07-2025", "command-a-03-2025"]),
        LLMConfig(id: "openrouter", name: "OpenRouter", endpoint: "https://openrouter.ai/api/v1", model: "openrouter/auto", modelsEndpoint: "https://openrouter.ai/api/v1/models", availableModels: ["openrouter/auto", "anthropic/claude-sonnet-4.5", "openai/gpt-5", "google/gemini-2.5-pro"]),
        LLMConfig(id: "together", name: "Together AI", endpoint: "https://api.together.ai/v1", model: "openai/gpt-oss-120b", modelsEndpoint: "https://api.together.ai/v1/models", availableModels: ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "zai-org/GLM-5", "deepseek-ai/DeepSeek-V3.1"]),
        LLMConfig(id: "fireworks", name: "Fireworks AI", endpoint: "https://api.fireworks.ai/inference/v1", model: "accounts/fireworks/models/kimi-k2p5", modelsEndpoint: "https://api.fireworks.ai/inference/v1/models", availableModels: ["accounts/fireworks/models/kimi-k2p5", "accounts/fireworks/models/llama-v3p1-70b-instruct", "accounts/fireworks/models/deepseek-v3"])
    ]
}


// MARK: - Persisted LLM config (no apiKey — secrets live in backend-owned credentials file)

struct PersistedLLMConfig: Codable {
    let id: String
    var name: String
    var endpoint: String?
    var model: String?
    var providerType: String
    var modelsEndpoint: String?
    var availableModels: [String]?
    var temperature: Double
    var maxTokens: Int

    init(from config: LLMConfig) {
        self.id = config.id
        self.name = config.name
        self.endpoint = config.endpoint
        self.model = config.model
        self.providerType = config.providerType
        self.modelsEndpoint = config.modelsEndpoint
        self.availableModels = config.availableModels
        self.temperature = config.temperature
        self.maxTokens = config.maxTokens
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        endpoint = try container.decodeIfPresent(String.self, forKey: .endpoint)
        model = try container.decodeIfPresent(String.self, forKey: .model)
        providerType = try container.decodeIfPresent(String.self, forKey: .providerType) ?? "openai_compatible"
        modelsEndpoint = try container.decodeIfPresent(String.self, forKey: .modelsEndpoint)
        availableModels = try container.decodeIfPresent([String].self, forKey: .availableModels)
        temperature = try container.decodeIfPresent(Double.self, forKey: .temperature) ?? 0.7
        maxTokens = try container.decodeIfPresent(Int.self, forKey: .maxTokens) ?? 8192
    }
}

extension LLMConfig {
    init(from persisted: PersistedLLMConfig) {
        self.id = persisted.id
        self.name = persisted.name
        self.apiKey = nil  // Secrets are not persisted in UserDefaults
        self.endpoint = persisted.endpoint
        self.model = persisted.model
        self.providerType = persisted.providerType
        self.modelsEndpoint = persisted.modelsEndpoint
        self.availableModels = persisted.availableModels
        self.temperature = persisted.temperature
        self.maxTokens = persisted.maxTokens
    }
}
