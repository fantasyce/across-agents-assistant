import AppKit
import Foundation

enum AttachmentImageSupport {
    static let pngPasteboardType = NSPasteboard.PasteboardType("public.png")
    private static let legacyPNGPasteboardType = NSPasteboard.PasteboardType("PNG")
    private static let imageExtensions: Set<String> = [
        "png", "jpg", "jpeg", "gif", "heic", "heif", "webp", "tif", "tiff", "bmp"
    ]

    static func isDisplayableImage(mimeType: String?, fileName: String) -> Bool {
        if let mimeType, mimeType.lowercased().hasPrefix("image/") {
            return true
        }
        let ext = (fileName as NSString).pathExtension.lowercased()
        return imageExtensions.contains(ext)
    }

    static func pastedImageFileName(id: String = UUID().uuidString) -> String {
        "pasted-\(id).png"
    }

    static func previewImage(filePath: String, mimeType: String?, fileName: String) -> NSImage? {
        guard isDisplayableImage(mimeType: mimeType, fileName: fileName) else { return nil }
        return NSImage(contentsOfFile: filePath)
    }

    static func pngData(from pasteboard: NSPasteboard) -> Data? {
        if let data = pasteboard.data(forType: pngPasteboardType) {
            return data
        }
        if let data = pasteboard.data(forType: legacyPNGPasteboardType) {
            return data
        }
        if let tiffData = pasteboard.data(forType: .tiff),
           let image = NSImage(data: tiffData) {
            return pngData(from: image)
        }
        if let image = NSImage(pasteboard: pasteboard) {
            return pngData(from: image)
        }
        return nil
    }

    static func pngData(from image: NSImage) -> Data? {
        var proposedRect = NSRect(origin: .zero, size: image.size)
        guard let cgImage = image.cgImage(forProposedRect: &proposedRect, context: nil, hints: nil) else {
            guard let tiffData = image.tiffRepresentation,
                  let bitmap = NSBitmapImageRep(data: tiffData) else {
                return nil
            }
            return bitmap.representation(using: .png, properties: [:])
        }

        let bitmap = NSBitmapImageRep(cgImage: cgImage)
        bitmap.size = image.size
        return bitmap.representation(using: .png, properties: [:])
    }

    @MainActor
    static func copyImageFileToPasteboard(_ fileURL: URL) -> Bool {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()

        var didWrite = false
        if let image = NSImage(contentsOf: fileURL) {
            didWrite = pasteboard.writeObjects([image]) || didWrite
        }
        if let data = try? Data(contentsOf: fileURL) {
            didWrite = pasteboard.setData(data, forType: pngPasteboardType) || didWrite
        }
        didWrite = pasteboard.setString(fileURL.absoluteString, forType: .fileURL) || didWrite
        return didWrite
    }

    static func fittingSize(for imageSize: NSSize, maxSize: NSSize) -> NSSize {
        guard imageSize.width > 0, imageSize.height > 0 else { return maxSize }
        let scale = min(maxSize.width / imageSize.width, maxSize.height / imageSize.height, 1)
        return NSSize(
            width: max(1, ceil(imageSize.width * scale)),
            height: max(1, ceil(imageSize.height * scale))
        )
    }
}
