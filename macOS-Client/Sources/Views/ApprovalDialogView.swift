import SwiftUI

// Create a custom AnyCodable type to handle mixed values in JSON dictionaries
enum AnyCodableValue: Codable, Equatable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let x = try? container.decode(Int.self) {
            self = .int(x)
            return
        }
        if let x = try? container.decode(Double.self) {
            self = .double(x)
            return
        }
        if let x = try? container.decode(String.self) {
            self = .string(x)
            return
        }
        if let x = try? container.decode(Bool.self) {
            self = .bool(x)
            return
        }
        if container.decodeNil() {
            self = .null
            return
        }
        throw DecodingError.typeMismatch(AnyCodableValue.self, DecodingError.Context(codingPath: decoder.codingPath, debugDescription: "Wrong type for AnyCodableValue"))
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .int(let x):
            try container.encode(x)
        case .double(let x):
            try container.encode(x)
        case .string(let x):
            try container.encode(x)
        case .bool(let x):
            try container.encode(x)
        case .null:
            try container.encodeNil()
        }
    }

    var stringValue: String {
        switch self {
        case .string(let s): return s
        case .int(let i): return String(i)
        case .double(let d): return String(d)
        case .bool(let b): return String(b)
        case .null: return "null"
        }
    }
}

struct ApprovalRequest: Codable, Equatable {
    var tool_name: String
    var risk_level: String
    var tool_args: [String: AnyCodableValue]?
    var description: String
    var tool_call_id: String?
}

struct ApprovalDialogView: View {
    let request: ApprovalRequest
    let onDecision: (String) -> Void
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences

    private var panelColor: Color { colorScheme == .dark ? Color(hex: "20222a") : Color(hex: "fafbfd") }
    private var boxColor: Color { colorScheme == .dark ? Color.white.opacity(0.055) : .white }
    private var lineColor: Color { colorScheme == .dark ? Color.white.opacity(0.09) : Color.black.opacity(0.10) }
    private var textColor: Color { colorScheme == .dark ? .legacyTextDark : Color(hex: "151820") }
    private var blueColor: Color { colorScheme == .dark ? Color(hex: "4da3ff") : Color(hex: "0a84ff") }

    private var riskColor: Color {
        switch request.risk_level.lowercased() {
        case "high": return .red
        case "medium": return .orange
        case "low": return .green
        default: return .blue
        }
    }

    private var riskTitle: String {
        ToolRiskLevel(rawValue: request.risk_level).title(localeIdentifier: appPreferences.resolvedLocaleIdentifier)
    }

    private var macOSPermissionText: String {
        switch request.tool_name {
        case "take_screenshot_and_ocr", "read_image_text":
            return appPreferences.text("approval.macos.screenRecording")
        case "get_active_browser_url", "get_finder_context":
            return appPreferences.text("approval.macos.accessibility")
        case "create_email_draft", "create_note_draft":
            return appPreferences.text("approval.macos.automation")
        default:
            return appPreferences.text("approval.macos.system")
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 12) {
                Text("!")
                    .font(.system(size: 20, weight: .bold))
                    .foregroundColor(.orange)
                    .frame(width: 40, height: 40)
                    .background(Color.orange.opacity(colorScheme == .dark ? 0.20 : 0.12))
                    .clipShape(RoundedRectangle(cornerRadius: 12))

                Text(appPreferences.text("approval.title"))
                    .font(.system(size: 20, weight: .bold))
                    .foregroundColor(textColor)
                    .lineLimit(1)

                Spacer()
            }

            VStack(spacing: 0) {
                requestRow(
                    label: appPreferences.text("approval.tool"),
                    value: "\(localizedToolName(request.tool_name, preferences: appPreferences))  \(request.tool_name)",
                    valueIsMonospaced: false
                )
                requestRow(label: appPreferences.text("approval.risk"), value: riskTitle)
                requestRow(label: appPreferences.text("approval.macos"), value: macOSPermissionText)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 4)
            .background(boxColor)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(lineColor, lineWidth: 1)
            )

            HStack(spacing: 8) {
                Spacer()
                dialogButton(title: appPreferences.text("approval.deny"), foreground: .red, background: boxColor) {
                    onDecision("reject")
                }
                dialogButton(title: appPreferences.text("approval.allowOnce"), foreground: textColor, background: boxColor) {
                    onDecision("approve")
                }
                dialogButton(title: appPreferences.text("approval.alwaysAllow"), foreground: .white, background: blueColor) {
                    onDecision("always_allow")
                }
            }
        }
        .padding(16)
        .frame(width: 430)
        .background(panelColor)
        .clipShape(RoundedRectangle(cornerRadius: 17))
        .overlay(
            RoundedRectangle(cornerRadius: 17)
                .stroke(lineColor, lineWidth: 1)
        )
        .shadow(color: Color.black.opacity(colorScheme == .dark ? 0.32 : 0.22), radius: 24, x: 0, y: 12)
    }

    private func requestRow(label: String, value: String, valueIsMonospaced: Bool = false) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Text(label)
                .font(.system(size: 12, weight: .bold))
                .foregroundColor(.secondary)
                .frame(width: 56, alignment: .leading)
            Text(value)
                .font(valueIsMonospaced ? .system(size: 12, design: .monospaced) : .system(size: 12, weight: .semibold))
                .foregroundColor(textColor)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(.vertical, 8)
        .overlay(alignment: .bottom) {
            Rectangle()
                .fill(lineColor)
                .frame(height: 1)
                .opacity(label == appPreferences.text("approval.macos") ? 0 : 1)
        }
    }

    private func dialogButton(
        title: String,
        foreground: Color,
        background: Color,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            Text(title)
                .font(.system(size: 13, weight: .bold))
                .foregroundColor(foreground)
                .frame(height: 34)
                .padding(.horizontal, 14)
                .background(background)
                .clipShape(RoundedRectangle(cornerRadius: 9))
                .overlay(
                    RoundedRectangle(cornerRadius: 9)
                        .stroke(background == blueColor ? Color.clear : lineColor, lineWidth: 1)
                )
        }
        .buttonStyle(.plain)
    }
}
