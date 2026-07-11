import SwiftUI

struct WorkspaceVisualFixtureView: View {
    let fixture: WorkspaceVisualFixture

    var body: some View {
        OperationalContentStateView(
            state: contentState,
            title: localizedTitle,
            retryTitle: AppPreferences.localizedString("system.retry", localeIdentifier: fixture.locale.rawValue)
        )
        .frame(minWidth: 640, minHeight: 420)
        .background(AcrossTheme.canvasFill(for: colorScheme))
        .environment(\.colorScheme, colorScheme)
        .environment(\.locale, Locale(identifier: fixture.locale.rawValue))
        .accessibilityIdentifier("workspace-fixture-\(fixture.id)")
    }

    private var colorScheme: ColorScheme {
        fixture.theme == .dark ? .dark : .light
    }

    private var contentState: OperationalContentState {
        switch fixture.state {
        case .loading: return .loading
        case .empty: return .empty
        case .error: return .error(localized("workspace.loadFailed"))
        case .blocked: return .disabled(localized("workspace.unavailable"))
        case .success: return .success(localized("workspace.ready"))
        }
    }

    private var localizedTitle: String {
        switch fixture.state {
        case .loading: return localized("workspace.loading")
        case .empty: return localized("workspace.noRuns")
        case .error: return localized("workspace.loadFailed")
        case .blocked: return localized("workspace.unavailable")
        case .success: return localized("workspace.ready")
        }
    }

    private func localized(_ key: String) -> String {
        AppPreferences.localizedString(key, localeIdentifier: fixture.locale.rawValue)
    }
}
