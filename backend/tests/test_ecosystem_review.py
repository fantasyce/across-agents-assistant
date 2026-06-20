import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "generate_ecosystem_review.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_ecosystem_review", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_ecosystem_review_loads_source_registry():
    module = _load_module()

    sources = module.load_sources(ROOT / "automation" / "ecosystem-sources.json")

    assert {source["id"] for source in sources} >= {
        "openai_web_search",
        "github_actions_schedule",
        "github_cli_workflows",
    }
    assert all(source["url"].startswith("https://") for source in sources)


def test_ecosystem_review_report_is_reviewable(tmp_path):
    module = _load_module()
    sources = [
        {
            "id": "example",
            "name": "Example Source",
            "url": "https://example.com",
            "area": "automation",
        }
    ]
    statuses = [{**sources[0], "status": "not_checked", "last_modified": ""}]

    report = module.build_report(
        sources=sources,
        statuses=statuses,
        web_research="Live web research was not requested for this run.",
        generated_at="2026-06-20T00:00:00Z",
        mode="test",
    )

    assert "# Across Ecosystem Review" in report
    assert "Example Source" in report
    assert "Review Checklist" in report
    assert "Automation Policy" in report
    assert "/Users/" not in report

    output = tmp_path / "review.md"
    exit_code = module.main(["--sources", str(ROOT / "automation" / "ecosystem-sources.json"), "--output", str(output), "--mode", "test"])
    assert exit_code == 0
    assert "Across Ecosystem Review" in output.read_text(encoding="utf-8")


def test_ecosystem_review_without_openai_key_is_safe(monkeypatch):
    module = _load_module()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    message = module.run_openai_web_research([], model="test-model", api_key=None)

    assert "OPENAI_API_KEY is not configured" in message
    assert "test-model" not in json.dumps(message)
