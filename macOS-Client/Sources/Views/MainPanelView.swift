import SwiftUI

struct FileTreeView: View {
    let item: FileItemModel
    let depth: Int
    @ObservedObject var viewModel: SessionViewModel
    @Environment(\.colorScheme) var colorScheme
    
    var body: some View {
        let isSelected = item.id == viewModel.selectedFileId
        let highlightColor = colorScheme == .dark ? Color.legacyTreeSelectedDark : Color.legacyTreeSelectedLight
        
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
        .id(item.id)
        .onDrag {
            // Provide the actual file URL for dragging.
            return NSItemProvider(object: NSURL(fileURLWithPath: item.path))
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
    @State private var scrollAnchorId: String? = nil
    @State private var mcpPollingTimer: Timer? = nil
    
    var body: some View {
        HStack(spacing: 0) {
            // LEFT SIDEBAR: File Explorer Placeholder
            VStack(spacing: 0) {
                // Explorer Header (matches 56px height)
                HStack {
                    // Custom Traffic Lights
                    CustomTrafficLights()

                    Spacer()

                    // MCP Context Indicator
                    if !viewModel.activeMCPContexts.isEmpty {
                        HStack(spacing: 4) {
                            ForEach(viewModel.activeMCPContexts) { context in
                                HStack(spacing: 3) {
                                    Image(systemName: "externaldrive.fill")
                                        .font(.system(size: 9))
                                    Text(context.name)
                                        .font(.system(size: 9))
                                    if let dbPath = context.dbPath {
                                        Text("(\(URL(fileURLWithPath: dbPath).lastPathComponent))")
                                            .font(.system(size: 8))
                                            .foregroundColor(.secondary)
                                    }
                                }
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color.accentColor.opacity(0.15))
                                .cornerRadius(4)
                            }
                        }
                        .padding(.leading, 8)
                    }

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
                .background(
                    WindowDragView()
                        .contentShape(Rectangle())
                )
                
                Divider().opacity(0.5)
                
                // Explorer Content
                GeometryReader { geo in
                    ScrollView([.vertical, .horizontal], showsIndicators: false) {
                        LazyVStack(alignment: .leading, spacing: 0) {
                            ForEach(viewModel.flatFileTree, id: \.node.id) { element in
                                FileTreeView(item: element.node, depth: element.depth, viewModel: viewModel)
                            }
                        }
                        .scrollTargetLayout()
                        .padding(.top, 8)
                        .frame(minWidth: max(CGFloat(sidebarWidth), geo.size.width), minHeight: geo.size.height, alignment: .topLeading)
                    }
                    .scrollPosition(id: $scrollAnchorId)
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
                        .fill(Color.black.opacity(0.001)) // Must not be completely clear to receive touches
                        .frame(width: 16)
                        .contentShape(Rectangle())
                        .onHover { hovering in
                            if hovering {
                                NSCursor.resizeLeftRight.push()
                            } else {
                                NSCursor.pop()
                            }
                        }
                        .gesture(
                            DragGesture(coordinateSpace: .global)
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
                .zIndex(100)
            
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
                            viewModel.copyFullConversation()
                        }) {
                            Image(systemName: "doc.on.clipboard")
                                .font(.system(size: 13))
                                .foregroundColor(.secondary)
                        }
                        .buttonStyle(.plain)
                        .help("复制完整对话记录")
                        
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
                            .contentShape(Rectangle())
                    }
                )
                
                Divider().opacity(0.5)
                
                // Messages List
                ScrollView {
                    ScrollViewReader { proxy in
                        VStack(alignment: .leading, spacing: 16) {
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
                                .offset(x: -2) // Compensate for ProgressView's intrinsic margin
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
                    VStack(alignment: .leading, spacing: 6) {
                        // Attached Files Area removed as it's now inline
                        
                        HStack {
                            ZStack(alignment: .topLeading) {
                                if viewModel.inputText.isEmpty {
                                    Text("Ask anything...")
                                        .font(.system(size: 13))
                                        .foregroundColor(.secondary.opacity(0.5))
                                        .padding(.top, 2)
                                        .padding(.leading, 4)
                                }
                                
                                MacEditorView(
                                     text: $viewModel.inputText,
                                     attachedFiles: $viewModel.attachedFiles,
                                     onSubmit: {
                                         if viewModel.pendingApproval == nil {
                                             submit()
                                         }
                                     },
                                     onNavigateHistory: { up in
                                         viewModel.navigateHistory(up: up)
                                     },
                                     textColor: NSColor(textColor)
                                 )
                                .disabled(viewModel.pendingApproval != nil)
                            }
                            .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .padding(.vertical, 6)
                    .padding(.horizontal, 8)
                    .background(Color.black.opacity(0.05))
                    .cornerRadius(14)
                    
                    if viewModel.isProcessing {
                        Button(action: {
                            viewModel.cancelGeneration()
                        }) {
                            Image(systemName: "stop.circle.fill")
                                .font(.system(size: 14))
                                .foregroundColor(accentColor)
                                .frame(width: 32, height: 32)
                                .background(Color.black.opacity(0.05))
                                .cornerRadius(6)
                        }
                        .buttonStyle(.plain)
                        .help("停止生成")
                    } else {
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
        .onAppear {
            viewModel.fetchMCPContexts()
            mcpPollingTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { _ in
                viewModel.fetchMCPContexts()
            }
        }
        .onDisappear {
            mcpPollingTimer?.invalidate()
        }
        .overlay(
            Group {
                if viewModel.showMCPPreferences {
                    MCPPreferencesView(onClose: {
                        withAnimation {
                            viewModel.showMCPPreferences = false
                        }
                    })
                    .transition(.opacity)
                    .zIndex(200)
                }
                
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
        guard !viewModel.isProcessing else { return }
        let text = viewModel.inputText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty || !viewModel.attachedFiles.isEmpty else { return }
        
        viewModel.sendMessage(text, attachedFiles: viewModel.attachedFiles)
        viewModel.inputText = ""
        viewModel.attachedFiles = []
    }
}

struct LegacyMessageBubble: View {
    let message: Message
    let userBgColor: Color
    let userTextColor: Color
    let agentTextColor: Color
    
    @State private var isHovered = false
    @State private var isCopied = false
    
    var body: some View {
        HStack(alignment: .bottom) {
            if message.isUser {
                Spacer(minLength: 40)
                VStack(alignment: .trailing, spacing: 4) {
                    bubbleContent
                    
                    // The row for the copy button always exists to prevent layout shifts
                    copyButton
                        .opacity(isHovered ? 1 : 0)
                        .offset(x: 2)
                }
            } else {
                VStack(alignment: .leading, spacing: 4) {
                    bubbleContent
                    
                    // The row for the copy button always exists to prevent layout shifts
                    copyButton
                        .opacity(isHovered ? 1 : 0)
                        .offset(x: -2)
                }
                Spacer(minLength: 40)
            }
        }
        .contentShape(Rectangle())
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.1)) {
                isHovered = hovering
                if !hovering {
                    // Reset copied state when mouse leaves the message bubble
                    isCopied = false
                }
            }
        }
    }
    
    @MainActor
    private var bubbleContent: some View {
        VStack(alignment: message.isUser ? .trailing : .leading, spacing: 6) {
            if !message.content.isEmpty {
                if message.attachedFiles.isEmpty {
                    Text(message.content)
                        .textSelection(.enabled)
                        .font(.system(size: 13))
                        .lineSpacing(4)
                } else {
                    mixedContent()
                        .textSelection(.enabled)
                        .font(.system(size: 13))
                        .lineSpacing(4)
                }
            } else if !message.attachedFiles.isEmpty {
                mixedContent()
                    .textSelection(.enabled)
                    .font(.system(size: 13))
                    .lineSpacing(4)
            }
        }
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
    
    @MainActor
    private func mixedContent() -> Text {
        let components = message.content.components(separatedBy: "\u{FFFC}")
        var result = Text("")
        var fileIndex = 0
        
        let textColorToUse = message.isUser ? userTextColor : agentTextColor
        
        for (i, component) in components.enumerated() {
            result = result + Text(component)
            if i < components.count - 1 && fileIndex < message.attachedFiles.count {
                let file = message.attachedFiles[fileIndex]
                
                // Create the chip image
                let renderer = ImageRenderer(content: FileChipView(file: file, textColor: textColorToUse))
                renderer.scale = NSScreen.main?.backingScaleFactor ?? 2.0
                if let image = renderer.nsImage {
                    // Align the chip visually with the text
                    result = result + Text(Image(nsImage: image)).baselineOffset(-3)
                } else {
                    result = result + Text(" [\(file.name)] ")
                }
                
                fileIndex += 1
            }
        }
        
        // If there are leftover files that weren't represented by \u{FFFC} (shouldn't happen normally)
        while fileIndex < message.attachedFiles.count {
            let file = message.attachedFiles[fileIndex]
            let renderer = ImageRenderer(content: FileChipView(file: file, textColor: textColorToUse))
            renderer.scale = NSScreen.main?.backingScaleFactor ?? 2.0
            if let image = renderer.nsImage {
                result = result + Text(" ") + Text(Image(nsImage: image)).baselineOffset(-3)
            }
            fileIndex += 1
        }
        
        return result
    }
    
    private var copyButton: some View {
        Button(action: {
            let pasteboard = NSPasteboard.general
            pasteboard.clearContents()
            pasteboard.setString(message.content, forType: .string)
            withAnimation {
                isCopied = true
            }
        }) {
            ZStack {
                Image(systemName: "doc.on.doc")
                    .font(.system(size: 10))
                    .opacity(isCopied ? 0 : 1)
                
                Image(systemName: "checkmark")
                    .font(.system(size: 10, weight: .bold))
                    .opacity(isCopied ? 1 : 0)
            }
            .foregroundColor(isCopied ? .green : .secondary)
            .frame(width: 14, height: 14) // Fixed frame to prevent layout shifts
            .padding(4)
            .background(Color.black.opacity(0.1))
            .cornerRadius(4)
        }
        .buttonStyle(.plain)
    }
}

struct AttachedFileChip: View {
    let file: AttachedFile
    let onRemove: (() -> Void)?
    @State private var isHovered = false
    @Environment(\.colorScheme) var colorScheme
    
    var body: some View {
        HStack(spacing: 4) {
            if isHovered && onRemove != nil {
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(.secondary)
                    .font(.system(size: 12))
            } else {
                if file.isFolder {
                    SVGIconView(name: "icon.14.explorer.folder.closed", size: 12)
                } else {
                    SVGIconView(name: getFileIconName(fileName: file.name), size: 12)
                }
            }
            
            Text(file.name)
                .font(.system(size: 11))
                .foregroundColor(.primary)
                .lineLimit(1)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(colorScheme == .dark ? Color.white.opacity(0.1) : Color.black.opacity(0.08))
        .cornerRadius(6)
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.1)) {
                isHovered = hovering
            }
        }
        .onTapGesture {
            if onRemove != nil {
                onRemove?()
            }
        }
        .help(file.path)
    }
}

