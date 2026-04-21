import SwiftUI

struct ApprovalRequest: Codable, Equatable {
    var tool_name: String
    var risk_level: String
    var tool_args: [String: String]?
    var description: String
}

struct ApprovalDialogView: View {
    var request: ApprovalRequest
    var onDecision: (Bool) -> Void
    
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Image(systemName: request.risk_level == "high" ? "exclamationmark.triangle.fill" : "shield.checkerboard")
                    .foregroundColor(request.risk_level == "high" ? .red : (request.risk_level == "medium" ? .orange : .green))
                    .font(.title2)
                
                Text("需要您的授权")
                    .font(.headline)
            }
            
            Text("助手申请执行以下操作：")
                .font(.subheadline)
                .foregroundColor(.secondary)
            
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("动作:")
                        .bold()
                        .frame(width: 50, alignment: .leading)
                    Text(request.tool_name)
                        .font(.system(.body, design: .monospaced))
                }
                HStack {
                    Text("说明:")
                        .bold()
                        .frame(width: 50, alignment: .leading)
                    Text(request.description)
                }
                
                if let args = request.tool_args, !args.isEmpty {
                    Text("参数:")
                        .bold()
                        .padding(.top, 4)
                    
                    VStack(alignment: .leading, spacing: 4) {
                        ForEach(Array(args.keys.sorted()), id: \.self) { key in
                            HStack(alignment: .top) {
                                Text("\(key):")
                                    .foregroundColor(.secondary)
                                Text(args[key] ?? "")
                                    .font(.system(.body, design: .monospaced))
                            }
                        }
                    }
                    .padding(8)
                    .background(Color.gray.opacity(0.1))
                    .cornerRadius(6)
                }
            }
            .padding()
            .background(Color(NSColor.windowBackgroundColor))
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.gray.opacity(0.2), lineWidth: 1)
            )
            
            HStack(spacing: 12) {
                Spacer()
                Button("拒绝") {
                    onDecision(false)
                }
                .keyboardShortcut(.cancelAction)
                
                Button("允许执行") {
                    onDecision(true)
                }
                .buttonStyle(.borderedProminent)
                .tint(request.risk_level == "high" ? .red : .blue)
                .keyboardShortcut(.defaultAction)
            }
            .padding(.top, 8)
        }
        .padding()
        .frame(width: 380)
        .background(VisualEffectView().ignoresSafeArea())
        .cornerRadius(12)
        .shadow(color: Color.black.opacity(0.2), radius: 10, x: 0, y: 4)
    }
}
