import Foundation

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

func testPermissionStateTitlesAreLocalized() {
    assert(
        ToolPermissionState.alwaysAllow.title(localeIdentifier: "zh-Hans") == "永久授权",
        "Always-allow should have a Simplified Chinese title"
    )
    assert(
        ToolPermissionState.askEveryTime.title(localeIdentifier: "zh-Hans") == "每次询问",
        "Ask-every-time should have a Simplified Chinese title"
    )
    assert(
        ToolPermissionState.unavailable.title(localeIdentifier: "en") == "Never",
        "Unavailable should use the current English permission label"
    )
}

func testCatalogOnlyShowsRuntimeSchemas() {
    let cards = ToolPermissionCatalog.makeCards(
        schemas: [
            ToolPermissionSchema(
                name: "list_directory",
                description: "List the contents of a local directory.",
                riskLevel: "low",
                scope: .local
            )
        ],
        permissionTypes: [:],
        enabledMCPServerIds: []
    )

    assert(cards.map(\.id) == ["list_directory"], "Catalog should not invent fallback tools")
    assert(cards[0].isRuntimeAvailable, "Fetched local schemas should be runtime available")
}

func testCatalogUsesFetchedMcpSchemasOnly() {
    let cards = ToolPermissionCatalog.makeCards(
        schemas: [
            ToolPermissionSchema(
                name: "sqlite__sqlite_query",
                description: "Query SQLite.",
                riskLevel: "medium",
                scope: .mcp
            )
        ],
        permissionTypes: [:],
        enabledMCPServerIds: []
    )

    assert(cards.map(\.id) == ["sqlite__sqlite_query"], "Catalog should show connected MCP tool schemas only")
    assert(cards[0].state == .askEveryTime, "Fetched MCP tools should be configurable by default")
}

func testCatalogUsesStableCardRhythmAcrossLocales() {
    let zh = ToolPermissionCardRhythm.metrics(localeIdentifier: "zh-Hans")
    let en = ToolPermissionCardRhythm.metrics(localeIdentifier: "en")

    assert(zh.cardHeight == en.cardHeight, "Card height should not change between Chinese and English")
    assert(zh.descriptionHeight == en.descriptionHeight, "Description height should not change between Chinese and English")
}

func testCardRhythmPlacesDescriptionCloserToRiskThanHeader() {
    let metrics = ToolPermissionCardRhythm.metrics(localeIdentifier: "zh-Hans")

    assert(
        metrics.headerToDescriptionSpacing > metrics.descriptionToRiskSpacing,
        "Description should sit farther from the header than from the risk label"
    )
}

func testAskPermissionStyleIsSofterThanAlwaysAllow() {
    let always = ToolPermissionVisualStyle.permissionChrome(for: .alwaysAllow)
    let ask = ToolPermissionVisualStyle.permissionChrome(for: .askEveryTime)
    let unavailable = ToolPermissionVisualStyle.permissionChrome(for: .unavailable)

    assert(
        ask.backgroundOpacity < always.backgroundOpacity,
        "Ask-every-time should use a softer background than always-allow"
    )
    assert(
        ask.borderOpacity < always.borderOpacity,
        "Ask-every-time should use a softer border than always-allow"
    )
    assert(
        unavailable.backgroundOpacity < ask.backgroundOpacity,
        "Unavailable should remain the quietest state"
    )
}

@main
struct ToolPermissionCatalogBehavior {
    static func main() {
        testPermissionStateTitlesAreLocalized()
        testCatalogOnlyShowsRuntimeSchemas()
        testCatalogUsesFetchedMcpSchemasOnly()
        testCatalogUsesStableCardRhythmAcrossLocales()
        testCardRhythmPlacesDescriptionCloserToRiskThanHeader()
        testAskPermissionStyleIsSofterThanAlwaysAllow()
        print("ToolPermissionCatalogBehavior passed")
    }
}
