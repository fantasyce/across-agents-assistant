import SwiftUI
import AppKit

struct TaskOrchestrationView: View {
    @ObservedObject var viewModel: TaskOrchestrationViewModel
    @ObservedObject var settingsVM: SettingsViewModel
    var defaultProjectPath: String? = nil
    var onClose: (() -> Void)? = nil

    @Environment(\.colorScheme) private var colorScheme
    @EnvironmentObject private var appPreferences: AppPreferences
    private var theme: TaskTheme { TaskTheme(colorScheme: colorScheme) }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                CustomTrafficLights(onClose: onClose)

                Spacer()

                Text(appPreferences.text("tasks.title"))
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(theme.primaryText)

                Spacer()

                Spacer().frame(width: 50)
            }
            .padding(.horizontal, 16)
            .frame(height: 56)
            .background(
                ZStack {
                    theme.headerBackground
                    WindowDragView()
                        .contentShape(Rectangle())
                }
            )

            Divider().opacity(0.5)

            HStack(spacing: 0) {
                TaskListSidebar(viewModel: viewModel)
                    .frame(width: 240)

                Rectangle()
                    .fill(theme.divider)
                    .frame(width: 1)

                TaskDetailPanel(viewModel: viewModel, settingsVM: settingsVM, defaultProjectPath: defaultProjectPath)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(theme.background.ignoresSafeArea())
        .ignoresSafeArea(.all, edges: .top)
        .onAppear {
            viewModel.loadTasks()
        }
    }
}
