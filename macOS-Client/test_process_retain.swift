import Foundation
import Cocoa

let tempPath = NSTemporaryDirectory() + "temp_screenshot_test2.png"

func doScreenshot() {
    let process = Process()
    process.launchPath = "/usr/sbin/screencapture"
    process.arguments = ["-x", tempPath] // no -i to avoid blocking without UI
    
    process.terminationHandler = { _ in
        print("Termination handler called!")
    }
    
    process.launch()
}

doScreenshot()

// keep runloop alive
RunLoop.main.run(until: Date(timeIntervalSinceNow: 2.0))
