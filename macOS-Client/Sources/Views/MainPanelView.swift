import SwiftUI

struct MainPanelView: View {
    @ObservedObject var viewModel: SessionViewModel
    @State private var inputText: String = ""
    
    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("Across Agents Copilot")
                    .font(.headline)
                    .foregroundColor(.secondary)
                Spacer()
                if viewModel.isProcessing {
                    ProgressView()
                        .scaleEffect(0.5)
                        .frame(width: 16, height: 16)
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 12)
            .background(Color.black.opacity(0.05))
            
            Divider()
            
            // Messages List
            ScrollView {
                ScrollViewReader { proxy in
                    LazyVStack(alignment: .leading, spacing: 16) {
                        ForEach(viewModel.messages) { message in
                            MessageBubble(message: message)
                                .id(message.id)
                        }
                    }
                    .padding()
                    .onChange(of: viewModel.messages.count) { _ in
                        if let lastId = viewModel.messages.last?.id {
                            withAnimation {
                                proxy.scrollTo(lastId, anchor: .bottom)
                            }
                        }
                    }
                }
            }
            
            Divider()
            
            // Input Area
            HStack(alignment: .bottom, spacing: 12) {
                TextField("Ask anything...", text: $inputText, axis: .vertical)
                    .textFieldStyle(.plain)
                    .padding(10)
                    .background(Color.gray.opacity(0.1))
                    .cornerRadius(8)
                    .lineLimit(1...5)
                    .disabled(viewModel.pendingApproval != nil)
                    .onSubmit {
                        if viewModel.pendingApproval == nil {
                            submit()
                        }
                    }
                
                Button(action: submit) {
                    Image(systemName: "paperplane.fill")
                        .font(.system(size: 16))
                        .foregroundColor(inputText.isEmpty || viewModel.pendingApproval != nil ? .gray : .blue)
                        .padding(10)
                        .background(Color.gray.opacity(0.1))
                        .clipShape(Circle())
                }
                .buttonStyle(.plain)
                .disabled(inputText.isEmpty || viewModel.pendingApproval != nil)
            }
            .padding()
        }
        .frame(width: 420, height: 650)
        .background(VisualEffectView().ignoresSafeArea())
        .overlay(
            Group {
                if let request = viewModel.pendingApproval {
                    ZStack {
                        Color.black.opacity(0.4).ignoresSafeArea()
                        ApprovalDialogView(request: request) { approved in
                            viewModel.submitDecision(approved: approved)
                        }
                    }
                }
            }
        )
    }
    
    private func submit() {
        let text = inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !text.isEmpty {
            viewModel.submitMessage(text)
            inputText = ""
        }
    }
}

struct MessageBubble: View {
    let message: Message
    
    var body: some View {
        HStack {
            if message.isUser {
                Spacer(minLength: 40)
            }
            
            Text(message.content)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(message.isUser ? Color.blue.opacity(0.8) : Color.gray.opacity(0.2))
                .foregroundColor(message.isUser ? .white : .primary)
                .cornerRadius(16)
            
            if !message.isUser {
                Spacer(minLength: 40)
            }
        }
    }
}

struct VisualEffectView: NSViewRepresentable {
    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = .popover
        view.blendingMode = .behindWindow
        view.state = .active
        return view
    }
    
    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {}
}
