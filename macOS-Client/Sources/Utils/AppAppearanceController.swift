import AppKit

@MainActor
enum AppAppearanceController {
    static func apply(_ mode: AppColorSchemeMode) {
        let appearance = nsAppearance(for: mode)
        NSApp.appearance = appearance
        for window in NSApp.windows {
            window.appearance = appearance
        }
    }

    private static func nsAppearance(for mode: AppColorSchemeMode) -> NSAppearance? {
        switch mode {
        case .followSystem:
            return nil
        case .light:
            return NSAppearance(named: .aqua)
        case .dark:
            return NSAppearance(named: .darkAqua)
        }
    }
}
