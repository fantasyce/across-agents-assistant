import SwiftUI

import AppKit



private let swiftPMResourceBundleName = "AcrossAgentsAssistant_AcrossAgentsAssistantClient.bundle"

func bundledAssetURL(named name: String, withExtension ext: String, subdirectory: String) -> URL? {
    let relativePath = "\(subdirectory)/\(name).\(ext)"
    let bundleCandidates: [URL?] = [
        Bundle.main.resourceURL?.appendingPathComponent(swiftPMResourceBundleName),
        Bundle.main.bundleURL.appendingPathComponent(swiftPMResourceBundleName),
        Bundle.main.resourceURL,
        Bundle.main.bundleURL,
    ]

    for bundleURL in bundleCandidates.compactMap({ $0 }) {
        let url = bundleURL.appendingPathComponent(relativePath)
        if FileManager.default.fileExists(atPath: url.path) {
            return url
        }
    }

    return Bundle.main.url(forResource: name, withExtension: ext, subdirectory: subdirectory)
}

private let iconFileExtensions = ["webp", "png", "svg", "icns"]

private let installedAppIconCandidates: [String: [String]] = [
    "agent.cursor": [
        "/Applications/Cursor.app",
        "~/Applications/Cursor.app",
    ],
]

private let directTemplateAgentIconNames: Set<String> = [
    "agent.hermes",
]

private let directInsetAgentIconNames: Set<String> = [
    "agent.codex",
    "agent.hermes",
    "agent.openclaw",
    "agent.local",
]

func isDirectTemplateAgentIcon(_ name: String) -> Bool {
    directTemplateAgentIconNames.contains(name)
}

func agentIconVisualScale(_ name: String) -> CGFloat {
    directInsetAgentIconNames.contains(name) ? 0.78 : 1.0
}

func agentIconVisualSize(_ name: String, containerSize: CGFloat) -> CGFloat {
    containerSize * agentIconVisualScale(name)
}

func agentIconCornerRadius(_ name: String, visualSize: CGFloat) -> CGFloat {
    directInsetAgentIconNames.contains(name) ? visualSize * 0.22 : visualSize * 0.20
}

private func themedIconBaseNames(_ name: String, colorScheme: ColorScheme?) -> [String] {
    if colorScheme == .light {
        return [name + ".light", name]
    }
    return [name]
}

private func iconOverrideDirectories() -> [URL] {
    let fileManager = FileManager.default
    let appSupportURLs = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask)
    guard let appSupportURL = appSupportURLs.first else {
        return []
    }
    return [
        appSupportURL.appendingPathComponent("AcrossAgentsAssistant/Icons", isDirectory: true),
        appSupportURL.appendingPathComponent("Across Agents Assistant/Icons", isDirectory: true),
    ]
}

private func loadImage(at url: URL) -> NSImage? {
    if let image = NSImage(contentsOf: url) {
        return image
    }
    guard let data = try? Data(contentsOf: url) else {
        return nil
    }
    return NSImage(data: data)
}

private func loadUserIconOverride(named name: String, colorScheme: ColorScheme?) -> NSImage? {
    let baseNames = themedIconBaseNames(name, colorScheme: colorScheme)
    for directory in iconOverrideDirectories() {
        for baseName in baseNames {
            for ext in iconFileExtensions {
                let url = directory.appendingPathComponent("\(baseName).\(ext)")
                if FileManager.default.fileExists(atPath: url.path),
                   let image = loadImage(at: url) {
                    return image
                }
            }
        }
    }
    return nil
}

private func loadInstalledAppIcon(named name: String, colorScheme: ColorScheme?) -> NSImage? {
    guard let appPaths = installedAppIconCandidates[name] else {
        return nil
    }
    for appPath in appPaths {
        let expandedPath = (appPath as NSString).expandingTildeInPath
        guard FileManager.default.fileExists(atPath: expandedPath) else {
            continue
        }
        let image = NSWorkspace.shared.icon(forFile: expandedPath)
        image.size = NSSize(width: 512, height: 512)
        return image
    }
    return nil
}

private func loadBundledAgentIcon(named name: String, colorScheme: ColorScheme?) -> NSImage? {
    let baseNames = themedIconBaseNames(name, colorScheme: colorScheme)
    for baseName in baseNames {
        for ext in ["webp", "png", "svg"] {
            guard let url = bundledAssetURL(named: baseName, withExtension: ext, subdirectory: "Assets/icons") else {
                continue
            }
            if let image = loadImage(at: url) {
                return image
            }
        }
    }
    return nil
}

func loadAgentIconSync(name: String, colorScheme: ColorScheme? = nil) -> NSImage? {
    if name.hasPrefix("agent."),
       let overrideImage = loadUserIconOverride(named: name, colorScheme: colorScheme) {
        return overrideImage
    }

    if let bundledIcon = loadBundledAgentIcon(named: name, colorScheme: colorScheme) {
        return bundledIcon
    }

    if name.hasPrefix("agent."),
       let installedAppImage = loadInstalledAppIcon(named: name, colorScheme: colorScheme) {
        return installedAppImage
    }

    return nil
}

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
    static let legacyBgLight = Color(red: 244/255, green: 245/255, blue: 247/255)
    static let legacyBgDark = Color(red: 28/255, green: 28/255, blue: 30/255)

    static let legacySidebarLight = Color(red: 247/255, green: 248/255, blue: 250/255)
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

enum SettingsHubPageLayout {
    static let contentMaxWidth: CGFloat = 980
    static let contentPadding: CGFloat = 28
    static let sectionSpacing: CGFloat = 28
}

struct CustomTrafficLights: View {
    @State private var isHovered = false
    var onClose: (() -> Void)? = nil

    var body: some View {
        HStack(spacing: 8) {
            TrafficLightButton(colorHex: "#FF5F56", defaultHex: "#FFBFBB", iconName: "xmark", isGroupHovered: isHovered) {
                if let onClose = onClose {
                    onClose()
                } else {
                    WindowVisibilityController.closeMainWindow()
                }
            }
            TrafficLightButton(colorHex: "#FFBD2E", defaultHex: "#FFE4AB", iconName: "minus", isGroupHovered: isHovered) {
                if onClose == nil {
                    NSApplication.shared.keyWindow?.miniaturize(nil)
                }
            }
            TrafficLightButton(colorHex: "#27C93F", defaultHex: "#A8E9B2", iconName: "arrow.up.left.and.arrow.down.right", isGroupHovered: isHovered) {
                if onClose == nil {
                    NSApplication.shared.keyWindow?.zoom(nil)
                }
            }
        }
        .contentShape(Rectangle())
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

struct WindowDragView: NSViewRepresentable {
    func makeNSView(context: Context) -> DraggableNSView {
        let view = DraggableNSView()
        // Ensure the view registers hits in AppKit
        view.wantsLayer = true
        view.layer?.backgroundColor = NSColor(white: 0, alpha: 0.001).cgColor
        return view
    }

    func updateNSView(_ nsView: DraggableNSView, context: Context) {}
}

class DraggableNSView: NSView {
    override var mouseDownCanMoveWindow: Bool {
        return false
    }

    override func mouseDown(with event: NSEvent) {
        if event.clickCount == 2 {
            self.window?.zoom(nil)
        } else {
            self.window?.performDrag(with: event)
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

func loadSVGIconSync(name: String) -> NSImage? {
    loadAgentIconSync(name: name)
}

func loadTemplateIconSync(name: String, colorScheme: ColorScheme? = nil) -> NSImage? {
    guard let image = loadAgentIconSync(name: name, colorScheme: colorScheme),
          let copy = image.copy() as? NSImage else {
        return nil
    }
    copy.isTemplate = true
    return copy
}

struct BundledTemplateIcon: View {
    let name: String
    let fallbackSystemName: String
    var size: CGFloat
    var weight: Font.Weight = .semibold
    var color: Color

    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        Group {
            if let image = loadTemplateIconSync(name: name, colorScheme: colorScheme) {
                Image(nsImage: image)
                    .renderingMode(.template)
                    .resizable()
                    .scaledToFit()
                    .frame(width: size, height: size)
            } else {
                Image(systemName: fallbackSystemName)
                    .font(.system(size: size, weight: weight))
            }
        }
        .foregroundColor(color)
    }
}

struct FileChipView: View {
    let file: AttachedFile
    let textColor: Color

    var body: some View {
        HStack(spacing: 4) {
            let iconName = file.isFolder ? "icon.14.explorer.folder.closed" : getFileIconName(fileName: file.name)
            if let nsImage = loadSVGIconSync(name: iconName) {
                Image(nsImage: nsImage)
                    .resizable()
                    .scaledToFit()
                    .frame(width: 14, height: 14)
            } else {
                Image(systemName: "doc")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 14, height: 14)
                    .foregroundColor(.secondary)
            }
            Text(file.name)
                .font(.system(size: 13, weight: .regular))
                .lineLimit(1)
                .truncationMode(.middle)
                .foregroundColor(textColor)
                .fixedSize()
        }
        .padding(.horizontal, 2)
        .padding(.vertical, 0)
        .background(Color.clear)
    }
}

struct AttachmentPreviewView: View {
    let file: AttachedFile
    let textColor: Color
    var maxPreviewSize = NSSize(width: 132, height: 80)

    var body: some View {
        if let image = AttachmentImageSupport.previewImage(
            filePath: file.path,
            mimeType: file.mimeType,
            fileName: file.name
        ) {
            let size = AttachmentImageSupport.fittingSize(for: image.size, maxSize: maxPreviewSize)
            Image(nsImage: image)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(width: size.width, height: size.height)
                .background(Color.black.opacity(0.10))
                .clipShape(RoundedRectangle(cornerRadius: 7))
                .overlay(
                    RoundedRectangle(cornerRadius: 7)
                        .stroke(Color.white.opacity(0.18), lineWidth: 1)
                )
                .help(file.path)
        } else {
            FileChipView(file: file, textColor: textColor)
        }
    }
}

class FileAttachment: NSTextAttachment {
    let attachedFile: AttachedFile

    @MainActor
    init(file: AttachedFile) {
        self.attachedFile = file
        super.init(data: nil, ofType: nil)

        let isImagePreview = AttachmentImageSupport.isDisplayableImage(
            mimeType: file.mimeType,
            fileName: file.name
        )
        let renderer = ImageRenderer(content: AttachmentPreviewView(file: file, textColor: .white))
        renderer.scale = NSScreen.main?.backingScaleFactor ?? 2.0
        if let image = renderer.nsImage {
            self.image = image
            let width = image.size.width
            if isImagePreview {
                let height = min(image.size.height, 80)
                self.bounds = NSRect(x: 0, y: -height + 14, width: width, height: height)
            } else {
                // Cap height to 15 to ensure file chips never push the line height up.
                let height = min(image.size.height, 15.0)
                self.bounds = NSRect(x: 0, y: -3, width: width, height: height)
            }
        }
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
}

struct AgentSidebarIcon: View {
    @Environment(\.colorScheme) private var colorScheme

    let agent: AgentModel
    let isActive: Bool
    let onTap: () -> Void

    @State private var isHovered = false

    var body: some View {
        Button(action: onTap) {
            Group {
                if let img = loadIconImage(named: agent.iconName, type: agent.type) {
                    let visualSize = agentIconVisualSize(agent.iconName, containerSize: 44)
                    let visualCornerRadius = agentIconCornerRadius(agent.iconName, visualSize: visualSize)
                    if isDirectTemplateAgentIcon(agent.iconName) {
                        Image(nsImage: img)
                            .renderingMode(.template)
                            .resizable()
                            .scaledToFit()
                            .foregroundColor(colorScheme == .dark ? .white : .legacyTextLight)
                            .frame(width: visualSize, height: visualSize)
                            .clipShape(RoundedRectangle(cornerRadius: visualCornerRadius))
                    } else {
                        Image(nsImage: img)
                            .resizable()
                            .scaledToFit()
                            .frame(width: visualSize, height: visualSize)
                            .clipShape(RoundedRectangle(cornerRadius: visualCornerRadius))
                    }
                } else {
                    Rectangle()
                        .fill(Color.gray)
                }
            }
            .frame(width: 44, height: 44)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(isActive ? Color(hex: agent.color) : Color.clear.opacity(isHovered ? 0.5 : 0), lineWidth: isActive ? 2 : 1)
            )
            .scaleEffect(isActive ? 1.0 : (isHovered ? 1.05 : 1.0))
        }
        .buttonStyle(.plain)
        .help(agent.name)
        .onHover { hovering in
            isHovered = hovering
        }
    }

    private func loadIconImage(named name: String, type: AgentType) -> NSImage? {
        loadAgentIconSync(name: name, colorScheme: colorScheme)
    }
}
