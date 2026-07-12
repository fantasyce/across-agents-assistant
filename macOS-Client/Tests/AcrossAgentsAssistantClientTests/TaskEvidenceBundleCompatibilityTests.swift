import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct TaskEvidenceBundleCompatibilityTests {
    @Test
    func redactedStringAuditFlagRemainsDecodable() throws {
        let data = Data(
            """
            {
              "task_id": "task-external",
              "task_status": "completed",
              "benchmark": {
                "benchmark_id": "external-task",
                "benchmark_version": "1.0",
                "status": "passed",
                "summary": {
                  "scenario_count": 0,
                  "passed_scenarios": 0,
                  "failed_scenarios": 0,
                  "min_quality_score": 0,
                  "max_remediation_attempts": 0
                },
                "scenarios": []
              },
              "audit": {
                "read_only": true,
                "repair_or_resume_triggered": false,
                "secrets_redacted": "[redacted]",
                "expected_files": [],
                "required_probes": []
              }
            }
            """.utf8
        )

        let bundle = try JSONDecoder().decode(TaskEvidenceBundle.self, from: data)
        #expect(bundle.audit.secretsRedacted)
    }
}
