import SwiftUI

struct InputAttachmentPreview: View {
    let file: AttachedFile
    let onRemove: () -> Void
    @Environment(\.colorScheme) private var colorScheme

    private var tileBackground: Color {
        colorScheme == .dark ? Color.white.opacity(0.10) : Color.black.opacity(0.06)
    }

    private var tileBorder: Color {
        colorScheme == .dark ? Color.white.opacity(0.18) : Color.black.opacity(0.10)
    }

    var body: some View {
        ZStack(alignment: .topTrailing) {
            previewContent
                .frame(width: 76, height: 54)
                .background(tileBackground)
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(tileBorder, lineWidth: 1)
                )

            Button(action: onRemove) {
                Image(systemName: "xmark")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundColor(colorScheme == .dark ? .white : .black.opacity(0.75))
                    .frame(width: 16, height: 16)
                    .background(colorScheme == .dark ? Color.black.opacity(0.55) : Color.white.opacity(0.92))
                    .clipShape(Circle())
                    .overlay(Circle().stroke(tileBorder, lineWidth: 1))
            }
            .buttonStyle(.plain)
            .offset(x: 5, y: -5)
        }
        .frame(width: 82, height: 60)
        .help(file.path)
    }

    @ViewBuilder
    private var previewContent: some View {
        if let image = AttachmentImageSupport.previewImage(
            filePath: file.path,
            mimeType: file.mimeType,
            fileName: file.name
        ) {
            Image(nsImage: image)
                .resizable()
                .scaledToFill()
                .frame(width: 76, height: 54)
                .clipped()
        } else {
            VStack(spacing: 4) {
                if file.isFolder {
                    SVGIconView(name: "icon.14.explorer.folder.closed", size: 18)
                } else {
                    SVGIconView(name: getFileIconName(fileName: file.name), size: 18)
                }
                Text(file.name)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .frame(maxWidth: 64)
            }
            .padding(.horizontal, 6)
        }
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
                .foregroundColor(.gray)
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


