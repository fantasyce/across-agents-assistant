import SwiftUI

struct HumanReviewQueueView: View {
    let snapshot: HumanReviewQueueSnapshot
    @ObservedObject var preferences: AppPreferences
    let isLoading: Bool
    let errorMessage: String?
    let onRefresh: () -> Void
    let onOpen: (HumanReviewSignal) -> Void

    @Environment(\.colorScheme) private var colorScheme
    @State private var selectedItemId: String?

    var body: some View {
        VStack(spacing: 0) {
            commandBar
            Rectangle()
                .fill(AcrossTheme.separator(for: colorScheme))
                .frame(height: 1)

            if isLoading && snapshot.items.isEmpty {
                OperationalContentStateView(
                    state: .loading,
                    title: preferences.text("review.loading")
                )
            } else if let errorMessage, snapshot.items.isEmpty {
                OperationalContentStateView(
                    state: .error(errorMessage),
                    title: preferences.text("review.unavailable"),
                    retryTitle: preferences.text("system.retry"),
                    retry: onRefresh
                )
            } else if snapshot.items.isEmpty {
                OperationalContentStateView(
                    state: .success(preferences.text("review.empty.detail")),
                    title: preferences.text("review.empty")
                )
            } else {
                HSplitView {
                    queueList
                        .frame(minWidth: 440, maxWidth: .infinity)
                    reviewInspector
                        .frame(minWidth: 270, idealWidth: AcrossTheme.Metrics.inspectorWidth, maxWidth: 370)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AcrossTheme.canvasFill(for: colorScheme))
        .onAppear {
            selectFirstIfNeeded()
        }
        .onChange(of: snapshot.items.map(\.id)) {
            selectFirstIfNeeded()
        }
    }

    private var commandBar: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(preferences.text("review.title"))
                    .font(.system(size: 16, weight: .semibold))
                Text(preferences.text("review.subtitle"))
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            StatusChip(
                status: snapshot.blockingCount > 0 ? "blocked" : "pending",
                label: String(format: preferences.text("review.count"), snapshot.totalCount)
            )
            CommandToolbarButton(
                systemName: "arrow.clockwise",
                accessibilityLabel: preferences.text("review.refresh"),
                help: preferences.text("review.refresh"),
                isDisabled: isLoading
            ) {
                onRefresh()
            }
        }
        .padding(.horizontal, 18)
        .frame(height: 58)
        .background(AcrossTheme.panelFill(for: colorScheme))
    }

    private var queueList: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                ForEach(snapshot.items) { item in
                    Button {
                        selectedItemId = item.id
                    } label: {
                        HStack(alignment: .top, spacing: 10) {
                            Image(systemName: icon(for: item.kind))
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundStyle(StatusPalette.tone(for: item.status).foreground)
                                .frame(width: 22, height: 22)
                                .accessibilityHidden(true)
                            VStack(alignment: .leading, spacing: 3) {
                                HStack(spacing: 7) {
                                    Text(item.title)
                                        .font(.system(size: 12, weight: .semibold))
                                        .foregroundStyle(.primary)
                                        .lineLimit(1)
                                    Text(preferences.text(item.kind.localizationKey))
                                        .font(.system(size: 9, weight: .medium))
                                        .foregroundStyle(.secondary)
                                }
                                Text(item.detail)
                                    .font(.system(size: 11))
                                    .foregroundStyle(.secondary)
                                    .lineLimit(2)
                            }
                            Spacer(minLength: 8)
                            StatusChip(status: item.status)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                        .frame(maxWidth: .infinity, minHeight: 54, alignment: .leading)
                        .background(
                            selectedItemId == item.id
                                ? AcrossTheme.selectedFill(for: colorScheme)
                                : AcrossTheme.panelFill(for: colorScheme)
                        )
                        .contentShape(Rectangle())
                        .overlay(alignment: .bottom) {
                            Rectangle()
                                .fill(AcrossTheme.separator(for: colorScheme))
                                .frame(height: 1)
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(Text(item.title))
                    .accessibilityValue(Text(StatusPalette.displayText(for: item.status)))
                }
            }
        }
        .background(AcrossTheme.panelFill(for: colorScheme))
    }

    private var reviewInspector: some View {
        InspectorPanel(
            title: preferences.text("review.inspector"),
            subtitle: selectedItem.map { preferences.text($0.kind.localizationKey) },
            toolbar: {
                if let selectedItem {
                    StatusChip(status: selectedItem.status)
                }
            },
            content: {
                if let item = selectedItem {
                    VStack(alignment: .leading, spacing: 16) {
                        VStack(alignment: .leading, spacing: 5) {
                            Text(item.title)
                                .font(.system(size: 13, weight: .semibold))
                            Text(item.detail)
                                .font(.system(size: 11))
                                .foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }

                        VStack(alignment: .leading, spacing: 7) {
                            inspectorValue(preferences.text("review.source"), item.source)
                            inspectorValue(preferences.text("review.type"), preferences.text(item.kind.localizationKey))
                            inspectorValue(preferences.text("review.status"), StatusPalette.displayText(for: item.status))
                        }

                        Button(preferences.text("review.open")) {
                            onOpen(item)
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                        .keyboardShortcut(.return, modifiers: [])

                        Text(preferences.text("review.humanBoundary"))
                            .font(.system(size: 10))
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)

                        Spacer()
                    }
                    .padding(14)
                } else {
                    OperationalContentStateView(
                        state: .empty,
                        title: preferences.text("review.select")
                    )
                }
            }
        )
    }

    private var selectedItem: HumanReviewSignal? {
        snapshot.items.first { $0.id == selectedItemId }
    }

    private func selectFirstIfNeeded() {
        if selectedItem == nil {
            selectedItemId = snapshot.items.first?.id
        }
    }

    private func inspectorValue(_ title: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.system(size: 9, weight: .medium))
                .foregroundStyle(.secondary)
            Text(value)
                .font(.system(size: 10, design: .monospaced))
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func icon(for kind: HumanReviewKind) -> String {
        switch kind {
        case .promotion: return "arrow.up.forward.square"
        case .pendingMemory: return "memorychip"
        case .blockingGate: return "xmark.octagon"
        case .manualGate: return "hand.raised"
        case .skippedGate: return "forward.end"
        case .permission: return "lock.shield"
        case .pluginRepair: return "wrench.and.screwdriver"
        }
    }
}

