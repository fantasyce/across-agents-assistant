// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "AcrossAgentsAssistant",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "AcrossAgentsAssistantClient", targets: ["AcrossAgentsAssistantClient"])
    ],
    dependencies: [
        .package(url: "https://github.com/soffes/HotKey", from: "0.2.0")
    ],
    targets: [
        .executableTarget(
            name: "AcrossAgentsAssistantClient",
            dependencies: ["HotKey"],
            path: "Sources",
            resources: [.copy("Assets")]
        )
    ]
)
