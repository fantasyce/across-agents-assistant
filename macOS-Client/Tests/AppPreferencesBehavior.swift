import Foundation

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

func testLanguageResolution() {
    assert(
        AppPreferences.resolveLocaleIdentifier(mode: .followSystem, preferredLanguages: ["zh-Hans-CN"]) == "zh-Hans",
        "Chinese system languages should resolve to Simplified Chinese"
    )
    assert(
        AppPreferences.resolveLocaleIdentifier(mode: .followSystem, preferredLanguages: ["fr-FR"]) == "en",
        "Unsupported system languages should resolve to English"
    )
    assert(
        AppPreferences.resolveLocaleIdentifier(mode: .english, preferredLanguages: ["zh-Hans-CN"]) == "en",
        "Manual English should override the system language"
    )
    assert(
        AppPreferences.resolveLocaleIdentifier(mode: .simplifiedChinese, preferredLanguages: ["en-US"]) == "zh-Hans",
        "Manual Simplified Chinese should override the system language"
    )
}

func testLocalizedStringsFallbackToEnglish() {
    assert(
        AppPreferences.localizedString("settings.title", localeIdentifier: "zh-Hans") == "设置",
        "Simplified Chinese labels should be available"
    )
    assert(
        AppPreferences.localizedString("settings.title", localeIdentifier: "en") == "Settings",
        "English labels should be available"
    )
    assert(
        AppPreferences.localizedString("settings.diagnostics", localeIdentifier: "zh-Hans") == "诊断",
        "Diagnostics tab should be localized in Simplified Chinese"
    )
    assert(
        AppPreferences.localizedString("diagnostics.status.warning", localeIdentifier: "en") == "Warning",
        "Diagnostics status labels should be localized in English"
    )
    assert(
        AppPreferences.localizedString("releaseVerification.run", localeIdentifier: "en") == "Run RC Check",
        "RC verification action should be localized in English"
    )
    assert(
        AppPreferences.localizedString("releaseVerification.run", localeIdentifier: "zh-Hans") == "运行 RC 验收",
        "RC verification action should be localized in Simplified Chinese"
    )
    assert(
        AppPreferences.localizedString("plugins.loop.runtime", localeIdentifier: "en") == "Agent Loop",
        "Agent Loop plugin capability label should be localized in English"
    )
    assert(
        AppPreferences.localizedString("plugins.loop.probe", localeIdentifier: "zh-Hans") == "运行 Agent Loop 探测",
        "Agent Loop probe action should be localized in Simplified Chinese"
    )
    assert(
        AppPreferences.localizedString("plugins.loop.events", localeIdentifier: "en") == "Events",
        "Agent Loop events timeline label should be localized in English"
    )
    assert(
        AppPreferences.localizedString("plugins.loop.events", localeIdentifier: "zh-Hans") == "事件",
        "Agent Loop events timeline label should be localized in Simplified Chinese"
    )
    assert(
        AppPreferences.localizedString("plugins.loop.eventsLive", localeIdentifier: "en") == "Live",
        "Agent Loop live timeline source should be localized in English"
    )
    assert(
        AppPreferences.localizedString("plugins.loop.eventsSnapshot", localeIdentifier: "zh-Hans") == "快照",
        "Agent Loop snapshot timeline source should be localized in Simplified Chinese"
    )
    assert(
        AppPreferences.localizedString("missing.key", localeIdentifier: "zh-Hans") == "missing.key",
        "Missing labels should fall back without becoming empty"
    )
}

@main
struct AppPreferencesBehavior {
    static func main() {
        testLanguageResolution()
        testLocalizedStringsFallbackToEnglish()
        print("AppPreferencesBehavior passed")
    }
}
