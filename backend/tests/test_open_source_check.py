from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_sensitive_scan_excludes_git_directory_and_worktree_pointer() -> None:
    script = (REPO_ROOT / "scripts" / "open_source_check.sh").read_text(encoding="utf-8")
    ripgrep_branch = script.split("if command -v rg", maxsplit=1)[1].split("else", maxsplit=1)[0]

    assert "--glob '!.git/**'" in ripgrep_branch
    assert "--glob '!.git'" in ripgrep_branch
