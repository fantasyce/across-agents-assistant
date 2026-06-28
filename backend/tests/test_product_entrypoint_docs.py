import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


ROOT_MARKDOWN_ALLOWLIST = {
    "AGENTS.md",
    "CHANGELOG.md",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "OPEN_SOURCE_RELEASE_HANDBOOK.md",
    "README.md",
    "SECURITY.md",
}

REMOVED_ROOT_DOCS = {
    "AGENT_ICON_WORKFLOW.md",
    "AGENT_LOOP_COMPLETENESS.md",
    "ARCHITECTURE.md",
    "AUTONOMOUS_WORKFLOW.md",
    "CANDIDATE_PRODUCT_PIPELINE_PLAN.md",
    "LOOP_ENGINEERING_FINAL_TEST_REPORT.md",
    "LOOP_ENGINEERING_PLATFORM_ACCEPTANCE.md",
    "LOOP_ENGINEERING_PLATFORM_PLAN.md",
    "LOOP_ENGINEERING_PRODUCT_PACKAGING.md",
    "LOOP_ENGINEERING_REFERENCE_ARCHITECTURE.md",
    "LOOP_ENGINEERING_REMAINING_WORK.md",
    "LOOP_ENGINEERING_SKILL_TOOL_MATRIX.md",
    "RELEASE_PROCESS.md",
}


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_root_markdown_is_limited_to_public_and_agent_entrypoints():
    root_markdown = {path.name for path in ROOT.glob("*.md")}

    assert root_markdown <= ROOT_MARKDOWN_ALLOWLIST
    assert not (root_markdown & REMOVED_ROOT_DOCS)


def test_agent_readable_entrypoints_do_not_advertise_removed_docs():
    readme = _read("README.md")
    llms = _read("llms.txt")
    product = json.loads(_read("across.product.json"))
    product_text = json.dumps(product, sort_keys=True)

    for path in REMOVED_ROOT_DOCS:
        assert path not in readme
        assert path not in llms
        assert path not in product_text

    assert product["machine_readable_entrypoints"] == [
        "llms.txt",
        "AGENTS.md",
        "across.product.json",
    ]
    assert "README.md" in product["human_readable_entrypoints"]
    assert "OPEN_SOURCE_RELEASE_HANDBOOK.md" in product["human_readable_entrypoints"]
