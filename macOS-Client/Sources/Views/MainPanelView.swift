import SwiftUI

// Helper to create Color from hex
extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3: // RGB (12-bit)
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6: // RGB (24-bit)
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8: // ARGB (32-bit)
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (255, 0, 0, 0)
        }
        self.init(.sRGB, red: Double(r) / 255, green: Double(g) / 255, blue:  Double(b) / 255, opacity: Double(a) / 255)
    }
}

// Define custom colors to match the legacy UI
extension Color {
    static let legacyBgLight = Color(red: 249/255, green: 249/255, blue: 249/255)
    static let legacyBgDark = Color(red: 28/255, green: 28/255, blue: 30/255)
    
    static let legacySidebarLight = Color(white: 1.0)
    static let legacySidebarDark = Color(red: 28/255, green: 28/255, blue: 30/255)
    
    static let legacyTextLight = Color(red: 29/255, green: 29/255, blue: 31/255)
    static let legacyTextDark = Color(red: 245/255, green: 245/255, blue: 247/255)
    
    static let legacyAccentLight = Color(red: 203/255, green: 166/255, blue: 240/255) // #CBA6F0
    static let legacyAccentDark = Color(red: 181/255, green: 138/255, blue: 227/255) // #B58AE3
    
    static let legacyUserMsgBgLight = Color(red: 235/255, green: 227/255, blue: 245/255) // #EBE3F5
    static let legacyUserMsgBgDark = Color(red: 155/255, green: 130/255, blue: 198/255) // #9B82C6
}

struct CustomTrafficLights: View {
    @State private var isHovered = false
    
    var body: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(Color(hex: isHovered ? "#FF5F56" : "#FFBFBB"))
                .frame(width: 12, height: 12)
                .onTapGesture {
                    NSApplication.shared.keyWindow?.close()
                }
            
            Circle()
                .fill(Color(hex: isHovered ? "#FFBD2E" : "#FFE4AB"))
                .frame(width: 12, height: 12)
                .onTapGesture {
                    NSApplication.shared.keyWindow?.miniaturize(nil)
                }
            
            Circle()
                .fill(Color(hex: isHovered ? "#27C93F" : "#A8E9B2"))
                .frame(width: 12, height: 12)
                .onTapGesture {
                    NSApplication.shared.keyWindow?.zoom(nil)
                }
        }
        .onHover { hovering in
            isHovered = hovering
        }
    }
}

struct FileTreeView: View {
    let item: FileItemModel
    let depth: Int
    @State private var isExpanded: Bool
    
    init(item: FileItemModel, depth: Int = 0) {
        self.item = item
        self.depth = depth
        _isExpanded = State(initialValue: item.isExpanded)
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 6) {
                Spacer().frame(width: CGFloat(depth * 15))
                
                if item.isFolder {
                    Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                        .frame(width: 12)
                    
                    Image(systemName: "folder.fill")
                        .foregroundColor(Color(hex: "#5AC8FA"))
                        .font(.system(size: 12))
                } else {
                    Spacer().frame(width: 12)
                    
                    Image(systemName: "doc.text")
                        .foregroundColor(.secondary)
                        .font(.system(size: 12))
                }
                
                Text(item.name)
                    .font(.system(size: 12))
                    .foregroundColor(Color.primary.opacity(0.8))
                
                Spacer()
            }
            .padding(.vertical, 6)
            .padding(.horizontal, 16)
            .contentShape(Rectangle())
            .onTapGesture {
                if item.isFolder {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        isExpanded.toggle()
                    }
                }
            }
            
            if item.isFolder && isExpanded, let children = item.children {
                ForEach(children) { child in
                    FileTreeView(item: child, depth: depth + 1)
                }
            }
        }
    }
}

struct MainPanelView: View {
    @ObservedObject var viewModel: SessionViewModel
    @Environment(\.colorScheme) var colorScheme
    
    // Dynamic color helpers based on color scheme
    private var bgColor: Color { colorScheme == .dark ? .legacyBgDark : .legacyBgLight }
    private var sidebarBgColor: Color { colorScheme == .dark ? .legacySidebarDark : .legacySidebarLight }
    private var textColor: Color { colorScheme == .dark ? .legacyTextDark : .legacyTextLight }
    private var accentColor: Color { colorScheme == .dark ? .legacyAccentDark : .legacyAccentLight }
    private var userMsgBgColor: Color { colorScheme == .dark ? .legacyUserMsgBgDark : .legacyUserMsgBgLight }
    private var userMsgTextColor: Color { colorScheme == .dark ? .white : .black }
    private var agentMsgTextColor: Color { colorScheme == .dark ? .white : .black }
    
    // State for interactive buttons
    @State private var isContinuousMode = false
    @State private var isMuted = false
    
    var body: some View {
        HStack(spacing: 0) {
            // LEFT SIDEBAR: File Explorer Placeholder
            VStack(spacing: 0) {
                // Explorer Header (matches 56px height)
                HStack {
                    // Custom Traffic Lights
                    CustomTrafficLights()
                    
                    Spacer()
                    
                    HStack(spacing: 12) {
                        Button(action: {}) {
                            Image(systemName: "arrow.up.right.and.arrow.down.left.rectangle")
                        }
                        .buttonStyle(.plain)
                        
                        Button(action: {}) {
                            Image(systemName: "arrow.clockwise")
                        }
                        .buttonStyle(.plain)
                        
                        Button(action: {}) {
                            Image(systemName: "eye.slash")
                        }
                        .buttonStyle(.plain)
                    }
                    .font(.system(size: 14))
                    .foregroundColor(.secondary)
                }
                .padding(.horizontal, 16)
                .frame(height: 56)
                
                Divider().opacity(0.5)
                
                // Explorer Content
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        ForEach(viewModel.fileTree) { node in
                            FileTreeView(item: node)
                        }
                    }
                    .padding(.top, 8)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(width: 250)
            .frame(maxHeight: .infinity)
            .background(sidebarBgColor)
            
            Divider().opacity(0.5)
            
            // CENTER: Main Chat Area
            VStack(spacing: 0) {
                // Header
                HStack {
                    // Show currently selected agent name
                    if let agent = viewModel.agents.first(where: { $0.id == viewModel.selectedAgentId }) {
                        Text(agent.name)
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(textColor)
                    }
                    
                    Spacer()
                    
                    // Header Actions
                    HStack(spacing: 16) {
                        Button(action: {
                            isContinuousMode.toggle()
                        }) {
                            Image(systemName: isContinuousMode ? "waveform.circle.fill" : "waveform")
                                .foregroundColor(isContinuousMode ? .blue : .secondary)
                        }
                        .buttonStyle(.plain)
                        
                        Button(action: {
                            isMuted.toggle()
                        }) {
                            Image(systemName: isMuted ? "speaker.slash.fill" : "speaker.wave.2")
                                .foregroundColor(isMuted ? .red : .secondary)
                        }
                        .buttonStyle(.plain)
                        
                        Button(action: {}) {
                            Image(systemName: "gearshape")
                                .foregroundColor(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                    .font(.system(size: 14))
                }
                .padding(.horizontal, 20)
                .frame(height: 56)
                .background(bgColor.opacity(0.8)) // For blur effect later
                
                Divider().opacity(0.5)
                
                // Messages List
                ScrollView {
                    ScrollViewReader { proxy in
                        LazyVStack(alignment: .leading, spacing: 16) {
                            ForEach(viewModel.messages) { message in
                                LegacyMessageBubble(
                                    message: message,
                                    userBgColor: userMsgBgColor,
                                    userTextColor: userMsgTextColor,
                                    agentTextColor: agentMsgTextColor
                                )
                                .id(message.id)
                            }
                            
                            if viewModel.isProcessing {
                                HStack {
                                    ProgressView()
                                        .scaleEffect(0.6)
                                    Text("思考中...")
                                        .font(.system(size: 11))
                                        .foregroundColor(.secondary)
                                    Spacer()
                                }
                                .padding(.horizontal, 24)
                                .id("processing")
                            }
                        }
                        .padding(EdgeInsets(top: 8, leading: 24, bottom: 24, trailing: 24))
                        .onChange(of: viewModel.messages.count) { _ in
                            if let lastId = viewModel.messages.last?.id {
                                withAnimation {
                                    proxy.scrollTo(lastId, anchor: .bottom)
                                }
                            }
                        }
                        .onChange(of: viewModel.isProcessing) { processing in
                            if processing {
                                withAnimation {
                                    proxy.scrollTo("processing", anchor: .bottom)
                                }
                            }
                        }
                    }
                }
                
                // Input Area
                HStack(alignment: .bottom, spacing: 12) {
                    // Screenshot Button
                    Button(action: {
                        viewModel.requestManualScreenshot()
                    }) {
                        Image(systemName: "camera.viewfinder")
                            .font(.system(size: 16))
                            .foregroundColor(.secondary)
                            .frame(width: 32, height: 32)
                            .background(Color.black.opacity(0.05))
                            .cornerRadius(6)
                    }
                    .buttonStyle(.plain)
                    
                    // Input Wrapper
                    HStack {
                        TextField("Ask anything...", text: $viewModel.inputText, axis: .vertical)
                            .textFieldStyle(.plain)
                            .font(.system(size: 13))
                            .foregroundColor(textColor)
                            .lineLimit(1...5)
                            .disabled(viewModel.pendingApproval != nil)
                            .onSubmit {
                                if viewModel.pendingApproval == nil {
                                    submit()
                                }
                            }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .background(Color.black.opacity(0.05))
                    .cornerRadius(14)
                    
                    Button(action: submit) {
                        Image(systemName: "paperplane.fill")
                            .font(.system(size: 14))
                            .foregroundColor(viewModel.inputText.isEmpty || viewModel.pendingApproval != nil ? .secondary : accentColor)
                            .frame(width: 32, height: 32)
                            .background(Color.black.opacity(0.05))
                            .cornerRadius(6)
                    }
                    .buttonStyle(.plain)
                    .disabled(viewModel.inputText.isEmpty || viewModel.pendingApproval != nil)
                }
                .padding(EdgeInsets(top: 12, leading: 24, bottom: 16, trailing: 24))
                .background(bgColor)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(bgColor)
            
            Divider().opacity(0.5)
            
            // RIGHT SIDEBAR: Agent Icons Placeholder
            VStack(spacing: 20) {
                ForEach(viewModel.agents) { agent in
                    let isActive = agent.id == viewModel.selectedAgentId
                    
                    Button(action: {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            viewModel.selectedAgentId = agent.id
                        }
                    }) {
                        Circle()
                            .fill(isActive ? Color(hex: agent.color) : Color.gray.opacity(0.2))
                            .frame(width: 40, height: 40)
                            .overlay(
                                Text(agent.initial)
                                    .font(.system(size: 16, weight: .bold))
                                    .foregroundColor(isActive ? .white : .gray)
                            )
                            .overlay(
                                Circle()
                                    .stroke(isActive ? Color(hex: agent.color).opacity(0.5) : Color.clear, lineWidth: 3)
                                    .scaleEffect(isActive ? 1.15 : 1.0)
                            )
                    }
                    .buttonStyle(.plain)
                }
                
                Spacer()
            }
            .padding(.top, 20)
            .frame(width: 80)
            .frame(maxHeight: .infinity)
            .background(sidebarBgColor)
        }
        .frame(width: 900, height: 650)
        .background(VisualEffectView().ignoresSafeArea())
        .cornerRadius(10) // Match legacy global border radius
        .overlay(
            Group {
                if let request = viewModel.pendingApproval {
                    ZStack {
                        Color.black.opacity(0.4).ignoresSafeArea()
                        ApprovalDialogView(request: request) { decision in
                            viewModel.submitDecision(decision: decision)
                        }
                    }
                }
                
                if viewModel.showPermissionAlert {
                    ZStack {
                        Color.black.opacity(0.4).ignoresSafeArea()
                        VStack(spacing: 20) {
                            Image(systemName: "lock.shield.fill")
                                .font(.system(size: 40))
                                .foregroundColor(.orange)
                            
                            Text("需要辅助功能权限")
                                .font(.headline)
                            
                            Text("小助手需要“辅助功能”权限才能读取您的屏幕内容（如浏览器网址或 Finder 选中的文件）。\n\n请在“系统设置”中勾选本应用，然后重试。")
                                .font(.subheadline)
                                .multilineTextAlignment(.center)
                                .padding(.horizontal)
                            
                            HStack(spacing: 16) {
                                Button("取消") {
                                    viewModel.showPermissionAlert = false
                                    viewModel.submitDecision(decision: "reject")
                                }
                                .buttonStyle(.plain)
                                .padding(.horizontal, 20)
                                .padding(.vertical, 8)
                                .background(Color.gray.opacity(0.2))
                                .cornerRadius(8)
                                
                                Button("前往系统设置") {
                                    viewModel.openAccessibilitySettings()
                                }
                                .buttonStyle(.plain)
                                .padding(.horizontal, 20)
                                .padding(.vertical, 8)
                                .background(Color.blue)
                                .foregroundColor(.white)
                                .cornerRadius(8)
                            }
                        }
                        .padding(30)
                        .frame(width: 350)
                        .background(VisualEffectView())
                        .cornerRadius(16)
                        .shadow(color: Color.black.opacity(0.2), radius: 20, x: 0, y: 10)
                    }
                }
            }
        )
    }
    
    private func submit() {
        let text = viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        if !text.isEmpty {
            viewModel.submitMessage(text)
            viewModel.inputText = ""
        }
    }
}

struct LegacyMessageBubble: View {
    let message: Message
    let userBgColor: Color
    let userTextColor: Color
    let agentTextColor: Color
    
    var body: some View {
        HStack {
            if message.isUser {
                Spacer(minLength: 40)
            }
            
            Text(message.content)
                .textSelection(.enabled)
                .font(.system(size: 13))
                .lineSpacing(4)
                .padding(.horizontal, message.isUser ? 12 : 0)
                .padding(.vertical, message.isUser ? 8 : 4)
                .background(message.isUser ? userBgColor : Color.clear)
                .foregroundColor(message.isUser ? userTextColor : agentTextColor)
                // Match the 12px border radius, with bottom-right square for user messages
                .clipShape(
                    CustomRoundedCorners(
                        topLeading: message.isUser ? 12 : 0,
                        topTrailing: message.isUser ? 12 : 0,
                        bottomLeading: message.isUser ? 12 : 0,
                        bottomTrailing: 0
                    )
                )
            
            if !message.isUser {
                Spacer(minLength: 40)
            }
        }
    }
}

// 1. Define custom Shape for macOS compatible specific corner radius
struct CustomRoundedCorners: Shape {
    var topLeading: CGFloat = 0.0
    var topTrailing: CGFloat = 0.0
    var bottomLeading: CGFloat = 0.0
    var bottomTrailing: CGFloat = 0.0

    func path(in rect: CGRect) -> Path {
        var path = Path()

        let w = rect.size.width
        let h = rect.size.height

        let tr = min(min(self.topTrailing, h/2), w/2)
        let tl = min(min(self.topLeading, h/2), w/2)
        let bl = min(min(self.bottomLeading, h/2), w/2)
        let br = min(min(self.bottomTrailing, h/2), w/2)

        // Top left
        path.move(to: CGPoint(x: rect.minX + tl, y: rect.minY))

        // Top right
        path.addLine(to: CGPoint(x: rect.maxX - tr, y: rect.minY))
        path.addArc(center: CGPoint(x: rect.maxX - tr, y: rect.minY + tr), 
                    radius: tr, startAngle: Angle(degrees: -90), endAngle: Angle(degrees: 0), clockwise: false)

        // Bottom right
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.maxY - br))
        path.addArc(center: CGPoint(x: rect.maxX - br, y: rect.maxY - br), 
                    radius: br, startAngle: Angle(degrees: 0), endAngle: Angle(degrees: 90), clockwise: false)

        // Bottom left
        path.addLine(to: CGPoint(x: rect.minX + bl, y: rect.maxY))
        path.addArc(center: CGPoint(x: rect.minX + bl, y: rect.maxY - bl), 
                    radius: bl, startAngle: Angle(degrees: 90), endAngle: Angle(degrees: 180), clockwise: false)

        // Top left again
        path.addLine(to: CGPoint(x: rect.minX, y: rect.minY + tl))
        path.addArc(center: CGPoint(x: rect.minX + tl, y: rect.minY + tl), 
                    radius: tl, startAngle: Angle(degrees: 180), endAngle: Angle(degrees: 270), clockwise: false)

        path.closeSubpath()
        return path
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
