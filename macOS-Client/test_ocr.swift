import Foundation
import Cocoa
import Vision

let imageURL = URL(fileURLWithPath: "/Users/fanhcy/Documents/projects/across-agents-assistant/macOS-Client/test_screenshot.png")

// create a dummy image with some text
let image = NSImage(size: NSSize(width: 400, height: 100))
image.lockFocus()
NSColor.white.set()
NSRect(x: 0, y: 0, width: 400, height: 100).fill()
let text = "Hello World 123 测试截图 OCR" as NSString
text.draw(at: NSPoint(x: 10, y: 40), withAttributes: [.foregroundColor: NSColor.black, .font: NSFont.systemFont(ofSize: 24)])
image.unlockFocus()

if let tiffData = image.tiffRepresentation, let bitmap = NSBitmapImageRep(data: tiffData), let pngData = bitmap.representation(using: .png, properties: [:]) {
    try? pngData.write(to: imageURL)
}

let request = VNRecognizeTextRequest { request, error in
    if let error = error {
        print("OCR Error: \(error)")
        exit(1)
    }
    
    guard let observations = request.results as? [VNRecognizedTextObservation] else {
        print("No observations")
        exit(1)
    }
    
    let text = observations.compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
    print("OCR Result: '\(text)'")
}

request.recognitionLevel = .accurate
request.recognitionLanguages = ["zh-Hans", "en-US"]
request.usesLanguageCorrection = true

let handler = VNImageRequestHandler(url: imageURL, options: [:])
do {
    try handler.perform([request])
} catch {
    print("Failed to perform OCR: \(error)")
}
