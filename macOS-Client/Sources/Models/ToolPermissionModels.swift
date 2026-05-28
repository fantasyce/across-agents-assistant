import Foundation

enum ToolPermissionScope: String, Equatable {
    case local
    case mcp
}

enum ToolPermissionState: String, CaseIterable, Equatable {
    case alwaysAllow = "always_allow"
    case askEveryTime = "ask"
    case unavailable = "unavailable"

    func title(localeIdentifier: String) -> String {
        switch self {
        case .alwaysAllow:
            return AppPreferences.localizedString("tools.permission.alwaysAllow", localeIdentifier: localeIdentifier)
        case .askEveryTime:
            return AppPreferences.localizedString("tools.permission.askEveryTime", localeIdentifier: localeIdentifier)
        case .unavailable:
            return AppPreferences.localizedString("tools.permission.unavailable", localeIdentifier: localeIdentifier)
        }
    }
}

enum ToolRiskLevel: String, Equatable {
    case low
    case medium
    case high
    case unknown

    init(rawValue: String?) {
        switch rawValue?.lowercased() {
        case "low": self = .low
        case "medium": self = .medium
        case "high": self = .high
        default: self = .unknown
        }
    }

    func title(localeIdentifier: String) -> String {
        switch self {
        case .low:
            return AppPreferences.localizedString("tools.risk.low", localeIdentifier: localeIdentifier)
        case .medium:
            return AppPreferences.localizedString("tools.risk.medium", localeIdentifier: localeIdentifier)
        case .high:
            return AppPreferences.localizedString("tools.risk.high", localeIdentifier: localeIdentifier)
        case .unknown:
            return AppPreferences.localizedString("tools.risk.unknown", localeIdentifier: localeIdentifier)
        }
    }
}

struct ToolPermissionSchema: Equatable {
    let name: String
    let description: String
    let riskLevel: ToolRiskLevel
    let scope: ToolPermissionScope

    init(name: String, description: String, riskLevel: String, scope: ToolPermissionScope? = nil) {
        self.name = name
        self.description = description
        self.riskLevel = ToolRiskLevel(rawValue: riskLevel)
        self.scope = scope ?? (name.contains("__") ? .mcp : .local)
    }
}

struct ToolPermissionCardModel: Identifiable, Equatable {
    let id: String
    let name: String
    let description: String
    let riskLevel: ToolRiskLevel
    let scope: ToolPermissionScope
    let state: ToolPermissionState
    let isRuntimeAvailable: Bool
}

struct ToolPermissionCardRhythm {
    struct Metrics: Equatable {
        let cardHeight: Double
        let descriptionHeight: Double
        let titleBlockHeight: Double
        let headerToDescriptionSpacing: Double
        let descriptionToRiskSpacing: Double
    }

    static func metrics(localeIdentifier: String) -> Metrics {
        Metrics(
            cardHeight: 130,
            descriptionHeight: 30,
            titleBlockHeight: 34,
            headerToDescriptionSpacing: 12,
            descriptionToRiskSpacing: 3
        )
    }
}

enum ToolPermissionVisualStyle {
    struct PermissionChrome: Equatable {
        let backgroundOpacity: Double
        let borderOpacity: Double
        let foregroundOpacity: Double
    }

    static func permissionChrome(for state: ToolPermissionState) -> PermissionChrome {
        switch state {
        case .alwaysAllow:
            return PermissionChrome(backgroundOpacity: 0.13, borderOpacity: 0.25, foregroundOpacity: 1.0)
        case .askEveryTime:
            return PermissionChrome(backgroundOpacity: 0.065, borderOpacity: 0.14, foregroundOpacity: 0.9)
        case .unavailable:
            return PermissionChrome(backgroundOpacity: 0.04, borderOpacity: 0.10, foregroundOpacity: 0.78)
        }
    }
}

enum ToolPermissionCatalog {
    static func makeCards(
        schemas: [ToolPermissionSchema],
        permissionTypes: [String: String],
        enabledMCPServerIds: Set<String>
    ) -> [ToolPermissionCardModel] {
        let schemaNames = Set(schemas.map(\.name))
        var mergedByName: [String: ToolPermissionSchema] = [:]

        for schema in schemas {
            mergedByName[schema.name] = schema
        }

        return mergedByName.values
            .map { schema in
                let runtimeAvailable = schemaNames.contains(schema.name)
                return ToolPermissionCardModel(
                    id: schema.name,
                    name: schema.name,
                    description: schema.description,
                    riskLevel: schema.riskLevel,
                    scope: schema.scope,
                    state: state(
                        for: schema,
                        permissionType: permissionTypes[schema.name],
                        isRuntimeAvailable: runtimeAvailable
                    ),
                    isRuntimeAvailable: runtimeAvailable
                )
            }
            .sorted { lhs, rhs in
                if lhs.scope != rhs.scope { return lhs.scope == .local }
                return lhs.id.localizedStandardCompare(rhs.id) == .orderedAscending
            }
    }

    private static func state(
        for schema: ToolPermissionSchema,
        permissionType: String?,
        isRuntimeAvailable: Bool
    ) -> ToolPermissionState {
        let normalized = permissionType?.lowercased()
        if normalized == ToolPermissionState.unavailable.rawValue {
            return .unavailable
        }
        if normalized == ToolPermissionState.alwaysAllow.rawValue {
            return .alwaysAllow
        }
        if normalized == ToolPermissionState.askEveryTime.rawValue {
            return .askEveryTime
        }
        if schema.scope == .mcp && !isRuntimeAvailable {
            return .unavailable
        }
        return .askEveryTime
    }

    static func serverId(for toolName: String) -> String {
        toolName.components(separatedBy: "__").first ?? ""
    }
}
