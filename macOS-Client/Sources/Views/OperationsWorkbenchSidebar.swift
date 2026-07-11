import SwiftUI

struct OperationsWorkbenchSidebar: View {
    @Binding var selection: OperationsWorkbenchSurface
    @ObservedObject var preferences: AppPreferences
    let reviewCount: Int
    let activeProjectName: String?
    let activeProjectPath: String?
    let onOpenAgents: () -> Void
    let onOpenCapabilities: () -> Void
    let onOpenPlugins: () -> Void
    let onOpenSystem: () -> Void

    @Environment(\.colorScheme) private var colorScheme
    @FocusState private var focusedSurface: OperationsWorkbenchSurface?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            sectionLabel(preferences.text("operations.primary"))

            VStack(spacing: 2) {
                ForEach(OperationsWorkbenchSurface.primary) { surface in
                    navigationRow(surface)
                }
            }
            .padding(.horizontal, 8)

            Rectangle()
                .fill(AcrossTheme.separator(for: colorScheme))
                .frame(height: 1)
                .padding(.vertical, 10)

            sectionLabel(preferences.text("operations.review"))

            navigationRow(.humanReview, badge: reviewCount)
                .padding(.horizontal, 8)

            Rectangle()
                .fill(AcrossTheme.separator(for: colorScheme))
                .frame(height: 1)
                .padding(.vertical, 10)

            sectionLabel(preferences.text("operations.manage"))

            VStack(spacing: 2) {
                secondaryRow(
                    systemName: "person.2",
                    title: preferences.text("operations.agents"),
                    action: onOpenAgents
                )
                secondaryRow(
                    systemName: "switch.2",
                    title: preferences.text("operations.capabilities"),
                    action: onOpenCapabilities
                )
                secondaryRow(
                    systemName: "puzzlepiece.extension",
                    title: preferences.text("operations.plugins"),
                    action: onOpenPlugins
                )
                secondaryRow(
                    systemName: "gearshape",
                    title: preferences.text("operations.system"),
                    action: onOpenSystem
                )
            }
            .padding(.horizontal, 8)

            navigationRow(.assist)
                .padding(8)
        }
        .background(AcrossTheme.sidebarFill(for: colorScheme))
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Text(preferences.text("operations.navigation")))
    }

    private func sectionLabel(_ title: String) -> some View {
        Text(title)
            .font(.system(size: 10, weight: .semibold))
            .foregroundStyle(.secondary)
            .padding(.horizontal, 14)
            .padding(.bottom, 6)
    }

    private func navigationRow(_ surface: OperationsWorkbenchSurface, badge: Int? = nil) -> some View {
        Button {
            selection = surface
        } label: {
            HStack(spacing: 9) {
                Image(systemName: surface.systemName)
                    .font(.system(size: 13, weight: .semibold))
                    .frame(width: 18, height: 18)
                    .accessibilityHidden(true)
                Text(preferences.text(surface.localizationKey))
                    .font(.system(size: 12, weight: selection == surface ? .semibold : .medium))
                    .lineLimit(1)
                Spacer()
                if let badge, badge > 0 {
                    Text("\(badge)")
                        .font(.system(size: 10, weight: .bold, design: .rounded))
                        .foregroundStyle(selection == surface ? AcrossTheme.accent : .secondary)
                        .frame(minWidth: 20, minHeight: 18)
                        .background(AcrossTheme.recessedFill(for: colorScheme))
                        .clipShape(RoundedRectangle(cornerRadius: 5))
                }
            }
            .foregroundStyle(selection == surface ? AcrossTheme.accent : Color.primary)
            .padding(.horizontal, 9)
            .frame(maxWidth: .infinity, minHeight: 34, alignment: .leading)
            .background(selection == surface ? AcrossTheme.selectedFill(for: colorScheme) : Color.clear)
            .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .focused($focusedSurface, equals: surface)
        .accessibilityValue(Text(selection == surface ? preferences.text("operations.selected") : ""))
        .help(preferences.text(surface.localizationKey))
    }

    private func secondaryRow(systemName: String, title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 9) {
                Image(systemName: systemName)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .frame(width: 18, height: 18)
                    .accessibilityHidden(true)
                Text(title)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                Spacer()
                Image(systemName: "chevron.right")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundStyle(.tertiary)
                    .accessibilityHidden(true)
            }
            .padding(.horizontal, 9)
            .frame(maxWidth: .infinity, minHeight: 32, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(title)
    }
}
