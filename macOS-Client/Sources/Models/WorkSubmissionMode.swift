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
        self == .protectedDelivery
    }

    var usesDirectAgent: Bool {
        !usesProtectedDelivery
    }

    var showsOrchestratorUpgradeHint: Bool {
        self == .directAgentFallback
    }
}
