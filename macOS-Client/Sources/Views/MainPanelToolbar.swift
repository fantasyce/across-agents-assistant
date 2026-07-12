import SwiftUI

extension MainPanelView {
    var headerBar: some View {
        HStack(spacing: 12) {
            if taskOrchestrationViewModel.selectedTask != nil || !appPreferences.automaticDeliveryProtection {
                Button {
                    showsSelectedTaskDetails = false
                    if taskOrchestrationViewModel.selectedTask != nil {
                        taskOrchestrationViewModel.enterWorkflowPicker()
                    }
                    appPreferences.automaticDeliveryProtection = true
                } label: {
                    Label(appPreferences.text("work.back"), systemImage: "chevron.left")
                }
                .buttonStyle(.plain)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(AcrossTheme.accent)
                .help(appPreferences.text("work.back.help"))
            }

            Text(viewModel.activeProjectName ?? appPreferences.text("work.title"))
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(textColor)
                .lineLimit(1)
            Spacer()
            if taskOrchestrationViewModel.selectedTask != nil {
                Button(appPreferences.text("work.new")) {
                    showsSelectedTaskDetails = false
                    taskOrchestrationViewModel.enterWorkflowPicker()
                    viewModel.inputText = ""
                }
                .buttonStyle(.plain)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(AcrossTheme.accent)
            }
        }
        .padding(.horizontal, 20)
        .frame(height: 56)
        .background(ZStack { bgColor; WindowDragView().contentShape(Rectangle()) })
    }
}
