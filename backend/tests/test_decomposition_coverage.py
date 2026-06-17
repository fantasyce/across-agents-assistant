"""Tests for decomposition coverage gate (Phase 2)."""

from across_agents_assistant.task_review.coverage import (
    evaluate_decomposition_coverage,
    find_matching_contract_deliverable,
    normalize_hint,
)


class TestNormalizeHint:
    def test_strips_leading_dot_slash(self):
        assert normalize_hint("./src/main.py") == "src/main.py"

    def test_normalizes_backslashes(self):
        assert normalize_hint("src\\main.py") == "src/main.py"

    def test_returns_empty_for_none(self):
        assert normalize_hint(None) == ""


class TestEvaluateDecompositionCoverage:
    def test_coverage_detects_missing_dockerfile_contract(self):
        manifest = {
            "deliverables": [
                {"requirement_id": "req-main", "artifact_type": "api_service_source",
                 "path_hint": "main.py", "required": True},
                {"requirement_id": "req-docker", "artifact_type": "dockerfile",
                 "path_hint": "Dockerfile", "required": True},
            ]
        }
        contracts = [
            {
                "level": "subtask",
                "subtask_id": "st-main",
                "expected_deliverables": [
                    {"artifact_type": "api_service_source", "path_hint": "main.py",
                     "required": True}
                ],
            }
        ]
        result = evaluate_decomposition_coverage(manifest, contracts)
        assert not result.passed
        assert [gap.path_hint for gap in result.gaps] == ["Dockerfile"]

    def test_coverage_matches_nested_path_hint(self):
        manifest = {
            "deliverables": [
                {"requirement_id": "req-tests", "artifact_type": "test_source",
                 "path_hint": "tests/test_api.py", "required": True},
            ]
        }
        contracts = [
            {
                "level": "subtask",
                "subtask_id": "st-tests",
                "expected_deliverables": [
                    {"artifact_type": "file", "path_hint": "tests/test_api.py",
                     "required": True}
                ],
            }
        ]
        result = evaluate_decomposition_coverage(manifest, contracts)
        assert result.passed
        assert result.assigned["req-tests"] == "st-tests"

    def test_coverage_passes_when_all_requirements_assigned(self):
        manifest = {
            "deliverables": [
                {"requirement_id": "req-main", "artifact_type": "api_service_source",
                 "path_hint": "main.py", "required": True},
                {"requirement_id": "req-docker", "artifact_type": "dockerfile",
                 "path_hint": "Dockerfile", "required": True},
            ]
        }
        contracts = [
            {
                "level": "subtask",
                "subtask_id": "st-main",
                "expected_deliverables": [
                    {"artifact_type": "api_service_source", "path_hint": "main.py",
                     "required": True}
                ],
            },
            {
                "level": "subtask",
                "subtask_id": "st-docker",
                "expected_deliverables": [
                    {"artifact_type": "dockerfile", "path_hint": "Dockerfile",
                     "required": True}
                ],
            },
        ]
        result = evaluate_decomposition_coverage(manifest, contracts)
        assert result.passed
        assert len(result.gaps) == 0

    def test_skips_non_required_deliverables(self):
        manifest = {
            "deliverables": [
                {"requirement_id": "req-opt", "artifact_type": "documentation",
                 "path_hint": "README.md", "required": False},
            ]
        }
        result = evaluate_decomposition_coverage(manifest, [])
        assert result.passed
        assert len(result.gaps) == 0

    def test_ignores_non_subtask_contracts(self):
        manifest = {
            "deliverables": [
                {"requirement_id": "req-main", "artifact_type": "api_service_source",
                 "path_hint": "main.py", "required": True},
            ]
        }
        contracts = [
            {
                "level": "task",
                "expected_deliverables": [
                    {"artifact_type": "api_service_source", "path_hint": "main.py",
                     "required": True}
                ],
            }
        ]
        result = evaluate_decomposition_coverage(manifest, contracts)
        assert not result.passed


class TestFindMatchingContractDeliverable:
    def test_exact_path_hint_match(self):
        req = {"path_hint": "main.py", "artifact_type": "api_service_source"}
        contracts = [{"path_hint": "main.py", "artifact_type": "file", "_subtask_id": "st-main"}]
        assert find_matching_contract_deliverable(req, contracts) is not None

    def test_basename_match_with_different_parent(self):
        req = {"path_hint": "src/main.py", "artifact_type": "api_service_source"}
        contracts = [{"path_hint": "main.py", "artifact_type": "file", "_subtask_id": "st-main"}]
        assert find_matching_contract_deliverable(req, contracts) is not None

    def test_no_match_returns_none(self):
        req = {"path_hint": "Dockerfile", "artifact_type": "dockerfile"}
        result = find_matching_contract_deliverable(req, [])
        assert result is None


class TestCoverageAliasMatching:
    def test_coverage_matches_readme_alias(self):
        manifest = {
            "deliverables": [
                {"requirement_id": "req-readme", "artifact_type": "documentation",
                 "path_hint": "README", "required": True}
            ]
        }
        contracts = [
            {
                "level": "subtask",
                "subtask_id": "st-docs",
                "expected_deliverables": [
                    {"artifact_type": "file", "path_hint": "README.md", "required": True}
                ],
            }
        ]
        result = evaluate_decomposition_coverage(manifest, contracts)
        assert result.passed
        assert result.assigned["req-readme"] == "st-docs"

    def test_coverage_matches_nested_test_alias(self):
        manifest = {
            "deliverables": [
                {"requirement_id": "req-test", "artifact_type": "test_source",
                 "path_hint": "test_api.py", "required": True}
            ]
        }
        contracts = [
            {
                "level": "subtask",
                "subtask_id": "st-tests",
                "expected_deliverables": [
                    {"artifact_type": "file", "path_hint": "tests/test_api.py", "required": True}
                ],
            }
        ]
        result = evaluate_decomposition_coverage(manifest, contracts)
        assert result.passed
