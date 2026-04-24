import Cocoa
import SwiftUI

struct TestEditor: NSViewRepresentable {
    @Binding var text: String
    
    func makeNSView(context: Context) -> NSTextView {
        let tv = NSTextView()
        tv.backgroundColor = .black
        return tv
    }
    
    func updateNSView(_ nsView: NSTextView, context: Context) {
        if nsView.string != text {
            let attr = NSMutableAttributedString(string: text)
            nsView.textStorage?.setAttributedString(attr)
            
            // Apply font and color AFTER setting attributed string
            nsView.font = .systemFont(ofSize: 24)
            nsView.textColor = .red
        }
    }
}

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    func applicationDidFinishLaunching(_ notification: Notification) {
        let view = TestEditor(text: .constant("Hello World! This is red text on black."))
        let host = NSHostingView(rootView: view)
        
        let wc = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 400, height: 400), styleMask: [.titled, .closable], backing: .buffered, defer: false)
        wc.contentView = host
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
