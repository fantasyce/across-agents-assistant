import SwiftUI
import AppKit

struct SubtaskListView: View {
    let task: TaskOrchestrationViewModel.TaskDetail
    @ObservedObject var viewModel: TaskOrchestrationViewModel
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(String(format: appPreferences.text("tasks.subtasks"), task.subtasks.count))
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(theme.primaryText)

            VStack(spacing: 8) {
                ForEach(task.subtasks) { subtask in
                    SubtaskCard(subtask: subtask, ownerAgentId: task.ownerAgent)
                }
            }
        }
    }
}

struct DAGVisualization: View {
    let task: TaskOrchestrationViewModel.TaskDetail
    @ObservedObject var viewModel: TaskOrchestrationViewModel

    @State private var selectedSubtask: TaskOrchestrationViewModel.SubtaskDetail?
    @State private var isProgressExpanded = true
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Button(action: { isProgressExpanded.toggle() }) {
                HStack(spacing: 6) {
                    Text(appPreferences.text("tasks.progress"))
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(theme.primaryText)

                    HStack(alignment: .bottom, spacing: 1) {
                        Rectangle()
                            .fill(Color(hex: "#FFBFBB"))
                            .frame(width: 3, height: 8)
                            .cornerRadius(1)
                        Rectangle()
                            .fill(Color(hex: "#FFE4AB"))
                            .frame(width: 3, height: 10)
                            .cornerRadius(1)
                        Rectangle()
                            .fill(Color(hex: "#A8E9B2"))
                            .frame(width: 3, height: 12)
                            .cornerRadius(1)
                    }

                    Image(systemName: isProgressExpanded ? "chevron.down" : "chevron.right")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.secondary)

                    Spacer()
                }
            }
            .buttonStyle(.plain)

            if isProgressExpanded {
                ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 0) {
                    ForEach(Array(task.waves.enumerated()), id: \.element.waveId) { index, wave in
                        WaveColumnView(
                            wave: wave,
                            isBlocked: wave.isBlocked,
                            ownerAgentId: task.ownerAgent,
                            onSubtaskTap: { subtask in
                                selectedSubtask = subtask
                            }
                        )

                        if index < task.waves.count - 1 {
                            Image(systemName: "arrow.right")
                                .font(.system(size: 14))
                                .foregroundColor(.secondary.opacity(0.4))
                                .padding(.horizontal, 12)
                                .padding(.top, 24)
                        }
                    }
                }
                .padding(.vertical, 8)
                }
            }
        }
        .sheet(item: $selectedSubtask) { subtask in
            SubtaskDetailSheet(subtask: subtask)
        }
    }
}

struct WaveColumnView: View {
    let wave: TaskOrchestrationViewModel.WaveDetail
    let isBlocked: Bool
    let ownerAgentId: String?
    let onSubtaskTap: (TaskOrchestrationViewModel.SubtaskDetail) -> Void
    @Environment(\.colorScheme) private var colorScheme
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Text(wave.waveNumber == 0 ? "Wave 0" : "Wave \(wave.waveNumber)")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.secondary)

                Circle()
                    .fill(statusColor)
                    .frame(width: 6, height: 6)

                Spacer()

                if wave.isRevalidating {
                    Image(systemName: "arrow.triangle.2.circlepath")
                        .font(.system(size: 10))
                        .foregroundColor(Color(hex: "#4d6bfe"))
                }

                if isBlocked {
                    Image(systemName: "lock.fill")
                        .font(.system(size: 10))
                        .foregroundColor(Color(hex: "#ff9f0a"))
                }

                if let governanceStatus = wave.governanceStatus, governanceStatus != "pending" {
                    Text(governanceStatusText(governanceStatus, blockedByWave: wave.blockedByWave))
                        .font(.system(size: 10))
                        .foregroundColor(governanceColor(governanceStatus))
                        .lineLimit(1)
                }
            }

            if let ownerDecision = wave.ownerDecision,
               let action = ownerDecision.recommendedAction,
               action != "approve" {
                HStack {
                    Spacer()
                    Text(ownerDecisionText(ownerDecision))
                        .font(.system(size: 10))
                        .foregroundColor(Color(hex: "#ff9f0a"))
                        .lineLimit(2)
                }
            }

            if !wave.subtasks.isEmpty {
                VStack(spacing: 8) {
                    ForEach(wave.subtasks) { subtask in
                        SubtaskCard(subtask: subtask, ownerAgentId: ownerAgentId)
                            .onTapGesture {
                                onSubtaskTap(subtask)
                            }
                    }
                }
                .opacity(isBlocked ? 0.5 : 1)
            }

            if let fixRounds = wave.fixRounds {
                ForEach(fixRounds) { fixRound in
                    FixRoundView(fixRound: fixRound)
                }
            }
        }
        .padding(12)
        .background(theme.subtleBackground)
        .cornerRadius(12)
    }

    private var statusColor: Color {
        if wave.isRevalidating {
            return Color(hex: "#4d6bfe")
        }
        switch wave.governanceStatus ?? wave.status {
        case "revalidating": return Color(hex: "#4d6bfe")
        case "blocked", "blocked_by_prior_wave", "needs_fix": return Color(hex: "#ff9f0a")
        case "running": return Color(hex: "#4d6bfe")
        case "completed": return Color(hex: "#30d158")
        case "failed": return Color(hex: "#FF453A")
        default: return Color(hex: "#8e8e93")
        }
    }

    private func governanceStatusText(_ status: String, blockedByWave: Int?) -> String {
        switch status {
        case "approved":
            return "Wave Gate Approved"
        case "blocked":
            if let blockedByWave {
                return "Blocked by Wave \(blockedByWave)"
            }
            return "Wave Gate Blocked"
        case "revalidating":
            return "Revalidating Downstream"
        case "needs_fix":
            return "Needs Fix"
        default:
            return status.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    private func governanceColor(_ status: String) -> Color {
        switch status {
        case "approved":
            return Color(hex: "#30d158")
        case "blocked", "needs_fix":
            return Color(hex: "#ff9f0a")
        case "revalidating":
            return Color(hex: "#4d6bfe")
        default:
            return .secondary
        }
    }
}

