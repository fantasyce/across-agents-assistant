import Foundation

// Standalone behavior binaries compile a deliberately small source subset.
// Production builds use Utils/LocalAppPaths.swift; these tests always inject
// explicit file URLs and need only a harmless fallback to satisfy type checking.
enum LocalAppPaths {
    static let root = FileManager.default.temporaryDirectory
        .appendingPathComponent("across-standalone-behavior", isDirectory: true)
        .appendingPathComponent(".across/data/across-agents-assistant", isDirectory: true)
    static let acrossRoot = FileManager.default.temporaryDirectory
        .appendingPathComponent("across-standalone-behavior/.across", isDirectory: true)
}
