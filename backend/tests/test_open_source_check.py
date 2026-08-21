import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_sensitive_scan_excludes_git_directory_and_worktree_pointer() -> None:
    script = (REPO_ROOT / "scripts" / "open_source_check.sh").read_text(encoding="utf-8")
    ripgrep_branch = script.split("if command -v rg", maxsplit=1)[1].split("else", maxsplit=1)[0]

    assert "--glob '!.git/**'" in ripgrep_branch
    assert "--glob '!.git'" in ripgrep_branch


def test_promotion_package_has_no_producer_checkout_imports_or_private_paths() -> None:
    source_path = (
        REPO_ROOT
        / "backend"
        / "src"
        / "across_agents_assistant"
        / "promotion_package.py"
    )
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported_roots.add(node.module.split(".", maxsplit=1)[0])

    assert imported_roots.isdisjoint(
        {"across_autopilot", "across_context", "across_orchestrator"}
    )
    assert "sys.path" not in source
    assert "PYTHONPATH" not in source
    assert "/Users/" not in source
    assert "Documents/projects" not in source
