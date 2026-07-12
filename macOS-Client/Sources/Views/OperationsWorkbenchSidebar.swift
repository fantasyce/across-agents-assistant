import SwiftUI

struct OperationsWorkbenchSidebar<MiddleContent: View>: View {
    @Binding var selection: OperationsWorkbenchSurface
    @ObservedObject var preferences: AppPreferences
    let reviewCount: Int
    let capabilitySurfaces: [OperationsWorkbenchSurface]
    let activeProjectName: String?
    let activeProjectPath: String?
    let onOpenSettings: () -> Void
    private let middleContent: MiddleContent

    @Environment(\.colorScheme) private var colorScheme
    @FocusState private var focusedSurface: OperationsWorkbenchSurface?

    init(
        selection: Binding<OperationsWorkbenchSurface>,
        preferences: AppPreferences,
        reviewCount: Int,
        capabilitySurfaces: [OperationsWorkbenchSurface],
        activeProjectName: String?,
        activeProjectPath: String?,
        onOpenSettings: @escaping () -> Void,
        @ViewBuilder middleContent: () -> MiddleContent
    ) {
        _selection = selection
        self.preferences = preferences
        self.reviewCount = reviewCount
        self.capabilitySurfaces = capabilitySurfaces
        self.activeProjectName = activeProjectName
        self.activeProjectPath = activeProjectPath
        self.onOpenSettings = onOpenSettings
        self.middleContent = middleContent()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(spacing: 4) {
                ForEach(OperationsWorkbenchSurface.primary) { surface in
                    navigationRow(surface)
                }
                if reviewCount > 0 {
                    navigationRow(.humanReview, badge: reviewCount)
                }
                ForEach(capabilitySurfaces) { surface in
                    navigationRow(surface)
                }
            }
            .padding(.horizontal, 10)

            middleContent

            Spacer(minLength: 12)

            settingsRow
                .padding(.horizontal, 10)
                .padding(.bottom, 10)
        }
        .background(AcrossTheme.sidebarFill(for: colorScheme))
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text(preferences.text("operations.navigation")))
    }

    private func navigationRow(_ surface: OperationsWorkbenchSurface, badge: Int? = nil) -> some View {
        Button {
            selection = surface
        } label: {
            HStack(spacing: 9) {
                Image(systemName: surface.systemName)
                    .font(.system(size: 14, weight: .medium))
                    .frame(width: 20, height: 20)
                    .accessibilityHidden(true)
                Text(preferences.text(surface.localizationKey))
                    .font(.system(size: 13, weight: selection == surface ? .semibold : .regular))
                    .lineLimit(1)
                Spacer()
                if let badge, badge > 0 {
                    Text("\(badge)")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(selection == surface ? AcrossTheme.accent : .secondary)
                        .frame(minWidth: 20, minHeight: 18)
                        .background(AcrossTheme.recessedFill(for: colorScheme))
                        .clipShape(RoundedRectangle(cornerRadius: 5))
                }
            }
            .foregroundStyle(selection == surface ? AcrossTheme.accent : Color.primary)
            .padding(.horizontal, 10)
            .frame(maxWidth: .infinity, minHeight: 38, alignment: .leading)
            .background(selection == surface ? AcrossTheme.selectedFill(for: colorScheme) : Color.clear)
            .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .focused($focusedSurface, equals: surface)
        .accessibilityValue(Text(selection == surface ? preferences.text("operations.selected") : ""))
        .help(preferences.text(surface.localizationKey))
    }

    private var settingsRow: some View {
        Button(action: onOpenSettings) {
            HStack(spacing: 9) {
                Image(systemName: "gearshape")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(.secondary)
                    .frame(width: 20, height: 20)
                    .accessibilityHidden(true)
                Text(preferences.text("settings.title"))
                    .font(.system(size: 13, weight: .regular))
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                Spacer()
            }
            .padding(.horizontal, 10)
            .frame(maxWidth: .infinity, minHeight: 38, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(preferences.text("settings.title"))
    }
}
