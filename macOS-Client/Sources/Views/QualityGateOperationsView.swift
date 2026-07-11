import SwiftUI

struct QualityGateOperationsView: View {
    @ObservedObject var operations: QualityGateViewModel
    @ObservedObject var preferences: AppPreferences
    let activeProjectPath: String?
    let onOpenFullWorkflow: () -> Void
    let onOpenReviewQueue: () -> Void

    @Environment(\.colorScheme) private var colorScheme
    @ObservedObject private var repositoryStore = SecurityScopedRepositoryStore.shared
    private let repositoryAccessOwner = "quality-gate"

    var body: some View {
        VStack(spacing: 0) {
            commandBar
            Rectangle().fill(AcrossTheme.separator(for: colorScheme)).frame(height: 1)
            HSplitView {
                gateForm
                    .frame(minWidth: 285, idealWidth: 320, maxWidth: 380)
                resultContent
                    .frame(minWidth: 520, maxWidth: .infinity)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AcrossTheme.canvasFill(for: colorScheme))
        .onAppear {
            repositoryStore.restore()
            if let path = repositoryStore.selectedPath, repositoryStore.beginAccess(owner: repositoryAccessOwner) {
                operations.configureProjectPath(path)
            } else {
                operations.configureProjectPath(nil)
            }
        }
        .onDisappear { repositoryStore.endAccess(owner: repositoryAccessOwner) }
        .alert(
            localized("Confirm GitHub remote operations", "确认 GitHub 远程操作"),
            isPresented: $operations.isRemoteConfirmationPresented
        ) {
            Button(localized("Cancel", "取消"), role: .cancel) {
                operations.cancelRemoteConfirmation()
            }
            Button(localized("Push and create draft PR", "推送并创建草稿 PR"), role: .destructive) {
                Task { await operations.confirmRemoteRun() }
            }
        } message: {
            Text(localized(
                "This will push the selected feature branch, create or update a draft pull request, watch CI, and publish the gate result. Credentials remain host-managed and are never entered or stored here.",
                "这会推送所选功能分支、创建或更新草稿 PR、等待 CI，并发布质量门结果。凭据始终由主机管理，不会在此输入或保存。"
            ))
        }
    }

    private var commandBar: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(preferences.text("gate.title"))
                    .font(.system(size: 16, weight: .semibold))
                Text(preferences.text("gate.subtitle"))
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if let result = operations.result {
                StatusChip(status: result.gateVerdict)
            }
            CommandToolbarButton(
                systemName: "person.crop.circle.badge.exclamationmark",
                accessibilityLabel: preferences.text("workspace.openReviewQueue"),
                help: preferences.text("workspace.openReviewQueue")
            ) { onOpenReviewQueue() }
            Button(preferences.text("gate.openWorkflow"), action: onOpenFullWorkflow)
                .buttonStyle(.bordered)
                .controlSize(.small)
                .keyboardShortcut("g", modifiers: [.command, .shift])
            Button {
                Task { await operations.run() }
            } label: {
                if operations.isRunning {
                    ProgressView().controlSize(.small)
                } else {
                    Label(preferences.text("gate.run"), systemImage: "play.fill")
                }
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.small)
            .disabled(operations.draft.validationError != nil || operations.isRunning || !repositoryStore.isAccessing)
            .keyboardShortcut(.defaultAction)
            .accessibilityLabel(Text(preferences.text("gate.run")))
            .accessibilityHint(Text(preferences.text("gate.runHelp")))
            .help(preferences.text("gate.runHelp"))
        }
        .padding(.horizontal, 18)
        .frame(height: 58)
        .background(AcrossTheme.panelFill(for: colorScheme))
    }

    private var gateForm: some View {
        VStack(spacing: 0) {
            HStack {
                Text(preferences.text("gate.form.title"))
                    .font(.system(size: 11, weight: .semibold))
                Spacer()
                Image(systemName: "slider.horizontal.3")
                    .foregroundStyle(.secondary)
                    .accessibilityHidden(true)
            }
            .padding(.horizontal, 12)
            .frame(height: 44)
            .overlay(alignment: .bottom) {
                Rectangle().fill(AcrossTheme.separator(for: colorScheme)).frame(height: 1)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: 13) {
                    repositorySelector
                    operationModeSelector
                    HStack(spacing: 8) {
                        gateTextField(preferences.text("gate.form.base"), text: $operations.draft.baseRef)
                        gateTextField(preferences.text("gate.form.head"), text: $operations.draft.headRef)
                    }
                    gateTextField(preferences.text("gate.form.branch"), text: $operations.draft.branch)
                    gateTextField(preferences.text("gate.form.commit"), text: $operations.draft.commit)
                    gateTextField(preferences.text("gate.form.ciPath"), text: $operations.draft.ciPath)

                    VStack(alignment: .leading, spacing: 7) {
                        Text(preferences.text("gate.form.ciWait"))
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(.secondary)
                        Stepper(value: $operations.draft.ciWaitSeconds, in: 0...900, step: 10) {
                            Text(String(format: preferences.text("gate.form.seconds"), operations.draft.ciWaitSeconds))
                                .font(.system(size: 11, weight: .semibold, design: .rounded))
                        }
                        .accessibilityLabel(Text(preferences.text("gate.form.ciWait")))
                    }

                    VStack(alignment: .leading, spacing: 7) {
                        Text(preferences.text("gate.form.maxRepairs"))
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(.secondary)
                        Stepper(value: $operations.draft.maxRepairs, in: 0...10) {
                            HStack {
                                Text("\(operations.draft.maxRepairs)")
                                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                                Spacer()
                                Text(preferences.text("gate.form.plannedOnly"))
                                    .font(.system(size: 9))
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .accessibilityLabel(Text(preferences.text("gate.form.maxRepairs")))
                    }

                    if operations.draft.operationMode == .localReadOnly {
                        Toggle(preferences.text("gate.form.draftPR"), isOn: $operations.draft.draftPR)
                            .toggleStyle(.checkbox)
                            .font(.system(size: 11))
                            .help(preferences.text("gate.form.draftPRHelp"))
                    } else {
                        remoteSettings
                    }

                    if let validationError = operations.draft.validationError {
                        Label(validationError, systemImage: "exclamationmark.triangle")
                            .font(.system(size: 10))
                            .foregroundStyle(StatusPalette.tone(for: "attention").foreground)
                    }

                    EvidencePanel(
                        title: preferences.text("gate.form.safety"),
                        summary: preferences.text("gate.form.safetyDetail"),
                        status: "ready"
                    ) {
                        VStack(alignment: .leading, spacing: 5) {
                            Label(
                                operations.draft.operationMode == .localReadOnly
                                    ? preferences.text("gate.form.noRemoteMutation")
                                    : localized("Remote changes require this run's confirmation", "远程变更需要本次运行单独确认"),
                                systemImage: "lock.shield"
                            )
                            Label(preferences.text("gate.form.blockedIsResult"), systemImage: "checkmark.circle")
                            Label(
                                localized("No credential input or token persistence", "不提供凭据输入，也不持久化令牌"),
                                systemImage: "key.slash"
                            )
                        }
                        .font(.system(size: 9))
                    }
                }
                .padding(12)
            }
        }
        .background(AcrossTheme.panelFill(for: colorScheme))
    }

    @ViewBuilder
    private var resultContent: some View {
        if operations.isRunning && operations.result == nil {
            runningContent
        } else if let result = operations.result {
            QualityGateResultView(result: result, preferences: preferences)
        } else if let error = operations.errorMessage {
            OperationalContentStateView(
                state: .error(error),
                title: preferences.text("gate.unavailable"),
                retryTitle: preferences.text("system.retry")
            ) { Task { await operations.run() } }
            .overlay(alignment: .bottom) {
                if let failure = operations.failure {
                    Label(
                        failure.recoveryHint,
                        systemImage: failure.recoverable ? "arrow.clockwise.circle" : "exclamationmark.shield"
                    )
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(18)
                    .accessibilityLabel(Text(failure.recoveryHint))
                }
            }
        } else if operations.draft.repoRoot.isEmpty {
            OperationalContentStateView(
                state: .disabled(preferences.text("gate.selectRepository")),
                title: preferences.text("gate.selectRepository")
            )
        } else {
            OperationalContentStateView(
                state: .disabled(preferences.text("gate.noResult.detail")),
                title: preferences.text("gate.noResult")
            )
        }
    }

    private var operationModeSelector: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(localized("OPERATION MODE", "操作模式"))
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(.secondary)
            Picker(localized("Operation mode", "操作模式"), selection: $operations.draft.operationMode) {
                Text(localized("Local read-only", "本地只读"))
                    .tag(QualityGateOperationMode.localReadOnly)
                Text(localized("GitHub draft PR", "GitHub 草稿 PR"))
                    .tag(QualityGateOperationMode.approvedRemoteDraftPR)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .accessibilityLabel(Text(localized("Quality gate operation mode", "质量门操作模式")))
            Text(
                operations.draft.operationMode == .localReadOnly
                    ? localized("Runs local checks and produces evidence without changing GitHub.", "运行本地检查并生成证据，不修改 GitHub。")
                    : localized("After confirmation: push branch, maintain a draft PR, watch CI, and publish verification.", "确认后：推送分支、维护草稿 PR、等待 CI 并发布验证结果。")
            )
            .font(.system(size: 9))
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var remoteSettings: some View {
        VStack(alignment: .leading, spacing: 10) {
            Toggle(localized("Watch GitHub CI", "等待 GitHub CI"), isOn: $operations.draft.watchCI)
                .toggleStyle(.checkbox)
                .font(.system(size: 11))
            if operations.draft.watchCI {
                Stepper(value: $operations.draft.ciIdleTimeoutSeconds, in: 30...7_200, step: 30) {
                    timeoutLabel(
                        localized("Idle", "空闲"),
                        seconds: operations.draft.ciIdleTimeoutSeconds
                    )
                }
                .accessibilityLabel(Text(localized("CI idle timeout", "CI 空闲超时")))
                Stepper(value: $operations.draft.ciMaxWallTimeoutSeconds, in: 60...14_400, step: 60) {
                    timeoutLabel(
                        localized("Max wall", "最长总时长"),
                        seconds: operations.draft.ciMaxWallTimeoutSeconds
                    )
                }
                .accessibilityLabel(Text(localized("CI maximum wall time", "CI 最长总时长")))
            }
        }
        .padding(10)
        .background(AcrossTheme.recessedFill(for: colorScheme))
        .clipShape(RoundedRectangle(cornerRadius: AcrossTheme.Metrics.controlCornerRadius))
    }

    private func timeoutLabel(_ title: String, seconds: Int) -> some View {
        HStack {
            Text(title).font(.system(size: 10, weight: .semibold))
            Spacer()
            Text(duration(seconds))
                .font(.system(size: 10, weight: .semibold, design: .rounded))
                .foregroundStyle(.secondary)
        }
    }

    private var runningContent: some View {
        VStack(spacing: 14) {
            ProgressView().controlSize(.regular)
            Text(preferences.text("gate.running"))
                .font(.system(size: 14, weight: .semibold))
            if let activity = operations.runActivity {
                StatusChip(status: activity.status.rawValue, label: activityLabel(activity.status))
                Text(String(format: localized("Elapsed %@", "已运行 %@"), duration(activity.elapsedSeconds)))
                    .font(.system(size: 11, weight: .semibold, design: .rounded))
                if activity.remote {
                    Text(String(
                        format: localized("Idle budget %@ · maximum wall %@", "空闲预算 %@ · 最长总时长 %@"),
                        duration(activity.idleTimeoutSeconds),
                        duration(activity.maxWallTimeoutSeconds)
                    ))
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .combine)
    }

    private func activityLabel(_ status: QualityGateRunActivityStatus) -> String {
        switch status {
        case .active: return localized("Active", "活跃")
        case .idle: return localized("Idle budget reached", "已达到空闲预算")
        case .maxWallExceeded: return localized("Maximum wall time reached", "已达到最长总时长")
        }
    }

    private func duration(_ seconds: Int) -> String {
        let hours = seconds / 3_600
        let minutes = (seconds % 3_600) / 60
        let remainingSeconds = seconds % 60
        if hours > 0 { return String(format: "%dh %02dm", hours, minutes) }
        if minutes > 0 { return String(format: "%dm %02ds", minutes, remainingSeconds) }
        return "\(remainingSeconds)s"
    }

    private func localized(_ english: String, _ simplifiedChinese: String) -> String {
        preferences.resolvedLocaleIdentifier == "zh-Hans" ? simplifiedChinese : english
    }

    private func gateTextField(_ title: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(.secondary)
            TextField(title, text: text)
                .textFieldStyle(.roundedBorder)
                .font(.system(size: 11, design: .monospaced))
                .accessibilityLabel(Text(title))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var repositorySelector: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(preferences.text("gate.form.repository"))
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(.secondary)
            HStack(spacing: 8) {
                Text(operations.draft.repoRoot.isEmpty ? preferences.text("workspace.notConfigured") : operations.draft.repoRoot)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundStyle(operations.draft.repoRoot.isEmpty ? Color.secondary : Color.primary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Button {
                    guard let url = repositoryStore.chooseRepository(
                        title: preferences.text("workspace.create.chooseRepository"),
                        message: preferences.text("workspace.create.repositoryPickerMessage"),
                        prompt: preferences.text("workspace.create.chooseRepository")
                    ) else { return }
                    guard repositoryStore.beginAccess(owner: repositoryAccessOwner) else { return }
                    operations.configureProjectPath(url.path)
                } label: {
                    Image(systemName: "folder")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .accessibilityLabel(Text(preferences.text("workspace.create.chooseRepository")))
                .accessibilityHint(Text(preferences.text("workspace.create.chooseRepositoryHint")))
                .help(preferences.text("workspace.create.chooseRepositoryHint"))
            }
            if repositoryStore.state.requiresReselection {
                Text(preferences.text("workspace.create.repositoryStale"))
                    .font(.system(size: 9))
                    .foregroundStyle(StatusPalette.tone(for: "attention").foreground)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
