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
        AppPreferences.localizedString("plugins.loop.eventSequence", localeIdentifier: "en") == "Sequence",
        "Agent Loop event sequence label should be localized in English"
    )
    assert(
        AppPreferences.localizedString("plugins.loop.correlationId", localeIdentifier: "zh-Hans") == "关联",
        "Agent Loop event correlation label should be localized in Simplified Chinese"
    )
    assert(
        AppPreferences.localizedString("plugins.loop.leaseStale", localeIdentifier: "en") == "Lease stale",
        "Agent Loop stale lease marker should be localized in English"
    )
    assert(
        AppPreferences.localizedString("plugins.loop.healthDetails", localeIdentifier: "zh-Hans") == "Loop 健康详情",
        "Agent Loop health detail popover should be localized in Simplified Chinese"
    )
    assert(
        AppPreferences.localizedString("plugins.loop.detailCancellation", localeIdentifier: "en") == "Cancellation",
        "Agent Loop cancellation detail label should be localized in English"
    )
    assert(
        AppPreferences.localizedString("plugins.loop.detailRouting", localeIdentifier: "zh-Hans") == "路由",
        "Agent Loop evidence routing label should be localized in Simplified Chinese"
    )
    assert(
        AppPreferences.localizedString("plugins.loop.auditComplete", localeIdentifier: "en") == "%d events complete",
        "Agent Loop evidence audit summary should be localized in English"
    )
    assert(
        AppPreferences.localizedString("plugins.loop.detailRecoveryPolicy", localeIdentifier: "en") == "Policy",
        "Agent Loop recovery policy detail label should be localized in English"
    )
    assert(
        AppPreferences.localizedString("plugins.loop.recoveryApplied", localeIdentifier: "zh-Hans") == "已应用",
        "Agent Loop recovery decision state should be localized in Simplified Chinese"
    )
    assert(
        AppPreferences.localizedString("plugins.loop.detailMemoryCandidate", localeIdentifier: "en") == "Candidate",
        "Agent Loop memory candidate detail label should be localized in English"
    )
    assert(
        AppPreferences.localizedString("plugins.loop.memoryCandidateTurn", localeIdentifier: "zh-Hans") == "第 %d 轮",
        "Agent Loop memory candidate turn should be localized in Simplified Chinese"
    )
    assert(
        AppPreferences.localizedString("plugins.memory.loopCandidates", localeIdentifier: "en") == "Loop memory candidates",
        "Agent Loop memory candidate list label should be localized in English"
    )
    assert(
        AppPreferences.localizedString("plugins.memory.focusCandidate", localeIdentifier: "zh-Hans") == "定位记忆审核",
        "Agent Loop memory candidate focus action should be localized in Simplified Chinese"
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
