import AppKit
import Foundation

@main
struct AttachmentImageSupportBehavior {
    @MainActor
    static func main() throws {
        try testImageAttachmentsArePreviewable()
        try testPastedImageFileNamesArePng()
        try testNSImageConvertsToPNGData()
        try testCopyImageFileToPasteboardPublishesPNG()
    }

    private static func testImageAttachmentsArePreviewable() throws {
        assert(
            AttachmentImageSupport.isDisplayableImage(mimeType: "image/png", fileName: "capture.bin"),
            "image MIME types should be previewable even when the filename is generic"
        )
        assert(
            AttachmentImageSupport.isDisplayableImage(mimeType: nil, fileName: "capture.PNG"),
            "known image extensions should be previewable without a MIME type"
        )
        assert(
            !AttachmentImageSupport.isDisplayableImage(mimeType: "application/pdf", fileName: "report.pdf"),
            "non-image files should keep the compact file chip"
        )
    }

    private static func testPastedImageFileNamesArePng() throws {
        let fileName = AttachmentImageSupport.pastedImageFileName(id: "unit-test")
        assert(fileName == "pasted-unit-test.png", "pasted image filenames should be deterministic PNG names")
    }

    private static func testNSImageConvertsToPNGData() throws {
        let image = NSImage(size: NSSize(width: 2, height: 2))
        image.lockFocus()
        NSColor.systemPurple.setFill()
        NSRect(x: 0, y: 0, width: 2, height: 2).fill()
        image.unlockFocus()

        guard let pngData = AttachmentImageSupport.pngData(from: image) else {
            fatalError("expected PNG data")
        }
        let pngSignature = [UInt8](pngData.prefix(8))
        assert(pngSignature == [137, 80, 78, 71, 13, 10, 26, 10], "expected PNG signature")
    }

    @MainActor
    private static func testCopyImageFileToPasteboardPublishesPNG() throws {
        let image = NSImage(size: NSSize(width: 4, height: 4))
        image.lockFocus()
        NSColor.systemGreen.setFill()
        NSRect(x: 0, y: 0, width: 4, height: 4).fill()
        image.unlockFocus()

        guard let pngData = AttachmentImageSupport.pngData(from: image) else {
            fatalError("expected PNG data")
        }
        let fileURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("attachment-image-support-\(UUID().uuidString).png")
        try pngData.write(to: fileURL, options: .atomic)
        defer { try? FileManager.default.removeItem(at: fileURL) }

        assert(AttachmentImageSupport.copyImageFileToPasteboard(fileURL), "expected image copy to succeed")
        assert(
            NSPasteboard.general.data(forType: AttachmentImageSupport.pngPasteboardType) != nil,
            "clipboard should include public PNG data"
        )
    }
}
