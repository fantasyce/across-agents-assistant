import Foundation

enum WorkSubmissionMode: Equatable {
    case protectedDelivery
    case directAgent
    case directAgentFallback

    static func resolve(
        automaticDeliveryProtection: Bool,
        orchestratorUnavailable: Bool
    ) -> WorkSubmissionMode {
        guard automaticDeliveryProtection else { return .directAgent }
        return orchestratorUnavailable ? .directAgentFallback : .protectedDelivery
    }

    var usesProtectedDelivery: Bool {
        self != .directAgent
    }

    var usesDirectAgent: Bool {
        self == .directAgent
    }

    var showsOrchestratorUpgradeHint: Bool {
        self == .directAgentFallback
    }
}
