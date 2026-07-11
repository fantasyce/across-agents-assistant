import SwiftUI
import AppKit

struct BackendUnavailableBanner: View {
    let message: String?
    let onRetry: () -> Void

    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(Color(hex: "#FF9F0A"))
                .frame(width: 16, height: 16)

            VStack(alignment: .leading, spacing: 6) {
                Text(appPreferences.text("tasks.backendUnavailable.title"))
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(theme.strongText)

                Text(message?.isEmpty == false ? message! : appPreferences.text("tasks.backendUnavailable.sidebar"))
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                    .lineLimit(3)

                Button(action: onRetry) {
                    Text(appPreferences.text("tasks.backendUnavailable.retry"))
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(Color(hex: "#4D6BFE"))
                }
                .buttonStyle(.plain)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(10)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(theme.hoverBackground)
        )
    }
}

struct TaskRowView: View {
    let task: TaskOrchestrationViewModel.TaskSummary
    let isSelected: Bool
    let onTap: () -> Void

    @State private var isHovered = false
    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    private var statusColor: Color {
        switch task.status {
        case "running": return Color(hex: "#4d6bfe")
        case "completed": return Color(hex: "#30d158")
        case "failed": return Color(hex: "#FF453A")
        case "completed_with_failures": return Color(hex: "#ff9f0a")
        case "paused": return Color(hex: "#ff9f0a")
        case "pending": return Color(hex: "#8e8e93")
        case "suspended": return Color(hex: "#8e8e93")
        default: return Color(hex: "#8e8e93")
        }
    }

    var body: some View {
        HStack(spacing: 0) {
            Rectangle()
                .fill(isSelected ? AcrossTheme.accent : Color.clear)
                .frame(width: 3)

            VStack(alignment: .leading, spacing: 4) {
                Text(task.description)
                    .font(.system(size: 12, weight: .medium))
                    .lineLimit(2)
                    .foregroundColor(theme.strongText)

                HStack(spacing: 6) {
                    Circle()
                        .fill(statusColor)
                        .frame(width: 6, height: 6)

                    Text(localizedTaskStatus(task.status, preferences: appPreferences))
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)

                    if task.totalCount > 0 {
                        Text("\(task.completedCount)/\(task.totalCount)")
                            .font(.system(size: 9))
                            .foregroundColor(.secondary.opacity(0.7))
                    }
                }
            }
            .padding(.leading, 10)
            .padding(.vertical, 8)

            Spacer()

            if task.status == "running" {
                ProgressView()
                    .controlSize(.mini)
                    .scaleEffect(0.7)
                    .padding(.trailing, 8)
            }
        }
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(backgroundColor)
                .padding(.horizontal, 8)
        )
        .contentShape(Rectangle())
        .onTapGesture(perform: onTap)
        .onHover { hovering in
            withAnimation(.easeInOut(duration: 0.1)) {
                isHovered = hovering
            }
        }
        .id(task.taskId)
    }

    private var backgroundColor: Color {
        if isSelected {
            return AcrossTheme.accent.opacity(0.2)
        }
        if isHovered {
            return theme.hoverBackground
        }
        return Color.clear
    }
}

