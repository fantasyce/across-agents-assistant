from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_reference_architecture_defines_required_layers_and_boundaries():
    doc = _read("LOOP_ENGINEERING_REFERENCE_ARCHITECTURE.md")

    for anchor in [
        "Trigger Layer",
        "Contract Layer",
        "Memory and State Layer",
        "Tool Layer",
        "Agent Orchestration Layer",
        "Verification and Promotion Layer",
        "Conformance Loop",
        "Autonomous Product Loop",
        "Tool Pack Registry",
        "AAA native tools and capability registry",
        "AAA unified capability registry for cross-product discovery without executor",
        "unified_capability_registry",
        "builder must not mark semantic acceptance passed",
        "candidate_app_lifecycle_passed",
    ]:
        assert anchor in doc


def test_existing_loop_engineering_docs_point_to_reference_architecture():
    plan = _read("LOOP_ENGINEERING_PLATFORM_PLAN.md")
    candidate = _read("CANDIDATE_PRODUCT_PIPELINE_PLAN.md")
    acceptance = _read("LOOP_ENGINEERING_PLATFORM_ACCEPTANCE.md")

    assert "LOOP_ENGINEERING_REFERENCE_ARCHITECTURE.md" in plan
    assert "conformance fixture" in plan
    assert "production autonomous loop" in plan

    assert "LOOP_ENGINEERING_REFERENCE_ARCHITECTURE.md" in candidate
    assert "fixed two-file AAA self-iteration LoopSpec is a conformance fixture" in candidate

    assert "LOOP_ENGINEERING_REFERENCE_ARCHITECTURE.md" in acceptance
    assert "fixed-target AAA" in acceptance
    assert "add an autonomous loop" in acceptance
