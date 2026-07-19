import SwiftUI
import AppKit

struct SubtaskCard: View {
    let subtask: TaskOrchestrationViewModel.SubtaskDetail
    let ownerAgentId: String?

    @State private var isHovered = false
    @Environment(\.colorScheme) private var colorScheme
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(subtask.description)
                .font(.system(size: 11))
                .foregroundColor(theme.bodyText)
                .lineLimit(3)
                .multilineTextAlignment(.leading)

            HStack(spacing: 6) {
                AgentIdentityBadge(agentId: subtask.agentId, ownerAgentId: ownerAgentId, size: 22)

                Spacer()

                if subtask.status == "running" {
                    if let runningForSeconds = subtask.runningForSeconds, runningForSeconds >= 1 {
                        Text(formatDuration(runningForSeconds))
                            .font(.system(size: 9))
                            .foregroundColor(AcrossTheme.accent)
                    } else {
                        ProgressView()
                            .controlSize(.mini)
                            .scaleEffect(0.6)
                    }
                } else if let duration = subtask.duration {
                    Text(String(format: "%.1fs", duration))
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                }
            }

            if let blockedText = subtaskBlockedText {
                Text(blockedText)
                    .font(.system(size: 9))
                    .foregroundColor(Color(hex: "#ff9f0a"))
                    .lineLimit(2)
            }

            if subtask.status == "running" {
                GeometryReader { geo in
                    RoundedRectangle(cornerRadius: 2)
                        .fill(theme.controlBackground)
                        .frame(height: 4)
                        .overlay(
                            RoundedRectangle(cornerRadius: 2)
                                .fill(AcrossTheme.accent)
                                .frame(width: geo.size.width * subtask.progress, height: 4)
                        )
                }
                .frame(height: 4)
            }
        }
        .padding(10)
        .frame(width: 200)
        .background(theme.cardBackground)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(theme.divider.opacity(isHovered ? 1 : 0.65), lineWidth: 1)
        )
        .cornerRadius(8)
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.1)) {
                isHovered = hovering
            }
        }
    }

    private var subtaskBlockedText: String? {
        guard subtask.status == "pending" else { return nil }
        if !subtask.waitingOnDependencies.isEmpty {
            return "Waiting for " + subtask.waitingOnDependencies.prefix(2).joined(separator: ", ")
        }
        guard let blockedReason = subtask.blockedReason else { return nil }
        switch blockedReason {
        case "blocked_by_prior_wave":
            return "Blocked by prior wave"
        case "wave_revalidating":
            return "Wave revalidating"
        case "wave_gate_blocked":
            return "Wave gate blocked"
        default:
            return blockedReason.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    private func formatDuration(_ seconds: Double) -> String {
        if seconds >= 60 {
            return String(format: "%.0fm", seconds / 60)
        }
        return String(format: "%.0fs", seconds)
    }
}

struct FixRoundView: View {
    let fixRound: TaskOrchestrationViewModel.FixRoundDetail
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: "wrench.fill")
                .font(.system(size: 10))
                .foregroundColor(Color(hex: "#ff9f0a"))

            Text(String(format: appPreferences.text("tasks.fixRound"), fixRound.roundNumber))
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(theme.bodyText)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Color(hex: "#ff9f0a").opacity(0.15))
        .cornerRadius(6)
    }
}

struct SubtaskDetailSheet: View {
    let subtask: TaskOrchestrationViewModel.SubtaskDetail

    @Environment(\.dismiss) private var dismiss
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text(appPreferences.text("tasks.subtaskDetails"))
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(theme.primaryText)

                Spacer()

                Button(action: { dismiss() }) {
                    Image(systemName: "xmark")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(appPreferences.text("tasks.description"))
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.secondary)

                        Text(subtask.description)
                            .font(.system(size: 13))
                            .foregroundColor(theme.primaryText)
                    }

                    HStack(spacing: 20) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(appPreferences.text("tasks.status"))
                                .font(.system(size: 11))
                                .foregroundColor(.secondary)

                            Text(localizedTaskStatus(subtask.status, preferences: appPreferences))
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(statusColor)
                        }

                        VStack(alignment: .leading, spacing: 4) {
                            Text(appPreferences.text("tasks.agent"))
                                .font(.system(size: 11))
                                .foregroundColor(.secondary)

                            Text(subtask.agentId)
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(theme.primaryText)
                        }

                        if let duration = subtask.duration {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(appPreferences.text("tasks.duration"))
                                    .font(.system(size: 11))
                                    .foregroundColor(.secondary)

                                Text(String(format: "%.1fs", duration))
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(theme.primaryText)
                            }
                        }

                        if subtask.status == "running", let runningForSeconds = subtask.runningForSeconds {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(appPreferences.text("tasks.runningFor"))
                                    .font(.system(size: 11))
                                    .foregroundColor(.secondary)

                                Text(String(format: "%.0fs", runningForSeconds))
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(AcrossTheme.accent)
                            }
                        }
                    }

                    if !subtask.waitingOnDependencies.isEmpty || subtask.blockedReason != nil {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(appPreferences.text("tasks.waitingState"))
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(Color(hex: "#ff9f0a"))

                            if !subtask.waitingOnDependencies.isEmpty {
                                Text(String(format: appPreferences.text("tasks.waitingOn"), subtask.waitingOnDependencies.joined(separator: ", ")))
                                    .font(.system(size: 12, design: .monospaced))
                                    .foregroundColor(theme.primaryText)
                            }

                            if let blockedReason = subtask.blockedReason {
                                Text(blockedReason.replacingOccurrences(of: "_", with: " ").capitalized)
                                    .font(.system(size: 12))
                                    .foregroundColor(theme.bodyText)
                            }
                        }
                        .padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color(hex: "#ff9f0a").opacity(0.1))
                        .cornerRadius(8)
                    }

                    if let outputFile = subtask.outputFile {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(appPreferences.text("tasks.outputFile"))
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(.secondary)

                            Text(outputFile)
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundColor(Color(hex: "#30d158"))
                                .padding(8)
                                .background(Color(hex: "#30d158").opacity(0.1))
                                .cornerRadius(6)
                        }
                    }

                    if let errorMessage = subtask.errorMessage {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(appPreferences.text("tasks.errorMessage"))
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(Color(hex: "#FF453A"))

                            Text(errorMessage)
                                .font(.system(size: 12, design: .monospaced))
                                .foregroundColor(theme.primaryText)
                                .padding(10)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color(hex: "#FF453A").opacity(0.1))
                                .cornerRadius(8)
                        }
                    }

                    if let fixPlan = subtask.fixPlan {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(appPreferences.text("tasks.fixPlan"))
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(Color(hex: "#ff9f0a"))

                            Text(fixPlan)
                                .font(.system(size: 12))
                                .foregroundColor(theme.primaryText)
                                .padding(10)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color(hex: "#ff9f0a").opacity(0.1))
                                .cornerRadius(8)
                        }
                    }
                }
            }
        }
        .padding(20)
        .frame(width: 500, height: 400)
        .background(theme.panelBackground)
    }

    private var statusColor: Color {
        switch subtask.status {
        case "running": return AcrossTheme.accent
        case "completed": return Color(hex: "#30d158")
        case "failed": return Color(hex: "#FF453A")
        case "pending": return Color(hex: "#8e8e93")
        default: return Color(hex: "#8e8e93")
        }
    }
}

func ownerDecisionText(_ decision: TaskOrchestrationViewModel.OwnerDecisionSummary) -> String {
    let action = decision.recommendedAction?.replacingOccurrences(of: "_", with: " ").capitalized ?? "Owner Decision"
    if let rootScope = decision.rootCauseScope, let rootWave = decision.rootCauseWave {
        return "\(action) · \(rootScope.replacingOccurrences(of: "_", with: " ")) W\(rootWave)"
    }
    if let rootScope = decision.rootCauseScope {
        return "\(action) · \(rootScope.replacingOccurrences(of: "_", with: " "))"
    }
    return action
}

@MainActor
func localizedTaskStatus(_ status: String, preferences: AppPreferences) -> String {
    let key = "status.\(status)"
    let localized = preferences.text(key)
    if localized != key {
        return localized
    }
    return status
        .split(separator: "_")
        .map { $0.prefix(1).uppercased() + $0.dropFirst() }
        .joined(separator: " ")
}
