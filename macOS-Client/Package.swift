// swift-tools-version: 5.10
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
        ),
        .testTarget(
            name: "AcrossAgentsAssistantClientTests",
            dependencies: ["AcrossAgentsAssistantClient"],
            path: "Tests/AcrossAgentsAssistantClientTests",
            swiftSettings: [
                .unsafeFlags([
                    "-F",
                    "/Library/Developer/CommandLineTools/Library/Developer/Frameworks",
                ])
            ],
            linkerSettings: [
                .unsafeFlags([
                    "-F",
                    "/Library/Developer/CommandLineTools/Library/Developer/Frameworks",
                    "-framework",
                    "Testing",
                    "-Xlinker",
                    "-rpath",
                    "-Xlinker",
                    "/Library/Developer/CommandLineTools/Library/Developer/Frameworks",
                    "-Xlinker",
                    "-rpath",
                    "-Xlinker",
                    "/Library/Developer/CommandLineTools/Library/Developer/usr/lib",
                ])
            ]
        )
    ],
    swiftLanguageVersions: [.v5]
)
