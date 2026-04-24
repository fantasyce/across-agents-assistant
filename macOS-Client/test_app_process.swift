import Cocoa

class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        print("Launching process...")
        doScreenshot()
    }
    
    func doScreenshot() {
        let process = Process()
        process.launchPath = "/usr/sbin/screencapture"
        process.arguments = ["-x", NSTemporaryDirectory() + "test.png"]
        
        process.terminationHandler = { _ in
            print("Termination handler called in App!")
            DispatchQueue.main.async {
                NSApplication.shared.terminate(nil)
            }
        }
        process.launch()
        print("doScreenshot returned")
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
