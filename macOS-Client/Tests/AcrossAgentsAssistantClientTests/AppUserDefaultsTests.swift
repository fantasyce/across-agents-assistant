import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct AppUserDefaultsTests {
    @Test
    func productionEnvironmentKeepsProvidedStandardDomain() {
        let fallback = UserDefaults(suiteName: "app.acrossagents.tests.fallback")!
        defer { fallback.removePersistentDomain(forName: "app.acrossagents.tests.fallback") }

        let selected = AppUserDefaults.make(environment: [:], fallback: fallback)

        #expect(selected === fallback)
    }

    @Test
    func matchingStudyProfileSelectsAnIsolatedSuite() {
        let profile = "0123456789abcdef"
        let suite = "app.acrossagents.assistant.beginner-study.\(profile)"
        let fallback = UserDefaults(suiteName: "app.acrossagents.tests.fallback-study")!
        defer {
            fallback.removePersistentDomain(forName: "app.acrossagents.tests.fallback-study")
            UserDefaults.standard.removePersistentDomain(forName: suite)
        }

        let selected = AppUserDefaults.make(
            environment: [
                "ACROSS_STUDY_PROFILE_ID": profile,
                "ACROSS_AGENTS_PREFERENCES_SUITE": suite,
            ],
            fallback: fallback
        )
        selected.set("isolated", forKey: "marker")

        #expect(selected !== fallback)
        #expect(selected.string(forKey: "marker") == "isolated")
        #expect(fallback.string(forKey: "marker") == nil)
    }

    @Test
    func mismatchedOrUnboundedSuiteCannotSelectAnotherDomain() {
        let fallback = UserDefaults(suiteName: "app.acrossagents.tests.fallback-invalid")!
        defer { fallback.removePersistentDomain(forName: "app.acrossagents.tests.fallback-invalid") }

        let selected = AppUserDefaults.make(
            environment: [
                "ACROSS_STUDY_PROFILE_ID": "0123456789abcdef",
                "ACROSS_AGENTS_PREFERENCES_SUITE": "app.acrossagents.assistant.beginner-study.ffffffffffffffff",
            ],
            fallback: fallback
        )

        #expect(selected === fallback)
    }
}
