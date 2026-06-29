import Foundation

enum SimpleStartWorkflowPreset: String, CaseIterable, Identifiable {
    case repositoryQuality = "repository-quality-copilot"
    case pluginCompatibility = "plugin-compatibility-lab"
    case releaseCaptain = "release-captain"

    var id: String { rawValue }

    var titleKey: String {
        switch self {
        case .repositoryQuality: return "tasks.simpleStart.repo.title"
        case .pluginCompatibility: return "tasks.simpleStart.plugin.title"
        case .releaseCaptain: return "tasks.simpleStart.release.title"
        }
    }

    var subtitleKey: String {
        switch self {
        case .repositoryQuality: return "tasks.simpleStart.repo.subtitle"
        case .pluginCompatibility: return "tasks.simpleStart.plugin.subtitle"
        case .releaseCaptain: return "tasks.simpleStart.release.subtitle"
        }
    }

    var actionKey: String {
        switch self {
        case .repositoryQuality: return "tasks.simpleStart.repo.action"
        case .pluginCompatibility: return "tasks.simpleStart.plugin.action"
        case .releaseCaptain: return "tasks.simpleStart.release.action"
        }
    }

    var iconSystemName: String {
        switch self {
        case .repositoryQuality: return "doc.text.magnifyingglass"
        case .pluginCompatibility: return "puzzlepiece.extension"
        case .releaseCaptain: return "checkmark.seal"
        }
    }

    var accentHex: String {
        switch self {
        case .repositoryQuality: return "#2F80ED"
        case .pluginCompatibility: return "#16A085"
        case .releaseCaptain: return "#C06C20"
        }
    }

    var targetPlaceholderKey: String? {
        switch self {
        case .pluginCompatibility:
            return "tasks.simpleStart.plugin.targetPlaceholder"
        case .repositoryQuality, .releaseCaptain:
            return nil
        }
    }

    var deliveryTaskTypes: Set<TaskOrchestrationDeliveryTaskType> {
        [.artifact, .functional]
    }

    func makeDraft(target: String = "", projectDirectory: String? = nil) -> SimpleStartWorkflowDraft {
        SimpleStartWorkflowDraft(
            preset: self,
            target: target.trimmingCharacters(in: .whitespacesAndNewlines),
            projectDirectory: projectDirectory?.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty
        )
    }

    func taskDescription(target: String) -> String {
        let cleanTarget = target.trimmingCharacters(in: .whitespacesAndNewlines)
        switch self {
        case .repositoryQuality:
            return """
            Run Repository Quality Copilot on this repository. Inspect repo health, project manifests, dependency and license risk, documentation entrypoints, release readiness, and policy boundaries. Produce a markdown repo-quality report, JSON evidence, release-readiness notes, and a redacted pending memory summary when useful.
            """
        case .pluginCompatibility:
            let targetText = cleanTarget.isEmpty ? "the candidate plugin, MCP server, manifest, command, GitHub repository, or local workspace selected for this task" : cleanTarget
            return """
            Run Plugin Compatibility Lab v2 for \(targetText). Evaluate compatibility, manifest quality, license and dependency risk, local/remote execution safety, projection readiness for MCP Tasks, LF A2A v2, AG-UI, Remote MCP/OAuth, and OTel export, plus optional browser or computer-use sandbox evidence. Produce an adoption recommendation, remediation list, JSON evidence, and only redacted pending memory candidates.
            """
        case .releaseCaptain:
            return """
            Run Release Captain for this repository. Verify open-source hygiene, version and changelog consistency, regression tests, release evidence, producer pins, Live E2E readiness, rollback notes, and unresolved risk. Produce a release-readiness report with pass/fail gates, required commands, evidence paths, and human-review attention items.
            """
        }
    }
}

struct SimpleStartWorkflowDraft: Identifiable, Equatable {
    let preset: SimpleStartWorkflowPreset
    let target: String
    let projectDirectory: String?

    var id: String {
        [preset.rawValue, target, projectDirectory ?? ""].joined(separator: "|")
    }

    var taskDescription: String {
        preset.taskDescription(target: target)
    }

    var deliveryTaskTypes: Set<TaskOrchestrationDeliveryTaskType> {
        preset.deliveryTaskTypes
    }

    var taskTypeValues: [String] {
        deliveryTaskTypes.map(\.rawValue).sorted()
    }
}

private extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
    }
}
