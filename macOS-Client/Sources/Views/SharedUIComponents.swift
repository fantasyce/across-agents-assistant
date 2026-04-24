import SwiftUI

import AppKit



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
    var onClose: (() -> Void)? = nil
    
    var body: some View {
        HStack(spacing: 8) {
            TrafficLightButton(colorHex: "#FF5F56", defaultHex: "#FFBFBB", iconName: "xmark", isGroupHovered: isHovered) {
                if let onClose = onClose {
                    onClose()
                } else {
                    NSApplication.shared.keyWindow?.close()
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
    if let url = Bundle.module.url(forResource: name, withExtension: "svg", subdirectory: "Assets/icons"),
       let data = try? Data(contentsOf: url) {
        return NSImage(data: data)
    } else if let url = Bundle.main.url(forResource: name, withExtension: "svg", subdirectory: "Assets/icons"),
              let data = try? Data(contentsOf: url) {
        return NSImage(data: data)
    }
    return nil
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

@MainActor
class FileAttachment: NSTextAttachment {
    let attachedFile: AttachedFile
    
    init(file: AttachedFile) {
        self.attachedFile = file
        super.init(data: nil, ofType: nil)
        
        let renderer = ImageRenderer(content: FileChipView(file: file, textColor: .white))
        renderer.scale = NSScreen.main?.backingScaleFactor ?? 2.0
        if let image = renderer.nsImage {
            self.image = image
            let width = image.size.width
            // Cap height to 15 to ensure it never pushes the line height up
            let height = min(image.size.height, 15.0)
            // Adjust y offset to align the chip vertically with the surrounding text baseline
            self.bounds = NSRect(x: 0, y: -3, width: width, height: height)
        }
    }
    
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
}