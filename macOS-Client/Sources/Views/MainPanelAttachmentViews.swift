import SwiftUI

struct InputAttachmentPreview: View {
    let file: AttachedFile
    let onRemove: () -> Void
    @EnvironmentObject private var appPreferences: AppPreferences

    @State private var isHovered = false

    var body: some View {
        ZStack(alignment: .topTrailing) {
            previewContent
                .frame(width: 76, height: 52)
                .background(Color(nsColor: .controlBackgroundColor))
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                        .stroke(Color(nsColor: .separatorColor), lineWidth: 0.5)
                )

            Button(action: onRemove) {
                Image(systemName: "xmark.circle.fill")
                    .symbolRenderingMode(.palette)
                    .foregroundStyle(Color.primary, Color(nsColor: .windowBackgroundColor))
                    .font(.system(size: 15))
            }
            .buttonStyle(.plain)
            .offset(x: 5, y: -5)
            .opacity(isHovered ? 1 : 0.72)
            .accessibilityLabel(
                Text(String(format: appPreferences.text("attachment.remove"), file.name))
            )
        }
        .frame(width: 82, height: 58)
        .contentShape(Rectangle())
        .onHover { isHovered = $0 }
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
                .frame(width: 76, height: 52)
                .clipped()
        } else {
            VStack(spacing: 4) {
                Image(systemName: file.isFolder ? "folder" : "doc")
                    .font(.system(size: 17))
                    .foregroundStyle(.secondary)
                Text(file.name)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundStyle(.secondary)
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
    @EnvironmentObject private var appPreferences: AppPreferences

    @State private var isHovered = false

    var body: some View {
        Group {
            if let onRemove {
                Button(action: onRemove) {
                    chipContent(isRemovable: true)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(
                    Text(String(format: appPreferences.text("attachment.remove"), file.name))
                )
            } else {
                chipContent(isRemovable: false)
            }
        }
        .onHover { isHovered = $0 }
        .help(file.path)
    }

    private func chipContent(isRemovable: Bool) -> some View {
        HStack(spacing: 5) {
            Image(systemName: isRemovable && isHovered ? "xmark" : (file.isFolder ? "folder" : "doc"))
                .font(.system(size: 10, weight: .medium))
                .foregroundStyle(.secondary)

            Text(file.name)
                .font(.system(size: 11))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .truncationMode(.middle)
        }
        .padding(.horizontal, 7)
        .frame(height: 24)
        .background(Color(nsColor: .controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 6, style: .continuous)
                .stroke(Color(nsColor: .separatorColor), lineWidth: 0.5)
        )
    }
}

struct MessageAttachmentPreview: View {
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
                .background(Color(nsColor: .controlBackgroundColor))
                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                        .stroke(Color(nsColor: .separatorColor), lineWidth: 0.5)
                )
                .help(file.path)
        } else {
            HStack(spacing: 4) {
                Image(systemName: file.isFolder ? "folder" : "doc")
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                Text(file.name)
                    .font(.system(size: 12))
                    .foregroundStyle(textColor)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            .padding(.horizontal, 6)
            .frame(height: 22)
            .background(Color(nsColor: .controlBackgroundColor))
            .clipShape(RoundedRectangle(cornerRadius: 5, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 5, style: .continuous)
                    .stroke(Color(nsColor: .separatorColor), lineWidth: 0.5)
            )
        }
    }
}
