"""Tests for requirement manifest extraction.

Phase 1 of the delivery-quality engineering implementation.
"""

from across_agents_assistant.task_manager.orchestration.requirements import (
    extract_requirement_manifest,
    extract_forbidden_path_hints,
    extract_required_path_hints,
    infer_artifact_type,
    is_probable_deliverable_path,
    normalize_path_hint,
)


class TestExtractRequiredPathHints:
    def test_extensionless_dockerfile_and_regular_files(self):
        hints = extract_required_path_hints(
            "Required deliverables: main.py, models.py, requirements.txt, "
            "Dockerfile, docker-compose.yml, tests/test_api.py, README.md, openapi_notes.md."
        )
        assert "main.py" in hints
        assert "models.py" in hints
        assert "requirements.txt" in hints
        assert "Dockerfile" in hints
        assert "docker-compose.yml" in hints
        assert "tests/test_api.py" in hints
        assert "README.md" in hints
        assert "openapi_notes.md" in hints

    def test_ignores_domains_and_package_names(self):
        hints = extract_required_path_hints(
            "Use FastAPI and call example.com in README.md."
        )
        assert "example.com" not in hints
        assert "FastAPI" not in hints
        assert "README.md" in hints

    def test_backtick_delimited_paths(self):
        hints = extract_required_path_hints("Create `src/main.py` and `tests/test_api.py`.")
        assert "src/main.py" in hints
        assert "tests/test_api.py" in hints

    def test_ignored_filelike_words_excluded(self):
        hints = extract_required_path_hints("Use python3 and pip install fastapi.")
        assert "python3" not in hints
        assert "fastapi" not in hints

    def test_extensionless_special_filenames(self):
        hints = extract_required_path_hints(
            "Create a Dockerfile, a Makefile, and a README."
        )
        assert "Dockerfile" in hints
        assert "Makefile" in hints
        assert "README" in hints

    def test_nested_file_paths(self):
        hints = extract_required_path_hints(
            "Write app/services/user_service.py and config/settings.yaml"
        )
        assert "app/services/user_service.py" in hints
        assert "config/settings.yaml" in hints

    def test_slash_separated_file_alternatives_are_expanded(self):
        hints = extract_required_path_hints(
            "Create project structure, setup.py/pyproject.toml, requirements.txt, and .gitignore."
        )
        assert "setup.py" in hints
        assert "pyproject.toml" in hints
        assert "setup.py/pyproject.toml" not in hints

    def test_no_false_positives_from_urls(self):
        hints = extract_required_path_hints(
            "Use the API at https://api.example.com/v1"
        )
        assert "api.example.com" not in hints

    def test_dotfiles_extracted(self):
        hints = extract_required_path_hints("Include .env.example and .gitignore.")
        assert ".env.example" in hints
        assert ".gitignore" in hints

    def test_slash_separated_behavior_words_are_not_extracted_as_paths(self):
        hints = extract_required_path_hints(
            "The CLI must cover add/list/complete behaviors and print friendly output."
        )
        assert "add/list/complete" not in hints

    def test_forbidden_files_are_not_extracted_as_required_paths(self):
        description = (
            "Create exactly one required file named README.md. "
            "Do not create Dockerfile, setup.py, package files, __init__.py, or container tooling."
        )

        hints = extract_required_path_hints(description)

        assert hints == ["README.md"]

    def test_exact_file_list_with_no_package_output_keeps_required_files(self):
        description = (
            "Deliver exactly these four root files and no package manager output: "
            "index.html, styles.css, app.js, README.md. "
            "No node_modules, no generated assets, no frameworks."
        )

        assert extract_forbidden_path_hints(description) == []

        hints = extract_required_path_hints(description)

        assert {"index.html", "styles.css", "app.js", "README.md"} <= set(hints)

    def test_opening_index_directly_with_no_package_managers_keeps_index_required(self):
        description = (
            "It must run by opening index.html directly, with no package managers, "
            "no external CDN, and no generated dependencies.\n\n"
            "Create exactly these files: index.html, styles.css, app.js, README.md."
        )

        assert "index.html" not in extract_forbidden_path_hints(description)

        hints = extract_required_path_hints(description)

        assert {"index.html", "styles.css", "app.js", "README.md"} <= set(hints)

    def test_chinese_forbidden_docker_is_not_extracted_as_required_path(self):
        hints = extract_required_path_hints(
            "实现 FastAPI + SQLite Web 应用，不得创建 Dockerfile/docker-compose，只需要 README.md 和 TESTING.md。"
        )

        assert "Dockerfile" not in hints
        assert "README.md" in hints
        assert "TESTING.md" in hints

    def test_chinese_except_clause_does_not_forbid_allowed_docs(self):
        description = "除 README.md 和 TESTING.md 外不要增加额外文档。"

        assert extract_forbidden_path_hints(description) == []
        assert extract_required_path_hints(description) == ["README.md", "TESTING.md"]

    def test_positive_dockerfile_requirement_is_still_extracted(self):
        hints = extract_required_path_hints(
            "Create app.py, Dockerfile, and README.md. Docker is required for packaging."
        )

        assert "Dockerfile" in hints

    def test_linked_assets_are_not_required_deliverables_for_single_html_subtask(self):
        hints = extract_required_path_hints(
            "Create index.html with semantic structure. Link styles.css and load app.js."
        )

        assert hints == ["index.html"]

    def test_explicit_file_list_keeps_assets_even_when_later_referenced(self):
        hints = extract_required_path_hints(
            "Create exactly these four files at the project root:\n"
            "- index.html\n"
            "- styles.css\n"
            "- app.js\n"
            "- README.md\n\n"
            "Quality requirements: index.html must link to styles.css and must load app.js."
        )

        assert {"index.html", "styles.css", "app.js", "README.md"} <= set(hints)


class TestExtractForbiddenPathHints:
    def test_extracts_forbidden_files_from_negative_sentence(self):
        hints = extract_forbidden_path_hints(
            "Do not create Dockerfile, setup.py, package files, __init__.py, or container tooling."
        )

        assert {"Dockerfile", "setup.py", "__init__.py"} <= set(hints)

    def test_required_readme_with_forbidden_contents_is_not_forbidden(self):
        description = (
            "Use these exact four files only: index.html, styles.css, app.js, README.md. "
            "README.md must not mention npm, yarn, pnpm, bun, node_modules, package.json, "
            "dev servers, build commands, or test-suite commands."
        )

        hints = extract_forbidden_path_hints(description)

        assert "README.md" not in hints
        assert "README" not in hints
        assert "package.json" in hints

    def test_extracts_forbidden_files_from_chinese_negative_sentence(self):
        hints = extract_forbidden_path_hints(
            "不得创建 Dockerfile/docker-compose，不要生成 setup.py。"
        )

        assert {"Dockerfile", "setup.py"} <= set(hints)


class TestNormalizePathHint:
    def test_strips_backticks_and_quotes(self):
        assert normalize_path_hint("`main.py`") == "main.py"
        assert normalize_path_hint('"main.py"') == "main.py"

    def test_strips_leading_dot_slash(self):
        assert normalize_path_hint("./src/main.py") == "src/main.py"

    def test_converts_backslashes(self):
        assert normalize_path_hint("src\\main.py") == "src/main.py"

    def test_strips_trailing_punctuation(self):
        assert normalize_path_hint("main.py.") == "main.py"
        assert normalize_path_hint("main.py)") == "main.py"

    def test_returns_none_for_empty(self):
        assert normalize_path_hint("") is None
        assert normalize_path_hint("   ") is None


class TestIsProbableDeliverablePath:
    def test_accepts_py_file(self):
        assert is_probable_deliverable_path("main.py")

    def test_rejects_bare_domain(self):
        assert not is_probable_deliverable_path("example.com")

    def test_accepts_dockerfile(self):
        assert is_probable_deliverable_path("Dockerfile")

    def test_rejects_url_scheme(self):
        assert not is_probable_deliverable_path("https://example.com")

    def test_accepts_nested_path(self):
        assert is_probable_deliverable_path("src/app/main.py")


class TestInferArtifactType:
    def test_dockerfile(self):
        assert infer_artifact_type("Dockerfile") == "dockerfile"

    def test_docker_compose_yml(self):
        assert infer_artifact_type("docker-compose.yml") == "compose_config"

    def test_readme(self):
        assert infer_artifact_type("README.md") == "documentation"

    def test_python_test_file(self):
        assert infer_artifact_type("tests/test_api.py") == "test_source"
        assert infer_artifact_type("test_main.py") == "test_source"

    def test_python_source_file(self):
        assert infer_artifact_type("main.py") == "api_service_source"
        assert infer_artifact_type("app/models.py") == "api_service_source"

    def test_config_file(self):
        assert infer_artifact_type("config.yaml") == "config_file"
        assert infer_artifact_type("settings.json") == "config_file"


class TestExtractRequirementManifest:
    def test_manifest_contains_all_expected_deliverables(self):
        manifest = extract_requirement_manifest(
            task_id="task-x",
            description=(
                "Required deliverables: main.py, models.py, requirements.txt, "
                "Dockerfile, docker-compose.yml, tests/test_api.py, README.md, openapi_notes.md."
            ),
            project_dir="/tmp/project",
        )
        hints = {d.path_hint for d in manifest.deliverables}
        assert {
            "main.py",
            "models.py",
            "requirements.txt",
            "Dockerfile",
            "docker-compose.yml",
            "tests/test_api.py",
            "README.md",
            "openapi_notes.md",
        } <= hints

    def test_manifest_ignores_domains_and_package_names(self):
        manifest = extract_requirement_manifest(
            task_id="task-x",
            description="Use FastAPI and call example.com in README.md.",
            project_dir="/tmp/project",
        )
        hints = {d.path_hint for d in manifest.deliverables}
        assert "example.com" not in hints
        assert "FastAPI" not in hints
        assert "README.md" in hints

    def test_manifest_excludes_forbidden_files_and_container_quality_check(self):
        manifest = extract_requirement_manifest(
            task_id="task-x",
            description=(
                "Create exactly one required file named README.md. "
                "Do not create Dockerfile, setup.py, package files, __init__.py, or container tooling."
            ),
            project_dir="/tmp/project",
        )

        hints = {d.path_hint for d in manifest.deliverables}
        check_types = {c.check_type for c in manifest.quality_checks}

        assert hints == {"README.md"}
        assert "container_config_exists" not in check_types

    def test_manifest_excludes_chinese_forbidden_docker_and_container_check(self):
        manifest = extract_requirement_manifest(
            task_id="task-x",
            description=(
                "实现 FastAPI + SQLite Web 应用，不得创建 Dockerfile/docker-compose，"
                "文档只需要 README.md 和 TESTING.md。"
            ),
            project_dir="/tmp/project",
        )

        hints = {d.path_hint for d in manifest.deliverables}
        check_types = {c.check_type for c in manifest.quality_checks}

        assert "Dockerfile" not in hints
        assert {"README.md", "TESTING.md"} <= hints
        assert "container_config_exists" not in check_types

    def test_manifest_excludes_runtime_json_file_persistence_hint(self):
        manifest = extract_requirement_manifest(
            task_id="task-x",
            description=(
                "Implement todo_cli.py using argparse. "
                "Use JSON file persistence (e.g., todos.json). "
                "Required files are todo_cli.py, tests/test_todo_cli.py, and README.md."
            ),
            project_dir="/tmp/project",
        )

        hints = {d.path_hint for d in manifest.deliverables}
        assert "todos.json" not in hints
        assert {"todo_cli.py", "tests/test_todo_cli.py", "README.md"} <= hints

    def test_manifest_has_quality_checks(self):
        manifest = extract_requirement_manifest(
            task_id="task-x",
            description="Create a FastAPI REST API with main.py and pytest tests.",
            project_dir="/tmp/project",
        )
        assert len(manifest.quality_checks) >= 1
        check_types = {c.check_type for c in manifest.quality_checks}
        assert "required_files_exist" in check_types

    def test_empty_description_produces_no_deliverables(self):
        manifest = extract_requirement_manifest(
            task_id="task-x", description="", project_dir="/tmp/project"
        )
        assert manifest.deliverables == []

    def test_manifest_id_is_unique(self):
        m1 = extract_requirement_manifest("task-1", "Create main.py")
        m2 = extract_requirement_manifest("task-2", "Create main.py")
        assert m1.manifest_id != m2.manifest_id


class TestPathDeduplication:
    def test_deduplicates_readme_md_over_extensionless_readme(self):
        hints = extract_required_path_hints("Create README.md with build instructions.")
        assert "README.md" in hints
        assert "README" not in hints

    def test_keeps_explicit_extensionless_readme_when_no_readme_md(self):
        hints = extract_required_path_hints("Create a README with build instructions.")
        assert hints == ["README"]

    def test_deduplicates_nested_test_path_over_bare_test_file(self):
        hints = extract_required_path_hints("Create tests/test_api.py with pytest coverage.")
        assert "tests/test_api.py" in hints
        assert "test_api.py" not in hints

    def test_requirements_txt_is_config_file(self):
        from across_agents_assistant.task_manager.orchestration.requirements import infer_artifact_type
        assert infer_artifact_type("requirements.txt") == "config_file"


class TestManifestDeduplication:
    def test_manifest_has_no_duplicate_readme_or_test_basenames(self):
        manifest = extract_requirement_manifest(
            task_id="task-x",
            description=(
                "Create main.py, tests/test_api.py, README.md, Dockerfile, "
                "docker-compose.yml, and requirements.txt."
            ),
            project_dir="/tmp/project",
        )
        hints = [d.path_hint for d in manifest.deliverables]
        assert "README.md" in hints
        assert "README" not in hints
        assert "tests/test_api.py" in hints
        assert "test_api.py" not in hints
        by_hint = {d.path_hint: d.artifact_type for d in manifest.deliverables}
        assert by_hint["requirements.txt"] == "config_file"


class TestPathAliasDeduplication:
    def test_manifest_prefers_nested_path_over_bare_basename_for_same_python_file(self):
        manifest = extract_requirement_manifest(
            "task-alias",
            """
            Required deliverables:
            1. app/calculator.py — defines add.
            """,
            project_dir="/tmp/project",
        )
        paths = [item.path_hint for item in manifest.deliverables]
        assert "app/calculator.py" in paths
        assert "calculator.py" not in paths

    def test_manifest_dedupes_src_paths_against_bare_names(self):
        manifest = extract_requirement_manifest(
            "task-src",
            """
            Required deliverables:
            1. src/server.py — entry point.
            2. src/routes.py — route metadata.
            """,
            project_dir="/tmp/project",
        )
        paths = [item.path_hint for item in manifest.deliverables]
        assert "src/server.py" in paths
        assert "src/routes.py" in paths
        assert "server.py" not in paths
        assert "routes.py" not in paths

    def test_manifest_does_not_extract_python_module_name_as_file(self):
        manifest = extract_requirement_manifest(
            "task-module",
            "Create src/server.py using the standard library http.server module.",
            project_dir="/tmp/project",
        )
        paths = [item.path_hint for item in manifest.deliverables]
        assert "src/server.py" in paths
        assert "http.server" not in paths

    def test_manifest_keeps_distinct_nested_python_files_with_same_basename(self):
        """Different nested paths with same basename should both be kept."""
        manifest = extract_requirement_manifest(
            "task-two-dirs",
            """
            Required deliverables:
            1. app/utils.py — app utilities.
            2. lib/utils.py — library utilities.
            """,
            project_dir="/tmp/project",
        )
        paths = [item.path_hint for item in manifest.deliverables]
        assert "app/utils.py" in paths
        assert "lib/utils.py" in paths
