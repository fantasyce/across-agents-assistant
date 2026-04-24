import Cocoa
import SwiftUI

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    func applicationDidFinishLaunching(_ notification: Notification) {
        let textView = NSTextView(frame: NSRect(x: 0, y: 0, width: 400, height: 400))
        textView.backgroundColor = .black
        textView.string = "Hello"
        textView.textColor = .white
        textView.font = .systemFont(ofSize: 24)
        
        // now programmatically update it
        let newStr = NSMutableAttributedString(string: "Hello World")
        textView.textStorage?.setAttributedString(newStr)
        textView.font = .systemFont(ofSize: 24)
        textView.textColor = .red
        
        let wc = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 400, height: 400), styleMask: [.titled, .closable], backing: .buffered, defer: false)
        wc.contentView = textView
        wc.makeKeyAndOrderFront(nil)
        self.window = wc
        
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
            NSApplication.shared.terminate(nil)
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
