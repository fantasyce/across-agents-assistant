import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct OperationsWorkbenchStateTests {
    @Test func primaryInformationArchitectureIsStable() {
        #expect(OperationsWorkbenchSurface.primary == [.workspaces, .qualityGate, .evidence, .memory])
        #expect(OperationsWorkbenchSurface.allCases.contains(.humanReview))
        #expect(OperationsWorkbenchSurface.allCases.contains(.assist))
        #expect(SettingsHubTab.groupedNavigation == [.diagnostics, .models, .capabilities, .plugins, .tools, .settings])
    }

    @Test func boundedWorkspaceLogKeepsLatestChunksAndReportsTruncation() {
        var log = BoundedWorkspaceLog(maxChunks: 2, maxCharacters: 256)
        log.append(WorkspaceLogChunk(stream: .stdout, text: "one"))
        log.append(WorkspaceLogChunk(stream: .stderr, text: "two"))
        log.append(WorkspaceLogChunk(stream: .stdout, text: "three"))

        #expect(log.chunks.map(\.text) == ["two", "three"])
        #expect(log.didTruncate)
        #expect(log.characterCount <= 256)
    }

    @Test func workspaceFixturesCoverEveryOperationalPane() {
        for state in WorkspaceFixtureState.allCases {
            let fixture = WorkspaceRunFixture.make(state)
            #expect(Set(fixture.paneStates.map(\.kind)) == Set(WorkspacePaneKind.allCases))
            #expect(fixture.agentStatus == state.status)
        }
        #expect(OperationalContentState.behaviorFixtures.count == 6)
        #expect(OperationalContentState.behaviorFixtures.contains(.active("active")))
        #expect(OperationalContentState.behaviorFixtures.contains(.disabled("disabled")))
        #expect(OperationalContentState.behaviorFixtures.contains(.success("success")))
    }

    @Test func workspaceVisualFixturesCoverThemeLocaleAndRequiredStates() {
        let fixtures = WorkspaceVisualFixture.completeMatrix
        #expect(fixtures.count == 20)
        #expect(Set(fixtures.map(\.id)).count == fixtures.count)
        for theme in WorkspaceVisualTheme.allCases {
            for locale in WorkspaceVisualLocale.allCases {
                let states = fixtures
                    .filter { $0.theme == theme && $0.locale == locale }
                    .map(\.state)
                #expect(Set(states) == Set(WorkspaceVisualState.allCases))
            }
        }
    }

    @Test func humanReviewQueueCoversEveryRequiredReviewKind() {
        let signals = HumanReviewKind.allCases.map { kind in
            HumanReviewSignal(
                id: kind.rawValue,
                kind: kind,
                title: kind.rawValue,
                detail: "detail",
                status: kind == .blockingGate ? "blocked" : "pending",
                source: "fixture"
            )
        } + [
            HumanReviewSignal(
                id: "resolved",
                kind: .promotion,
                title: "Resolved promotion",
                detail: "detail",
                status: "approved",
                source: "fixture"
            ),
        ]

        let snapshot = HumanReviewQueueSnapshot(signals: signals)

        #expect(snapshot.totalCount == HumanReviewKind.allCases.count)
        #expect(snapshot.blockingCount == 1)
        for kind in HumanReviewKind.allCases {
            #expect(snapshot.count(for: kind) == 1)
        }
        #expect(snapshot.items.first?.kind == .blockingGate)
    }

    @Test func iconControlsRequireStableNamesAndHelp() {
        let valid = AcrossIconControlContract(
            id: "workspace.refresh",
            accessibilityLabel: "Refresh workspace readiness",
            help: "Refresh workspace readiness"
        )
        let missingLabel = AcrossIconControlContract(
            id: "workspace.refresh",
            accessibilityLabel: " ",
            help: "Refresh workspace readiness"
        )

        #expect(valid.isValid)
        #expect(!missingLabel.isValid)
    }

    @Test func focusPathsAreOrderedAndContainNoDuplicates() {
        #expect(OperationsFocusTarget.workspacePath.first == .primaryNavigation)
        #expect(OperationsFocusTarget.workspacePath.last == .commandToolbar)
        #expect(Set(OperationsFocusTarget.workspacePath).count == OperationsFocusTarget.workspacePath.count)
        #expect(OperationsFocusTarget.reviewPath.contains(.reviewQueue))
        #expect(OperationsFocusTarget.reviewPath.contains(.inspector))
        #expect(OperationsFocusTarget.workspacePath.contains(.diffReview))
        #expect(OperationsFocusTarget.workspacePath.contains(.inlineComment))
        #expect(ApprovalDialogAccessibilityContract.standard.isValid)
        #expect(ApprovalDialogAccessibilityContract.standard.initialFocus == .deny)
        #expect(ApprovalDialogAccessibilityContract.standard.escapeDecision == "reject")
    }

    @Test func newOperationsStringsCoverEnglishAndChinese() {
        let keys = OperationsWorkbenchSurface.allCases.map(\.localizationKey)
            + WorkspacePaneKind.allCases.map(\.localizationKey)
            + HumanReviewKind.allCases.map(\.localizationKey)
            + [
                "settings.systemHealth",
                "settings.agentsModels",
                "settings.pluginsMCP",
                "settings.toolPermissions",
                "workspace.output.notPersisted",
                "workspace.create.chooseRepository",
                "workspace.create.repositoryStale",
                "workspace.create.repositoryFailed",
                "workspace.create.repositoryPickerMessage",
                "workspace.comment.inlineTitle",
                "workspace.comment.anchorLine",
                "workspace.provider.account",
                "workspace.provider.rateLimit",
                "gate.run",
                "gate.result.ciTaxonomy",
                "memory.scope.ordinary",
                "memory.scope.pending",
                "memory.pendingExplicit",
                "review.humanBoundary",
                "approval.decisionHint",
            ]

        for key in keys {
            #expect(AppPreferences.localizedString(key, localeIdentifier: "en") != key)
            #expect(AppPreferences.localizedString(key, localeIdentifier: "zh-Hans") != key)
        }
    }
}
