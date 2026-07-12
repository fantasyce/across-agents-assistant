import SwiftUI
import AppKit

struct TaskListSidebar: View {
    @ObservedObject var viewModel: TaskOrchestrationViewModel
    @State private var searchText = ""
    @State private var showsReleaseE2EConfirmation = false

    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    private var filteredTasks: [TaskOrchestrationViewModel.TaskSummary] {
        if searchText.isEmpty {
            return viewModel.tasks
        }
        return viewModel.tasks.filter { $0.description.localizedCaseInsensitiveContains(searchText) }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text(appPreferences.text("tasks.sidebar"))
                    .font(.system(size: 10, weight: .semibold))
                    .tracking(0.8)
                    .foregroundColor(.secondary.opacity(0.6))
                    .frame(maxWidth: .infinity, alignment: .leading)

                Button(action: { viewModel.enterCreateMode() }) {
                    Image(systemName: "plus.circle.fill")
                        .font(.system(size: 14))
                        .foregroundColor(viewModel.isOrchestratorPluginUnavailable ? .secondary.opacity(0.5) : AcrossTheme.accent)
                }
                .buttonStyle(.plain)
                .disabled(viewModel.isOrchestratorPluginUnavailable)
                .help(appPreferences.text("tasks.new"))
            }
            .padding(.horizontal, 16)
            .padding(.top, 12)
            .padding(.bottom, 8)

            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)

                TextField(appPreferences.text("tasks.search"), text: $searchText)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(theme.primaryText)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(theme.fieldBackground)
            .cornerRadius(6)
            .padding(.horizontal, 12)

            ReleaseEvaluationCard(
                summary: viewModel.releaseEvaluation,
                isLoading: viewModel.isLoadingReleaseEvaluation,
                errorMessage: viewModel.releaseEvaluationError,
                isStartingE2E: viewModel.isStartingReleaseE2E,
                e2eErrorMessage: viewModel.releaseE2EError,
                isOrchestratorUnavailable: viewModel.isOrchestratorPluginUnavailable,
                onRefresh: { viewModel.loadReleaseEvaluation() },
                onOpenCenter: { viewModel.openReleaseCenter() },
                onRunE2E: { showsReleaseE2EConfirmation = true }
            )
            .padding(.horizontal, 12)
            .padding(.top, 10)

            if viewModel.isBackendUnavailable {
                BackendUnavailableBanner(
                    message: viewModel.backendUnavailableMessage,
                    onRetry: { viewModel.loadTasks() }
                )
                .padding(.horizontal, 12)
                .padding(.top, 10)
            }

            ScrollView {
                LazyVStack(spacing: 2) {
                    ForEach(filteredTasks) { task in
                        TaskRowView(
                            task: task,
                            isSelected: viewModel.selectedTask?.taskId == task.taskId,
                            onTap: { viewModel.selectTask(task.taskId) }
                        )
                    }

                    if searchText.isEmpty && viewModel.hasMoreTasks {
                        Button(action: { viewModel.loadMoreTasks() }) {
                            HStack(spacing: 6) {
                                if viewModel.isLoadingMoreTasks {
                                    ProgressView()
                                        .controlSize(.mini)
                                        .scaleEffect(0.7)
                                } else {
                                    Image(systemName: "chevron.down")
                                        .font(.system(size: 10, weight: .semibold))
                                }
                                Text(viewModel.isLoadingMoreTasks ? appPreferences.text("tasks.loading") : appPreferences.text("tasks.loadMore"))
                                    .font(.system(size: 11, weight: .medium))
                            }
                            .foregroundColor(.secondary)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 10)
                        }
                        .buttonStyle(.plain)
                        .disabled(viewModel.isLoadingMoreTasks)
                    }
                }
                .padding(.vertical, 8)
            }

            Spacer()
        }
        .confirmationDialog(
            appPreferences.text("tasks.releaseE2E.confirmTitle"),
            isPresented: $showsReleaseE2EConfirmation,
            titleVisibility: .visible
        ) {
            Button(appPreferences.text("tasks.releaseE2E.run")) {
                viewModel.startReleaseE2E()
            }
            Button(appPreferences.text("system.cancel"), role: .cancel) {}
        } message: {
            Text(appPreferences.text("tasks.releaseE2E.confirmMessage"))
        }
        .frame(maxHeight: .infinity)
        .background(theme.background)
    }
}
