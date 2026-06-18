"""Tests for project-level quality acceptance (Phase 4)."""

from across_agents_assistant.task_history.models import Task
from across_agents_assistant.task_review.project_acceptance import (
    run_project_acceptance,
)


class TestProjectAcceptance:
    def test_reports_missing_required_file(self, tmp_path):
        manifest = {
            "deliverables": [
                {
                    "requirement_id": "req-main",
                    "path_hint": "main.py",
                    "artifact_type": "api_service_source",
                    "required": True,
                },
                {
                    "requirement_id": "req-docker",
                    "path_hint": "Dockerfile",
                    "artifact_type": "dockerfile",
                    "required": True,
                },
            ]
        }
        (tmp_path / "main.py").write_text("print('ok')\n")
        task = Task.new("Build API", project_dir=str(tmp_path))
        report = run_project_acceptance(task, manifest, artifact_records=[])
        assert not report.passed
        assert "Dockerfile" in report.missing_required

    def test_passes_when_required_files_exist(self, tmp_path):
        manifest = {
            "deliverables": [
                {
                    "requirement_id": "req-main",
                    "path_hint": "main.py",
                    "artifact_type": "api_service_source",
                    "required": True,
                },
            ]
        }
        (tmp_path / "main.py").write_text("print('ok')\n")
        task = Task.new("Build API", project_dir=str(tmp_path))
        report = run_project_acceptance(task, manifest, artifact_records=[])
        assert report.passed
        assert len(report.missing_required) == 0

    def test_reports_empty_file(self, tmp_path):
        """An empty required file should produce a check failure."""
        manifest = {
            "deliverables": [
                {
                    "requirement_id": "req-main",
                    "path_hint": "empty.py",
                    "artifact_type": "api_service_source",
                    "required": True,
                },
            ]
        }
        (tmp_path / "empty.py").write_text("")
        task = Task.new("Build API", project_dir=str(tmp_path))
        report = run_project_acceptance(task, manifest, artifact_records=[])
        assert not report.passed  # empty file is now blocking
        non_empty_checks = [r for r in report.results if r.check_type == "file_non_empty"]
        assert any(not r.passed for r in non_empty_checks)

    def test_detects_python_syntax_error(self, tmp_path):
        manifest = {
            "deliverables": [
                {
                    "requirement_id": "req-main",
                    "path_hint": "broken.py",
                    "artifact_type": "api_service_source",
                    "required": True,
                },
            ]
        }
        (tmp_path / "broken.py").write_text("def broken(:\n    pass\n")
        task = Task.new("Build API", project_dir=str(tmp_path))
        report = run_project_acceptance(task, manifest, artifact_records=[])
        syntax_checks = [r for r in report.results if r.check_type == "python_syntax_valid"]
        assert any(not r.passed for r in syntax_checks)

    def test_no_manifest_returns_passed(self, tmp_path):
        task = Task.new("Build API", project_dir=str(tmp_path))
        report = run_project_acceptance(task, None, artifact_records=[])
        assert report.passed
        assert len(report.missing_required) == 0

    def test_skips_non_required_deliverable(self, tmp_path):
        manifest = {
            "deliverables": [
                {
                    "requirement_id": "req-opt",
                    "path_hint": "optional.md",
                    "artifact_type": "documentation",
                    "required": False,
                },
            ]
        }
        task = Task.new("Build API", project_dir=str(tmp_path))
        report = run_project_acceptance(task, manifest, artifact_records=[])
        assert report.passed


class TestProjectAcceptanceAliases:
    def test_readme_alias_counts_as_produced(self, tmp_path):
        manifest = {
            "deliverables": [
                {"requirement_id": "req-readme", "path_hint": "README",
                 "artifact_type": "documentation", "required": True}
            ]
        }
        (tmp_path / "README.md").write_text("# Demo\n")
        task = Task.new("Build docs", project_dir=str(tmp_path))
        report = run_project_acceptance(task, manifest, artifact_records=[])
        assert report.passed
        assert report.missing_required == []
        assert "README" in report.produced_required

    def test_bare_test_file_alias_counts_nested_test_as_produced(self, tmp_path):
        manifest = {
            "deliverables": [
                {"requirement_id": "req-test", "path_hint": "test_api.py",
                 "artifact_type": "test_source", "required": True}
            ]
        }
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_api.py").write_text("def test_ok():\n    assert True\n")
        task = Task.new("Build tests", project_dir=str(tmp_path))
        report = run_project_acceptance(task, manifest, artifact_records=[])
        assert report.passed
        assert report.missing_required == []

    def test_slash_file_alternative_counts_as_produced(self, tmp_path):
        manifest = {
            "deliverables": [
                {"requirement_id": "req-config", "path_hint": "setup.py/pyproject.toml",
                 "artifact_type": "config_file", "required": True}
            ]
        }
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
        task = Task.new("Build project structure", project_dir=str(tmp_path))

        report = run_project_acceptance(task, manifest, artifact_records=[])

        assert report.passed
        assert report.missing_required == []


def test_reports_empty_required_file_as_invalid_required(tmp_path):
    from across_agents_assistant.task_review.project_acceptance import run_project_acceptance
    from across_agents_assistant.task_history.models import Task
    manifest = {
        "deliverables": [
            {"requirement_id": "req-empty", "path_hint": "empty.py", "artifact_type": "api_service_source", "required": True}
        ]
    }
    (tmp_path / "empty.py").write_text("")
    task = Task.new("Build API", project_dir=str(tmp_path))

    report = run_project_acceptance(task, manifest, artifact_records=[])

    assert not report.passed
    assert report.invalid_required == [
        {
            "path_hint": "empty.py",
            "check_type": "file_non_empty",
            "message": "empty.py exists but is empty",
        }
    ]


def test_reports_python_syntax_error_as_invalid_required(tmp_path):
    from across_agents_assistant.task_review.project_acceptance import run_project_acceptance
    from across_agents_assistant.task_history.models import Task
    manifest = {
        "deliverables": [
            {"requirement_id": "req-broken", "path_hint": "broken.py", "artifact_type": "api_service_source", "required": True}
        ]
    }
    (tmp_path / "broken.py").write_text("def broken(:\n    pass\n")
    task = Task.new("Build API", project_dir=str(tmp_path))

    report = run_project_acceptance(task, manifest, artifact_records=[])

    assert not report.passed
    assert report.invalid_required[0]["path_hint"] == "broken.py"
    assert report.invalid_required[0]["check_type"] == "python_syntax_valid"


class TestBarePathResolution:
    def test_project_acceptance_resolves_bare_python_hint_to_unique_nested_file(self, tmp_path):
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "calculator.py").write_text("def add(a, b): return a + b\n")
        task = Task.new("calculator", project_dir=str(tmp_path))
        manifest = {
            "deliverables": [
                {"requirement_id": "req-calc", "path_hint": "calculator.py", "artifact_type": "api_service_source", "required": True}
            ]
        }
        report = run_project_acceptance(task, manifest, [])
        assert report.passed
        assert report.produced_required == ["calculator.py"]
        assert report.missing_required == []

    def test_project_acceptance_does_not_accept_ambiguous_bare_hint(self, tmp_path):
        (tmp_path / "app").mkdir()
        (tmp_path / "src").mkdir()
        (tmp_path / "app" / "server.py").write_text("print('app')\n")
        (tmp_path / "src" / "server.py").write_text("print('src')\n")
        task = Task.new("server", project_dir=str(tmp_path))
        manifest = {
            "deliverables": [
                {"requirement_id": "req-server", "path_hint": "server.py", "artifact_type": "api_service_source", "required": True}
            ]
        }
        report = run_project_acceptance(task, manifest, [])
        assert not report.passed
        assert "server.py" in report.missing_required

        result = next(
            item
            for item in report.results
            if item.check_type == "required_file_exists" and item.message == "Missing server.py"
        )
        ambiguous = result.evidence.get("ambiguous_candidates", [])
        assert len(ambiguous) == 2
        assert str(tmp_path / "app" / "server.py") in ambiguous
        assert str(tmp_path / "src" / "server.py") in ambiguous

    def test_project_acceptance_resolves_bare_hint_in_src(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "server.py").write_text("print('hello')\n")
        task = Task.new("server", project_dir=str(tmp_path))
        manifest = {
            "deliverables": [
                {"requirement_id": "req-server", "path_hint": "server.py", "artifact_type": "api_service_source", "required": True}
            ]
        }
        report = run_project_acceptance(task, manifest, [])
        assert report.passed
        assert report.produced_required == ["server.py"]

    def test_project_acceptance_resolves_relative_hint_under_common_package_prefix(self, tmp_path):
        (tmp_path / "app" / "routes").mkdir(parents=True)
        (tmp_path / "app" / "routes" / "expenses.py").write_text("router = object()\n")
        task = Task.new("routes", project_dir=str(tmp_path))
        manifest = {
            "deliverables": [
                {"requirement_id": "req-routes", "path_hint": "routes/expenses.py", "artifact_type": "api_service_source", "required": True}
            ]
        }
        report = run_project_acceptance(task, manifest, [])
        assert report.passed
        assert report.produced_required == ["routes/expenses.py"]


def test_project_acceptance_rejects_flask_when_fastapi_requested(tmp_path):
    from across_agents_assistant.task_history.models import Task
    from across_agents_assistant.task_review.project_acceptance import run_project_acceptance

    (tmp_path / "app.py").write_text("from flask import Flask\napp = Flask(__name__)\n")
    (tmp_path / "requirements.txt").write_text("flask-sqlalchemy\n")
    task = Task.new("Build a FastAPI SQLite app. Do not use Flask.", project_dir=str(tmp_path))
    manifest = {"deliverables": [], "quality_checks": []}

    report = run_project_acceptance(task, manifest, [])

    assert not report.passed
    assert any(result.check_type == "requested_framework_alignment" for result in report.results)


def test_project_acceptance_rejects_postgresql_when_sqlite_requested(tmp_path):
    from across_agents_assistant.task_history.models import Task
    from across_agents_assistant.task_review.project_acceptance import run_project_acceptance

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "database.py").write_text(
        "DATABASE_URL = 'postgresql+asyncpg://postgres:postgres@localhost/db'\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("fastapi\nasyncpg\n", encoding="utf-8")
    task = Task.new("Build a FastAPI SQLite app. Do not use PostgreSQL.", project_dir=str(tmp_path))
    manifest = {"deliverables": [], "quality_checks": []}

    report = run_project_acceptance(task, manifest, [])

    assert not report.passed
    assert any(result.check_type == "requested_storage_alignment" for result in report.results)


def test_project_acceptance_accepts_fastapi_when_requested(tmp_path):
    from across_agents_assistant.task_history.models import Task
    from across_agents_assistant.task_review.project_acceptance import run_project_acceptance

    (tmp_path / "app.py").write_text("from fastapi import FastAPI\nDATABASE_URL = 'sqlite+aiosqlite:///./app.db'\napp = FastAPI()\n")
    (tmp_path / "requirements.txt").write_text("fastapi\nuvicorn\naiosqlite\n")
    task = Task.new("Build a FastAPI SQLite app.", project_dir=str(tmp_path))
    manifest = {"deliverables": [], "quality_checks": []}

    report = run_project_acceptance(task, manifest, [])

    assert report.passed
    assert any(
        result.check_type == "requested_framework_alignment" and result.passed
        for result in report.results
    )
