import Foundation
import OSLog

enum StartupTelemetry {
    private static let processStartedAt = ProcessInfo.processInfo.systemUptime
    private static let instanceID = UUID().uuidString.lowercased()
    private static let writerQueue = DispatchQueue(label: "app.acrossagents.assistant.startup-telemetry")
    private static let logger = Logger(
        subsystem: Bundle.main.bundleIdentifier ?? "com.fanhcy.across-agents-assistant",
        category: "Startup"
    )

    static func mark(_ stage: String) {
        let elapsedMilliseconds = max(
            0,
            Int((ProcessInfo.processInfo.systemUptime - processStartedAt) * 1_000)
        )
        logger.info(
            "startup stage=\(stage, privacy: .public) elapsed_ms=\(elapsedMilliseconds, privacy: .public)"
        )
        let payload: [String: Any] = [
            "schema_version": "across-aaa-startup-timing/1.0",
            "instance_id": instanceID,
            "timestamp": ISO8601DateFormatter().string(from: Date()),
            "stage": stage,
            "elapsed_ms": elapsedMilliseconds,
        ]
        writerQueue.async {
            guard let data = try? JSONSerialization.data(withJSONObject: payload),
                  var line = String(data: data, encoding: .utf8)?.data(using: .utf8) else { return }
            line.append(0x0A)
            let url = LocalAppPaths.logFile("startup_timing.jsonl")
            if !FileManager.default.fileExists(atPath: url.path) {
                try? line.write(to: url, options: .atomic)
                return
            }
            guard let handle = try? FileHandle(forWritingTo: url) else { return }
            defer { try? handle.close() }
            do {
                try handle.seekToEnd()
                try handle.write(contentsOf: line)
            } catch {
                return
            }
        }
    }
}
