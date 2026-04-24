import Cocoa

let text = "Hello\n【截图内容】:\nsome text\n"
let newAttrStr = NSMutableAttributedString(string: text)
let textView = NSTextView(frame: NSRect(x: 0, y: 0, width: 400, height: 400))
textView.textStorage?.setAttributedString(newAttrStr)

textView.font = .systemFont(ofSize: 13)
textView.textColor = .red

let attr = textView.textStorage?.attributes(at: 0, effectiveRange: nil)
print(attr ?? [:])
