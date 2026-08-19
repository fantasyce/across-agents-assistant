import Foundation

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

private let validTrajectoryJSON = """
{
  "schema_version": "across-execution-trajectory/1.0",
  "generated_at": 10.0,
  "task_id": "task-public",
  "task_status": "completed",
  "source": "orchestrator_evidence",
  "summary": {
    "source_event_count": 1,
    "normalized_event_count": 1,
    "first_sequence": 1,
    "last_sequence": 1,
    "started_at": 9.0,
    "completed_at": 10.0,
    "terminal_status": "completed",
    "private_summary": "private-summary-marker"
  },
  "page": {
    "offset": 0,
    "limit": 200,
    "returned": 1,
    "total": 1,
    "next_offset": null,
    "has_more": false
  },
  "receipt": {
    "schema_version": "across-evidence-receipt/1.0",
    "integrity_state": "hash_valid",
    "digest_algorithm": "sha256",
    "digest_field": "evidence_sha256",
    "digest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "verdict": "ready",
    "reason": "hash_matches_raw_receipt",
    "private_receipt": "private-receipt-marker"
  },
  "items": [
    {
      "event_id": "event-1",
      "sequence": 1,
      "timestamp": 10.0,
      "event_type": "task.completed",
      "category": "task",
      "phase": "completed",
      "status": "succeeded",
      "title": "Task completed",
      "scope_kind": "task",
      "scope_id": "task-public",
      "actor": "agent-public",
      "evidence_refs": ["artifact-public"],
      "payload": "private-payload-marker"
    }
  ],
  "audit": {
    "read_only": true,
    "mutations_triggered": false,
    "repair_or_resume_triggered": false,
    "secrets_redacted": true,
    "receipt_checked_before_redaction": true,
    "raw_payload_exposed": false,
    "event_integrity_state": "clean",
    "omitted_event_count": 0,
    "conflicting_duplicate_count": 0,
    "truncated": false,
    "private_audit": "private-audit-marker"
  },
  "private_top_level": "private-top-marker"
}
"""

private func decode(_ json: String) throws -> TaskExecutionTrajectory {
    try JSONDecoder().decode(TaskExecutionTrajectory.self, from: Data(json.utf8))
}

private func assertDecodeFails(_ json: String, _ message: String) {
    do {
        _ = try decode(json)
        fatalError(message)
    } catch is DecodingError {
        return
    } catch {
        fatalError("Expected DecodingError: \(error)")
    }
}

func testStrictTrajectoryDecodeAndClosedExport() throws {
    let trajectory = try decode(validTrajectoryJSON)

    assert(trajectory.schemaVersion == "across-execution-trajectory/1.0", "Schema should decode")
    assert(trajectory.source == .orchestratorEvidence, "Source should decode")
    assert(trajectory.taskStatus == .completed, "Task status should decode")
    assert(trajectory.receipt.integrityState == .hashValid, "Receipt integrity should decode")
    assert(trajectory.items.first?.category == .task, "Category should decode")
    assert(trajectory.items.first?.phase == .completed, "Phase should decode")
    assert(trajectory.items.first?.status == .succeeded, "Status should decode")
    assert(trajectory.audit.eventIntegrityState == .clean, "Audit integrity should decode")
    assert(trajectory.audit.readOnly, "Read-only proof should decode")

    let exported = String(decoding: try trajectory.prettyPublicJSON(), as: UTF8.self)
    for marker in [
        "private-summary-marker",
        "private-receipt-marker",
        "private-payload-marker",
        "private-audit-marker",
        "private-top-marker",
        "private_top_level",
    ] {
        assert(!exported.contains(marker), "Closed export leaked \(marker)")
    }
    assert(!exported.contains("\"payload\""), "Closed export must not contain a payload key")
    assert(exported.contains("\"schema_version\""), "Export should use public snake-case keys")
    assert(TaskExecutionTrajectory.exportFileName(taskId: " task/../../private ") == "task-private-execution-trajectory.json", "Export filename should be sanitized")
}

func testUnknownFutureEnumsFailClosedToUnknown() throws {
    let future = validTrajectoryJSON
        .replacingOccurrences(of: "\"task_status\": \"completed\"", with: "\"task_status\": \"future_task_status\"")
        .replacingOccurrences(of: "\"source\": \"orchestrator_evidence\"", with: "\"source\": \"future_source\"")
        .replacingOccurrences(of: "\"integrity_state\": \"hash_valid\"", with: "\"integrity_state\": \"future_integrity\"")
        .replacingOccurrences(of: "\"category\": \"task\"", with: "\"category\": \"future_category\"")
        .replacingOccurrences(of: "\"phase\": \"completed\"", with: "\"phase\": \"future_phase\"")
        .replacingOccurrences(of: "\"status\": \"succeeded\"", with: "\"status\": \"future_status\"")
        .replacingOccurrences(of: "\"event_integrity_state\": \"clean\"", with: "\"event_integrity_state\": \"future_event_integrity\"")

    let trajectory = try decode(future)

    assert(trajectory.taskStatus == .unknown, "Unknown task status should fail closed")
    assert(trajectory.source == .unknown, "Unknown source should fail closed")
    assert(trajectory.receipt.integrityState == .unknown, "Unknown receipt integrity should fail closed")
    assert(trajectory.items.first?.category == .unknown, "Unknown category should fail closed")
    assert(trajectory.items.first?.phase == .unknown, "Unknown phase should fail closed")
    assert(trajectory.items.first?.status == .unknown, "Unknown item status should fail closed")
    assert(trajectory.audit.eventIntegrityState == .unknown, "Unknown event integrity should fail closed")
}

func testMissingOrUnsafeSafetyFieldsAreRejected() {
    assertDecodeFails(
        validTrajectoryJSON.replacingOccurrences(of: "    \"read_only\": true,\n", with: ""),
        "Missing read_only must fail"
    )
    assertDecodeFails(
        validTrajectoryJSON.replacingOccurrences(of: "\"read_only\": true", with: "\"read_only\": false"),
        "read_only=false must fail"
    )
    assertDecodeFails(
        validTrajectoryJSON.replacingOccurrences(of: "\"mutations_triggered\": false", with: "\"mutations_triggered\": true"),
        "mutations_triggered=true must fail"
    )
    assertDecodeFails(
        validTrajectoryJSON.replacingOccurrences(of: "    \"raw_payload_exposed\": false,\n", with: ""),
        "Missing raw_payload_exposed must fail"
    )
    assertDecodeFails(
        validTrajectoryJSON.replacingOccurrences(of: "\"repair_or_resume_triggered\": false", with: "\"repair_or_resume_triggered\": true"),
        "repair_or_resume_triggered=true must fail"
    )
    assertDecodeFails(
        validTrajectoryJSON.replacingOccurrences(of: "\"secrets_redacted\": true", with: "\"secrets_redacted\": false"),
        "secrets_redacted=false must fail"
    )
    assertDecodeFails(
        validTrajectoryJSON.replacingOccurrences(of: "\"receipt_checked_before_redaction\": true", with: "\"receipt_checked_before_redaction\": false"),
        "receipt_checked_before_redaction=false must fail"
    )
}

@main
struct ExecutionTrajectoryBehavior {
    static func main() {
        do {
            try testStrictTrajectoryDecodeAndClosedExport()
            try testUnknownFutureEnumsFailClosedToUnknown()
            testMissingOrUnsafeSafetyFieldsAreRejected()
            print("ExecutionTrajectoryBehavior passed")
        } catch {
            fatalError("ExecutionTrajectoryBehavior failed: \(error)")
        }
    }
}
