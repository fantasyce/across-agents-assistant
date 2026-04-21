// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "AcrossAgentsAssistant",
    platforms: [
        .macOS(.v13)
    ],
    products: [
        .executable(name: "AcrossAgentsAssistantClient", targets: ["AcrossAgentsAssistantClient"])
    ],
    dependencies: [],
    targets: [
        .executableTarget(
            name: "AcrossAgentsAssistantClient",
            dependencies: [],
            path: "Sources"
        )
    ]
)
