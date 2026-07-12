import Foundation

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

func testOperationsWorkbenchPrimarySurfaces() {
    assert(
        OperationsWorkbenchSurface.primary == [.assist],
        "The first screen must expose one clear work surface"
    )
    assert(
        OperationsWorkbenchSurface.allCases.contains(.humanReview),
        "Human Review must remain globally reachable"
    )
    assert(
        OperationsWorkbenchSurface.allCases.contains(.assist),
        "Work must remain the default product surface"
    )
}

func testBoundedWorkspaceLogs() {
    var log = BoundedWorkspaceLog(maxChunks: 2, maxCharacters: 256)
    log.append(WorkspaceLogChunk(stream: .stdout, text: "first"))
    log.append(WorkspaceLogChunk(stream: .stderr, text: "second"))
    log.append(WorkspaceLogChunk(stream: .stdout, text: "third"))

    assert(log.chunks.map(\.text) == ["second", "third"], "Only the latest bounded chunks should remain")
    assert(log.didTruncate, "A bounded log must expose truncation")
    assert(log.characterCount <= 256, "A bounded log must enforce its character budget")
}

func testWorkspaceStateFixtures() {
    for state in WorkspaceFixtureState.allCases {
        let fixture = WorkspaceRunFixture.make(state)
        assert(
            Set(fixture.paneStates.map(\.kind)) == Set(WorkspacePaneKind.allCases),
            "Every state fixture must cover every workspace pane"
        )
        assert(fixture.agentStatus == state.status, "Fixture status should match the requested state")
    }
    assert(OperationalContentState.behaviorFixtures.count == 6, "All operational content states need fixtures")
    assert(
        OperationalContentState.behaviorFixtures.contains(.active("active")),
        "Active content state needs a fixture"
    )
    assert(
        OperationalContentState.behaviorFixtures.contains(.disabled("disabled")),
        "Disabled content state needs a fixture"
    )
    assert(WorkspaceVisualFixture.completeMatrix.count == 20, "Theme, locale, and state fixtures must form a complete matrix")
    for theme in WorkspaceVisualTheme.allCases {
        for locale in WorkspaceVisualLocale.allCases {
            let states = WorkspaceVisualFixture.completeMatrix
                .filter { $0.theme == theme && $0.locale == locale }
                .map(\.state)
            assert(Set(states) == Set(WorkspaceVisualState.allCases), "Visual fixture matrix is incomplete")
        }
    }
}

func testHumanReviewQueueCoverage() {
    let signals = HumanReviewKind.allCases.map { kind in
        HumanReviewSignal(
            id: kind.rawValue,
            kind: kind,
            title: kind.rawValue,
            detail: "fixture",
            status: kind == .blockingGate ? "blocked" : "pending",
            source: "behavior"
        )
    }
    let queue = HumanReviewQueueSnapshot(signals: signals)

    assert(queue.totalCount == HumanReviewKind.allCases.count, "Every review category should enter the queue")
    assert(queue.items.first?.kind == .blockingGate, "Blocking gates should sort first")
    for kind in HumanReviewKind.allCases {
        assert(queue.count(for: kind) == 1, "Missing review category: \(kind.rawValue)")
    }
}

func testAccessibilityAndFocusContracts() {
    let valid = AcrossIconControlContract(
        id: "workspace.refresh",
        accessibilityLabel: "Refresh workspace readiness",
        help: "Refresh workspace readiness"
    )
    let invalid = AcrossIconControlContract(
        id: "workspace.refresh",
        accessibilityLabel: "",
        help: "Refresh workspace readiness"
    )

    assert(valid.isValid, "Named icon controls should pass the accessibility contract")
    assert(!invalid.isValid, "Unnamed icon controls should fail the accessibility contract")
    assert(
        Set(OperationsFocusTarget.workspacePath).count == OperationsFocusTarget.workspacePath.count,
        "Workspace focus order must not contain duplicate targets"
    )
    assert(
        OperationsFocusTarget.reviewPath.contains(.reviewQueue),
        "Review focus order must include the queue"
    )
    assert(OperationsFocusTarget.workspacePath.contains(.diffReview), "Workspace focus order must include diff review")
    assert(OperationsFocusTarget.workspacePath.contains(.inlineComment), "Workspace focus order must include inline comments")
    assert(ApprovalDialogAccessibilityContract.standard.isValid, "Approval dialog must keep safe initial focus and Escape behavior")
}

@main
struct OperationsWorkbenchBehavior {
    static func main() {
        testOperationsWorkbenchPrimarySurfaces()
        testBoundedWorkspaceLogs()
        testWorkspaceStateFixtures()
        testHumanReviewQueueCoverage()
        testAccessibilityAndFocusContracts()
        print("OperationsWorkbenchBehavior passed")
    }
}
