from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_product_language as product_language  # noqa: E402
from check_product_language import find_language_violations, main  # noqa: E402


FORBIDDEN_EXAMPLE = "goal" + "board"


@pytest.mark.parametrize(
    "text",
    [
        FORBIDDEN_EXAMPLE,
        "Goal" + " " + "Board",
        "goal" + "-" + "board",
        "goal" + "_" + "board",
    ],
)
def test_detects_prohibited_product_language_in_text(tmp_path: Path, text: str) -> None:
    (tmp_path / "README.md").write_text(text, encoding="utf-8")

    violations = find_language_violations([tmp_path])

    assert [violation.kind for violation in violations] == ["content"]


def test_detects_prohibited_product_language_in_filename(tmp_path: Path) -> None:
    path = tmp_path / f"{FORBIDDEN_EXAMPLE}-release.json"
    path.write_text("safe content", encoding="utf-8")

    violations = find_language_violations([tmp_path])

    assert [violation.kind for violation in violations] == ["path"]


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        ("safe.py", f"ACROSS_{FORBIDDEN_EXAMPLE.upper()}_RELEASE_TRAIN_CANDIDATE=1"),
        (f"write_{FORBIDDEN_EXAMPLE}_release.py", "safe content"),
    ],
)
def test_detects_prohibited_language_embedded_in_identifiers(
    tmp_path: Path,
    filename: str,
    content: str,
) -> None:
    (tmp_path / filename).write_text(content, encoding="utf-8")

    violations = find_language_violations([tmp_path])

    assert violations


def test_ignores_generated_dependency_directories(tmp_path: Path) -> None:
    ignored = tmp_path / "node_modules" / "example.txt"
    ignored.parent.mkdir(parents=True)
    ignored.write_text(FORBIDDEN_EXAMPLE, encoding="utf-8")

    assert find_language_violations([tmp_path]) == []


def test_fails_closed_when_source_cannot_be_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "README.md"
    source.write_text("safe content", encoding="utf-8")
    original_read_bytes = Path.read_bytes

    def fail_for_source(path: Path) -> bytes:
        if path == source:
            raise OSError("fixture read failure")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_for_source)

    with pytest.raises(RuntimeError, match="could not inspect a source file"):
        find_language_violations([tmp_path])


def test_fails_closed_when_source_is_not_utf8(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_bytes(b"\xff\xfe")

    with pytest.raises(RuntimeError, match="could not decode a source file"):
        find_language_violations([tmp_path])


def test_fails_closed_when_source_tree_cannot_be_traversed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_walk(root: Path, onerror=None):
        assert root == tmp_path.resolve()
        assert onerror is not None
        onerror(OSError("fixture traversal failure"))
        return iter(())

    monkeypatch.setattr(product_language.os, "walk", failing_walk)

    with pytest.raises(RuntimeError, match="could not traverse a source tree"):
        find_language_violations([tmp_path])


def test_cli_reports_only_repo_label_and_relative_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = tmp_path / "example-repo"
    repository.mkdir()
    (repository / "README.md").write_text(FORBIDDEN_EXAMPLE, encoding="utf-8")

    assert main([str(repository)]) == 1

    output = capsys.readouterr().out
    assert "example-repo:README.md:1 [content]" in output
    assert str(tmp_path) not in output


def test_open_source_check_enforces_product_language_guard() -> None:
    check_script = (ROOT / "scripts" / "open_source_check.sh").read_text(encoding="utf-8")

    assert "python3 scripts/check_product_language.py ." in check_script


def test_release_acceptance_scans_all_four_source_trees() -> None:
    acceptance_script = (
        ROOT / "scripts" / "run_vnext_single_release_acceptance.sh"
    ).read_text(encoding="utf-8")

    assert "product_language_guard" in acceptance_script
    assert (
        "scripts/check_product_language.py '$ROOT_DIR' '$ORCHESTRATOR_ROOT' "
        "'$CONTEXT_ROOT' '$AUTOPILOT_ROOT'"
    ) in acceptance_script
