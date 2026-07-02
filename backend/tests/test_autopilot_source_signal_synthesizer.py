from __future__ import annotations

from across_agents_assistant.autopilot_source_signal_synthesizer import (
    AI_READY_CONTEXT_SCHEMA,
    classify_source_signal,
    render_ai_ready_context,
    summarize_source_signal,
    synthesize_ai_ready_context,
)
from across_agents_assistant.loop_engineering_capability_pack import loop_engineering_capability_pack


def test_source_signal_synthesizer_classifies_and_bounds_public_context():
    context = synthesize_ai_ready_context(
        {
            "signals": [
                {"summary": "MCP adapter contract drift should be handled by projection status."},
                {"summary": "Release E2E failure needs validation gate repair."},
                {"summary": "Workbench onboarding copy should make self-iteration easier to start."},
            ]
        },
        max_summary_chars=80,
    )

    assert context["schema_version"] == AI_READY_CONTEXT_SCHEMA
    assert context["source_count"] == 3
    assert context["category_counts"]["architecture"] == 1
    assert context["category_counts"]["validation"] == 1
    assert context["category_counts"]["user_experience"] == 1
    assert all(
        len(item["summary"]) <= 80
        for items in context["categories"].values()
        for item in items
    )


def test_source_signal_synthesizer_redacts_secrets_paths_and_sensitive_fields():
    summary = summarize_source_signal(
        {
            "summary": "Use token=plain-secret and Bearer abcdefghijklmnop inside /Users/alice/private/file.txt.",
            "transcript": "This raw transcript should not be copied.",
            "secret": "sk-supersecretvalue",
        }
    )

    assert "plain-secret" not in summary
    assert "abcdefghijklmnop" not in summary
    assert "/Users/alice" not in summary
    assert "raw transcript" not in summary
    assert "[redacted-secret]" in summary
    assert "[redacted-local-path]" in summary


def test_source_signal_synthesizer_limits_items_per_category():
    context = synthesize_ai_ready_context(
        [
            {"summary": "CI validation failure one"},
            {"summary": "CI validation failure two"},
            {"summary": "CI validation failure three"},
        ],
        max_items_per_category=2,
    )

    assert context["category_counts"]["validation"] == 3
    assert len(context["categories"]["validation"]) == 2


def test_loop_engineering_capability_pack_exposes_ai_ready_context():
    pack = loop_engineering_capability_pack(
        [{"summary": "OAuth token policy needs validation evidence before release."}]
    )
    capability_ids = {item["id"] for item in pack["ready"]}

    assert "source_signal_synthesizer" in capability_ids
    assert pack["ready_count"] == len(pack["ready"])
    assert pack["ai_ready_context"]["schema_version"] == AI_READY_CONTEXT_SCHEMA
    assert pack["ai_ready_context"]["source_count"] == 1
    assert pack["ai_ready_context"]["policy"]["raw_transcripts_excluded"] is True
    assert "AI-Ready Context" in render_ai_ready_context(pack["ai_ready_context"])


def test_source_signal_classification_defaults_to_uncategorized():
    assert classify_source_signal({"summary": "Small neutral note"}) == "uncategorized"
