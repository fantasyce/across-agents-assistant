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
}

struct ApprovalDialogView: View {
    let request: ApprovalRequest
    let onDecision: (String) -> Void
    
    private var riskColor: Color {
        switch request.risk_level.lowercased() {
        case "high": return .red
        case "medium": return .orange
        case "low": return .green
        default: return .blue
        }
    }
    
    var body: some View {
        VStack(spacing: 20) {
            // Header
            HStack {
                Image(systemName: "exclamationmark.shield.fill")
                    .foregroundColor(riskColor)
                    .font(.title2)
                Text("Action Requires Approval")
                    .font(.headline)
                Spacer()
            }
            
            // Tool Info
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("Tool:")
                        .fontWeight(.semibold)
                        .foregroundColor(.secondary)
                    Text(request.tool_name)
                        .font(.system(.body, design: .monospaced))
                }
                
                Text(request.description)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.gray.opacity(0.1))
            .cornerRadius(8)
            
            // Arguments
            if let args = request.tool_args, !args.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Parameters:")
                        .fontWeight(.semibold)
                        .foregroundColor(.secondary)
                    
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(args.keys.sorted()), id: \.self) { key in
                            HStack(alignment: .top) {
                                Text("\(key):")
                                    .fontWeight(.medium)
                                    .foregroundColor(.secondary)
                                Text(args[key]?.stringValue ?? "null")
                            }
                            .font(.system(.caption, design: .monospaced))
                        }
                    }
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.black.opacity(0.05))
                    .cornerRadius(6)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            
            // Buttons
            HStack(spacing: 12) {
                Button(action: {
                    onDecision("reject")
                }) {
                    Text("Deny")
                        .fontWeight(.medium)
                        .foregroundColor(.red)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                        .background(Color.red.opacity(0.1))
                        .cornerRadius(6)
                }
                .buttonStyle(.plain)
                
                Button(action: {
                    onDecision("approve")
                }) {
                    Text("Allow Once")
                        .fontWeight(.medium)
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                        .background(riskColor)
                        .cornerRadius(6)
                }
                .buttonStyle(.plain)
                
                Button(action: {
                    onDecision("always_allow")
                }) {
                    Text("Always Allow")
                        .fontWeight(.medium)
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                        .background(Color.blue)
                        .cornerRadius(6)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(24)
        .frame(width: 400)
        .background(VisualEffectView())
        .cornerRadius(16)
        .shadow(color: Color.black.opacity(0.2), radius: 20, x: 0, y: 10)
    }
}
