import SwiftUI
import AppKit

import SwiftUI

enum MainPanelIconMetrics {
    static let glyphSize: CGFloat = 14
    static let buttonSize: CGFloat = 24
}

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

    @State var nsImage: NSImage?

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

    func loadImage() {
        if let url = bundledAssetURL(named: name, withExtension: "svg", subdirectory: "Assets/icons") {
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


