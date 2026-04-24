import CoreGraphics
import Cocoa

func checkScreenRecordingPermission() -> Bool {
    if #available(macOS 10.15, *) {
        // CGPreflightScreenCaptureAccess() returns true if authorized, false if not
        return CGPreflightScreenCaptureAccess()
    }
    return true // Assume true for older macOS
}

func requestScreenRecordingPermission() -> Bool {
    if #available(macOS 10.15, *) {
        return CGRequestScreenCaptureAccess()
    }
    return true
}

print("Has Permission? \(checkScreenRecordingPermission())")
