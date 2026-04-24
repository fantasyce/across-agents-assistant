import Foundation

let tempPath = NSTemporaryDirectory() + "temp_screenshot.png"
if FileManager.default.fileExists(atPath: tempPath) {
    try? FileManager.default.removeItem(atPath: tempPath)
}

let process = Process()
process.launchPath = "/usr/sbin/screencapture"
process.arguments = ["-i", "-x", tempPath]

print("Launching screencapture...")
process.launch()
process.waitUntilExit()
print("Screencapture exited.")

if FileManager.default.fileExists(atPath: tempPath) {
    print("Screenshot exists! Size: \(try! FileManager.default.attributesOfItem(atPath: tempPath)[.size]!)")
} else {
    print("Screenshot does NOT exist.")
}
