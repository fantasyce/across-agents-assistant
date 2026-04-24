import Cocoa

let text = "Hello\u{FFFC}World"
let newAttrStr = NSMutableAttributedString(string: text)
let attachment = NSTextAttachment()
let cell = NSTextAttachmentCell(imageCell: NSImage(size: NSSize(width: 10, height: 10)))
attachment.attachmentCell = cell
newAttrStr.replaceCharacters(in: NSRange(location: 5, length: 1), with: NSAttributedString(attachment: attachment))

let textView = NSTextView(frame: NSRect(x: 0, y: 0, width: 400, height: 400))
textView.textStorage?.setAttributedString(newAttrStr)

textView.font = .systemFont(ofSize: 13)
textView.textColor = .red

var effectiveRange = NSRange()
let attr = textView.textStorage?.attributes(at: 5, effectiveRange: &effectiveRange)
print("Attributes at index 5: \(attr ?? [:])")
print("Effective range: \(effectiveRange)")
