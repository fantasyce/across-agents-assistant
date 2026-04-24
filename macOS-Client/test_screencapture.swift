import Foundation
import Cocoa

let tempPath = NSTemporaryDirectory() + "temp_screenshot_test.png"
print("Will save to: \(tempPath)")

let process = Process()
process.launchPath = "/usr/sbin/screencapture"
process.arguments = ["-i", "-x", tempPath]

process.launch()
process.waitUntilExit()

if FileManager.default.fileExists(atPath: tempPath) {
    print("Screenshot saved successfully!")
    let size = try? FileManager.default.attributesOfItem(atPath: tempPath)[.size]
    print("Size: \(size ?? 0)")
} else {
    print("Failed to save screenshot.")
}
