import Foundation

/// Keeps normal installs on the standard preference domain while allowing a
/// supervised beginner-study launch to use a unique, disposable domain.
///
/// `HOME` does not isolate Core Foundation preferences on macOS, so the study
/// runner supplies a narrowly validated suite name in addition to its private
/// HOME and ACROSS_HOME. Arbitrary suite names are deliberately ignored.
enum AppUserDefaults {
    static let studyProfileEnvironmentKey = "ACROSS_STUDY_PROFILE_ID"
    static let studySuiteEnvironmentKey = "ACROSS_AGENTS_PREFERENCES_SUITE"
    static let studySuitePrefix = "app.acrossagents.assistant.beginner-study."

    static let current: UserDefaults = make(
        environment: ProcessInfo.processInfo.environment,
        fallback: .standard
    )

    static func studySuiteName(environment: [String: String]) -> String? {
        guard let profileID = environment[studyProfileEnvironmentKey]?.trimmingCharacters(in: .whitespacesAndNewlines),
              profileID.range(of: #"^[a-f0-9]{16}$"#, options: .regularExpression) != nil,
              let raw = environment[studySuiteEnvironmentKey]?.trimmingCharacters(in: .whitespacesAndNewlines),
              raw.hasPrefix(studySuitePrefix) else {
            return nil
        }
        let suffix = String(raw.dropFirst(studySuitePrefix.count))
        guard suffix == profileID else {
            return nil
        }
        return raw
    }

    static func make(
        environment: [String: String],
        fallback: UserDefaults
    ) -> UserDefaults {
        guard let suiteName = studySuiteName(environment: environment),
              let isolated = UserDefaults(suiteName: suiteName) else {
            return fallback
        }
        return isolated
    }
}
