import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct GrowthAssetManifestTests {
    @Test func productionGrowthAssetsHaveAcrossOwnedProvenance() throws {
        let url = try #require(Bundle.module.url(
            forResource: "asset-manifest",
            withExtension: "json",
            subdirectory: "Assets/growth"
        ))
        let data = try Data(contentsOf: url)
        let object = try #require(
            JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        let atlases = try #require(object["atlases"] as? [[String: Any]])
        let raw = String(decoding: data, as: UTF8.self).lowercased()

        #expect(object["owner"] as? String == "Across Agents Assistant")
        #expect(atlases.count == 7)
        #expect(Set(atlases.compactMap { $0["file"] as? String }) == Set([
            "capability-atlas.png",
            "achievement-atlas.png",
            "achievement-milestones-atlas.png",
            "journey-node-atlas.png",
            "status-companion-atlas.png",
            "trust-seal-atlas.png",
            "challenge-reward-atlas.png",
        ]))
        #expect(!raw.contains("homerail"))
        #expect(!raw.contains("xiaotianfotos"))
    }

    @Test func generatedAtlasValidationCoversRequiredSizesAndModes() throws {
        let url = try #require(Bundle.module.url(
            forResource: "asset-validation",
            withExtension: "json",
            subdirectory: "Assets/growth"
        ))
        let object = try #require(
            JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any]
        )
        let atlases = try #require(object["atlases"] as? [[String: Any]])
        let sizes = try #require(object["validation_sizes"] as? [Int])
        let modes = try #require(object["background_modes"] as? [String])

        #expect(atlases.count == 4)
        #expect(Set(sizes) == Set([48, 64, 96]))
        #expect(Set(modes) == Set(["light", "dark"]))
        #expect(atlases.allSatisfy { ($0["output_sha256"] as? String)?.count == 64 })
    }
}
