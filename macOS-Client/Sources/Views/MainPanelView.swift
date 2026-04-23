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
    
    static let legacyTreeSelectedLight = Color(red: 203/255, green: 166/255, blue: 240/255, opacity: 0.25)
    static let legacyTreeSelectedDark = Color(red: 181/255, green: 138/255, blue: 227/255, opacity: 0.25)
}

struct CustomTrafficLights: View {
    @State private var isHovered = false
    
    var body: some View {
        HStack(spacing: 8) {
            TrafficLightButton(colorHex: "#FF5F56", defaultHex: "#FFBFBB", iconName: "xmark", isGroupHovered: isHovered) {
                NSApplication.shared.keyWindow?.close()
            }
            TrafficLightButton(colorHex: "#FFBD2E", defaultHex: "#FFE4AB", iconName: "minus", isGroupHovered: isHovered) {
                NSApplication.shared.keyWindow?.miniaturize(nil)
            }
            TrafficLightButton(colorHex: "#27C93F", defaultHex: "#A8E9B2", iconName: "arrow.up.left.and.arrow.down.right", isGroupHovered: isHovered) {
                NSApplication.shared.keyWindow?.zoom(nil)
            }
        }
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.1)) {
                isHovered = hovering
            }
        }
    }
}

struct TrafficLightButton: View {
    let colorHex: String
    let defaultHex: String
    let iconName: String
    let isGroupHovered: Bool
    let action: () -> Void
    
    @State private var isPressed = false
    @State private var isSelfHovered = false
    
    var body: some View {
        RoundedRectangle(cornerRadius: 3)
            .fill(Color(hex: isSelfHovered ? colorHex : defaultHex))
            .frame(width: 12, height: 12)
            .overlay(
                Image(systemName: iconName)
                    .font(.system(size: 8, weight: .bold))
                    .foregroundColor(.black.opacity(isGroupHovered ? 0.5 : 0))
            )
            .scaleEffect(isPressed ? 0.9 : 1.0)
            .onHover { hovering in
                isSelfHovered = hovering
            }
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { _ in isPressed = true }
                    .onEnded { _ in 
                        isPressed = false
                        action()
                    }
            )
    }
}

struct FileTreeView: View {
    let item: FileItemModel
    let depth: Int
    @ObservedObject var viewModel: SessionViewModel
    @Environment(\.colorScheme) var colorScheme
    
    init(item: FileItemModel, depth: Int = 0, viewModel: SessionViewModel) {
        self.item = item
        self.depth = depth
        self.viewModel = viewModel
    }
    
    var body: some View {
        let isSelected = item.id == viewModel.selectedFileId
        let highlightColor = colorScheme == .dark ? Color.legacyTreeSelectedDark : Color.legacyTreeSelectedLight
        
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 6) {
                Spacer().frame(width: CGFloat(depth * 8))
                
                if item.isFolder {
                    Image(systemName: item.isExpanded ? "chevron.down" : "chevron.right")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                        .frame(width: 12)
                    
                    SVGIconView(name: item.isExpanded ? "icon.14.explorer.folder.open" : "icon.14.explorer.folder.closed", size: 14)
                } else {
                    Spacer().frame(width: 12)
                    
                    SVGIconView(name: getFileIconName(fileName: item.name), size: 14)
                }
                
                Text(item.name)
                    .font(.system(size: 12))
                    .foregroundColor(Color.primary.opacity(0.8))
                    .fixedSize(horizontal: true, vertical: false)
                
                Spacer()
            }
            .padding(.vertical, 4)
            .padding(.horizontal, 8)
            .background(isSelected ? highlightColor : Color.clear)
            .cornerRadius(4)
            .padding(.horizontal, 8)
            .contentShape(Rectangle())
            .onTapGesture {
                viewModel.selectedFileId = item.id
                if item.isFolder {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        viewModel.toggleFolderExpansion(for: item)
                    }
                }
            }
            
            if item.isFolder && item.isExpanded, let children = item.children {
                ForEach(children) { child in
                    FileTreeView(item: child, depth: depth + 1, viewModel: viewModel)
                }
            }
        }
        .onDrag {
            // Provide the actual file URL for dragging.
            return NSItemProvider(object: NSURL(fileURLWithPath: item.path))
        }
    }
}

struct WindowDragView: NSViewRepresentable {
    func makeNSView(context: Context) -> DraggableNSView {
        let view = DraggableNSView()
        return view
    }
    
    func updateNSView(_ nsView: DraggableNSView, context: Context) {}
}

class DraggableNSView: NSView {
    override func mouseDown(with event: NSEvent) {
        if event.clickCount == 2 {
            self.window?.zoom(nil)
        } else {
            self.window?.performDrag(with: event)
        }
    }
}

struct SVGIconView: View {
    let name: String
    var size: CGFloat = 14
    
    @State private var nsImage: NSImage?
    
    var body: some View {
        Group {
            if let img = nsImage {
                Image(nsImage: img)
                    .resizable()
                    .scaledToFit()
                    .frame(width: size, height: size)
            } else {
                Image(systemName: "doc")
                    .resizable()
                    .scaledToFit()
                    .frame(width: size, height: size)
                    .foregroundColor(.secondary)
            }
        }
        .onAppear(perform: loadImage)
    }
    
    private func loadImage() {
        if let url = Bundle.module.url(forResource: name, withExtension: "svg", subdirectory: "Assets/icons") {
            if let data = try? Data(contentsOf: url) {
                self.nsImage = NSImage(data: data)
            }
        } else if let url = Bundle.main.url(forResource: name, withExtension: "svg", subdirectory: "Assets/icons") {
            if let data = try? Data(contentsOf: url) {
                self.nsImage = NSImage(data: data)
            }
        }
    }
}

func getFileIconName(fileName: String) -> String {
    let lowerName = fileName.lowercased()
    
    // Check specific file names
    if lowerName == "readme.md" || lowerName == "readme" { return "icon.14.explorer.file.readme" }
    if lowerName == "package.json" { return "icon.14.explorer.npm" }
    if lowerName == "dockerfile" { return "icon.14.explorer.type.docker" }
    
    // Check extensions
    let ext = URL(fileURLWithPath: fileName).pathExtension.lowercased()
    switch ext {
    case "js": return "icon.14.explorer.lang.js"
    case "ts": return "icon.14.explorer.lang.ts"
    case "py": return "icon.14.explorer.lang.python"
    case "json": return "icon.14.explorer.lang.json"
    case "md": return "icon.14.explorer.type.markdown"
    case "swift": return "icon.14.explorer.type.class"
    case "cpp", "cc", "cxx": return "icon.14.explorer.lang.c++"
    case "c": return "icon.14.explorer.lang.c"
    case "h", "hpp": return "icon.14.explorer.type.h"
    case "go": return "icon.14.explorer.lang.go"
    case "rs": return "icon.14.explorer.lang.rs"
    case "html", "htm": return "icon.14.explorer.lang.html"
    case "css": return "icon.14.explorer.lang.css"
    case "vue": return "icon.14.explorer.lang.vue"
    case "txt": return "icon.14.explorer.type.txt"
    case "png", "jpg", "jpeg", "gif", "ico": return "icon.14.explorer.type.image"
    case "svg": return "icon.14.explorer.type.svg"
    case "sh", "bash", "zsh": return "icon.14.explorer.type.bash"
    case "pdf": return "icon.14.explorer.type.pdf"
    case "docx", "doc": return "icon.14.explorer.type.docx"
    case "xlsx", "xls", "csv": return "icon.14.explorer.type.xlsx"
    case "yaml", "yml": return "icon.14.explorer.lang.yaml"
    case "xml": return "icon.14.explorer.lang.xml"
    case "java": return "icon.14.explorer.lang.java"
    default: return "icon.14.explorer.file"
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
    @State private var showSettings = false
    @AppStorage("sidebarWidth") private var sidebarWidth: Double = 250
    @State private var dragStartWidth: Double = 0
    
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
                        Button(action: {
                            withAnimation(.easeInOut(duration: 0.2)) {
                                viewModel.collapseAllFolders()
                            }
                        }) {
                            Image(systemName: "arrow.up.right.and.arrow.down.left.rectangle")
                        }
                        .buttonStyle(.plain)
                        .help("Collapse All")
                        
                        Button(action: {
                            withAnimation(.easeInOut(duration: 0.2)) {
                                viewModel.refreshFileTree()
                            }
                        }) {
                            Image(systemName: "arrow.clockwise")
                        }
                        .buttonStyle(.plain)
                        .help("Refresh")
                        
                        Button(action: {
                            viewModel.toggleHiddenFiles()
                        }) {
                            Image(systemName: viewModel.showHiddenFiles ? "eye" : "eye.slash")
                        }
                        .buttonStyle(.plain)
                        .help(viewModel.showHiddenFiles ? "Hide Hidden Files" : "Show Hidden Files")
                    }
                    .font(.system(size: 14))
                    .foregroundColor(.secondary)
                }
                .padding(.horizontal, 16)
                .frame(height: 56)
                .background(WindowDragView())
                
                Divider().opacity(0.5)
                
                // Explorer Content
                GeometryReader { geo in
                    ScrollView([.vertical, .horizontal], showsIndicators: false) {
                        VStack(alignment: .leading, spacing: 0) {
                            ForEach(viewModel.fileTree) { node in
                                FileTreeView(item: node, viewModel: viewModel)
                            }
                        }
                        .padding(.top, 8)
                        .frame(minWidth: max(CGFloat(sidebarWidth), geo.size.width), minHeight: geo.size.height, alignment: .topLeading)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .frame(width: CGFloat(sidebarWidth))
            .frame(maxHeight: .infinity)
            .background(sidebarBgColor)
            
            // Draggable Resizer
            Rectangle()
                .fill(Color.gray.opacity(0.1))
                .frame(width: 1)
                .overlay(
                    Rectangle()
                        .fill(Color.clear)
                        .frame(width: 10)
                        .onHover { hovering in
                            if hovering {
                                NSCursor.resizeLeftRight.push()
                            } else {
                                NSCursor.pop()
                            }
                        }
                        .gesture(
                            DragGesture()
                                .onChanged { value in
                                    if dragStartWidth == 0 { dragStartWidth = sidebarWidth }
                                    let newWidth = dragStartWidth + Double(value.translation.width)
                                    sidebarWidth = max(150, min(newWidth, 600))
                                }
                                .onEnded { _ in
                                    dragStartWidth = 0
                                    NSCursor.pop()
                                }
                        )
                )
                .zIndex(1)
            
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
                            // Single turn voice input placeholder
                        }) {
                            Image(systemName: "mic")
                                .foregroundColor(.secondary)
                        }
                        .buttonStyle(.plain)
                        
                        Button(action: {
                            isContinuousMode.toggle()
                        }) {
                            Image(systemName: isContinuousMode ? "waveform.circle.fill" : "waveform")
                                .foregroundColor(isContinuousMode ? .blue : .secondary)
                        }
                        .buttonStyle(.plain)
                        
                        Button(action: {
                            viewModel.isMuted.toggle()
                        }) {
                            Image(systemName: viewModel.isMuted ? "speaker.slash.fill" : "speaker.wave.2")
                                .foregroundColor(viewModel.isMuted ? .red : .secondary)
                        }
                        .buttonStyle(.plain)
                        
                        Button(action: {
                            showSettings.toggle()
                        }) {
                            Image(systemName: "gearshape")
                                .foregroundColor(.secondary)
                        }
                        .buttonStyle(.plain)
                        .popover(isPresented: $showSettings, arrowEdge: .bottom) {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("Settings")
                                    .font(.headline)
                                Text("This feature requires backend integration in Phase 6.")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            .padding()
                            .frame(width: 250)
                        }
                    }
                    .font(.system(size: 14))
                }
                .padding(.horizontal, 20)
                .frame(height: 56)
                .background(
                    ZStack {
                        bgColor.opacity(0.8) // For blur effect later
                        WindowDragView()
                    }
                )
                
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
                                HStack(spacing: 6) {
                                    ProgressView()
                                        .controlSize(.small)
                                    Text("Thinking...")
                                        .font(.system(size: 11))
                                        .foregroundColor(.secondary)
                                    Spacer()
                                }
                                .padding(.vertical, 4)
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
                            .onDrop(of: [.fileURL], isTargeted: nil) { providers in
                                for provider in providers {
                                    _ = provider.loadObject(ofClass: URL.self) { url, _ in
                                        if let url = url {
                                            DispatchQueue.main.async {
                                                if !viewModel.inputText.isEmpty {
                                                    viewModel.inputText += " "
                                                }
                                                viewModel.inputText += url.path
                                            }
                                        }
                                    }
                                }
                                return true
                            }
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .background(Color.black.opacity(0.05))
                    .cornerRadius(14)
                    // Make the entire wrapper clickable to focus the text field
                    .onTapGesture {
                        // Normally we'd use FocusState here, but since this is a simple port, 
                        // just preventing the tap from falling through is enough, 
                        // macOS automatically focuses the text field when clicking its padding area.
                    }
                    
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
                        SVGIconView(name: agent.iconName, size: 44)
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(isActive ? Color(hex: agent.color) : Color.clear, lineWidth: 2)
                                    .scaleEffect(isActive ? 1.05 : 1.0)
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
        .frame(minWidth: 700, idealWidth: 900, minHeight: 500, idealHeight: 650)
        .background(VisualEffectView().ignoresSafeArea())
        .ignoresSafeArea(.all, edges: .top)
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
        guard !text.isEmpty else { return }
        
        viewModel.sendMessage(text)
        viewModel.inputText = ""
    }
}

struct LegacyMessageBubble: View {
    let message: Message
    let userBgColor: Color
    let userTextColor: Color
    let agentTextColor: Color
    
    @State private var isHovered = false
    
    var body: some View {
        HStack(alignment: .bottom) {
            if message.isUser {
                Spacer(minLength: 40)
                VStack(alignment: .trailing, spacing: 4) {
                    bubbleContent
                    
                    // The row for the copy button always exists to prevent layout shifts
                    copyButton
                        .opacity(isHovered ? 1 : 0)
                }
            } else {
                VStack(alignment: .leading, spacing: 4) {
                    bubbleContent
                    
                    // The row for the copy button always exists to prevent layout shifts
                    copyButton
                        .opacity(isHovered ? 1 : 0)
                }
                Spacer(minLength: 40)
            }
        }
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.1)) {
                isHovered = hovering
            }
        }
    }
    
    private var bubbleContent: some View {
        Text(message.content)
            .textSelection(.enabled)
            .font(.system(size: 13))
            .lineSpacing(4)
            .padding(.horizontal, message.isUser ? 12 : 0)
            .padding(.vertical, message.isUser ? 8 : 4)
            .background(message.isUser ? userBgColor : Color.clear)
            .foregroundColor(message.isUser ? userTextColor : agentTextColor)
            .clipShape(
                CustomRoundedCorners(
                    topLeading: message.isUser ? 12 : 0,
                    topTrailing: message.isUser ? 12 : 0,
                    bottomLeading: message.isUser ? 12 : 0,
                    bottomTrailing: 0
                )
            )
    }
    
    private var copyButton: some View {
        Button(action: {
            let pasteboard = NSPasteboard.general
            pasteboard.clearContents()
            pasteboard.setString(message.content, forType: .string)
        }) {
            Image(systemName: "doc.on.doc")
                .font(.system(size: 10))
                .foregroundColor(.secondary)
                .padding(4)
                .background(Color.black.opacity(0.1))
                .cornerRadius(4)
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 4)
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
