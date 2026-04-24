import Foundation

let tempPath = NSTemporaryDirectory() + "temp_screenshot.png"
let process = Process()
process.launchPath = "/usr/sbin/screencapture"
process.arguments = ["-x", tempPath] // no -i

process.launch()
process.waitUntilExit()

if FileManager.default.fileExists(atPath: tempPath) {
    print("File exists! Size: \(try! FileManager.default.attributesOfItem(atPath: tempPath)[.size]!)")
    try! FileManager.default.removeItem(atPath: tempPath)
} else {
    print("File DOES NOT exist!")
}
