import Testing
@testable import AcrossAgentsAssistantClient

struct MemoryReviewTextFormatterTests {
    @Test func structuredMemoryUsesReadableActionSequenceInsteadOfRawJSON() {
        let text = """
        {"decisions":[{"action_type":"task_dispatch","status":"completed"},{"action_type":"memory_search","status":"completed"},{"action_type":"quality_gate","status":"completed"}]}
        """

        let summary = MemoryReviewTextFormatter.summary(for: text)

        #expect(summary == "task dispatch  ->  memory search  ->  quality gate")
        #expect(!summary.contains("{"))
        #expect(!summary.contains("\""))
    }

    @Test func explicitSummaryWinsOverInternalStructuredFields() {
        let text = """
        {"summary":"Remember the release verification result.","action_type":"memory_search"}
        """

        #expect(
            MemoryReviewTextFormatter.summary(for: text)
                == "Remember the release verification result."
        )
    }

    @Test func plainTextRemainsReadableAndBounded() {
        let summary = MemoryReviewTextFormatter.summary(for: "  A useful project decision.\nKeep it concise.  ")
        #expect(summary == "A useful project decision. Keep it concise.")
        #expect(summary.count <= 280)
    }

    @Test func malformedStructuredMemoryNeverLeaksRawJSON() {
        let summary = MemoryReviewTextFormatter.summary(
            for: "{\"schema_version\":\"broken\"",
            fallback: "Readable fallback"
        )
        #expect(summary == "Readable fallback")
        #expect(!summary.contains("{"))
    }
}
