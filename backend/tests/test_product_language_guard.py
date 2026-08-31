from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from check_product_language import find_language_violations  # noqa: E402


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


def test_ignores_generated_dependency_directories(tmp_path: Path) -> None:
    ignored = tmp_path / "node_modules" / "example.txt"
    ignored.parent.mkdir(parents=True)
    ignored.write_text(FORBIDDEN_EXAMPLE, encoding="utf-8")

    assert find_language_violations([tmp_path]) == []


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
