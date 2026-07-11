import subprocess

import pytest

import across_agents_assistant.plugin_runtime as plugin_runtime
from across_agents_assistant.plugin_runtime import (
    PluginLifecycleError,
    improve_context_memory,
    retrieve_context_memories_merged,
    rollback_distilled_context_memory,
    search_context_memories,
    update_context_memory_status,
)


def test_search_context_memories_defaults_to_active_policy(monkeypatch):
    captured = {}

    def fake_run(args, *, env=None, timeout=15):
        captured.update(args=args, env=env, timeout=timeout)
        return {"results": [{"id": "mem-1", "status": "active"}], "result_count": 1}

    monkeypatch.setattr(plugin_runtime, "_run_context_cli_json", fake_run)
    result = search_context_memories(
        "recurring release failure",
        project_root="/tmp/project",
        mode="hybrid",
        limit=250,
        env={"ACROSS_HOME": "/tmp/across"},
    )

    assert captured["args"] == [
        "search",
        "recurring release failure",
        "--mode",
        "hybrid",
        "--limit",
        "100",
        "--json",
        "--project",
        "/tmp/project",
    ]
    assert "--status" not in captured["args"]
    assert result["result_count"] == 1


def test_search_context_memories_allows_explicit_pending_review(monkeypatch):
    captured = {}

    def fake_run(args, *, env=None, timeout=15):
        captured["args"] = args
        return {"results": [], "result_count": 0}

    monkeypatch.setattr(plugin_runtime, "_run_context_cli_json", fake_run)
    search_context_memories("candidate", status="pending")

    assert captured["args"][-3:] == ["--status", "pending", "--review-pending"]


@pytest.mark.parametrize("query,mode", [("", "hybrid"), ("valid", "unknown")])
def test_search_context_memories_rejects_invalid_input(query, mode):
    with pytest.raises(PluginLifecycleError):
        search_context_memories(query, mode=mode)


def test_search_context_memories_rejects_non_object_payload(monkeypatch):
    monkeypatch.setattr(plugin_runtime, "_run_context_cli_json", lambda *args, **kwargs: [])

    with pytest.raises(PluginLifecycleError, match="unexpected search payload"):
        search_context_memories("release evidence")


def test_improve_context_memory_builds_bounded_governed_command(monkeypatch):
    captured = {}

    def fake_run(args, *, env=None, timeout=15):
        captured.update(args=args, timeout=timeout)
        return {
            "schema_version": "across-context-memory-distillation/1.0",
            "approval_required": True,
            "proposals": [{"memory": {"id": "mem_proposal_1", "status": "pending"}}],
        }

    monkeypatch.setattr(plugin_runtime, "_run_context_cli_json", fake_run)
    result = improve_context_memory(
        project_root="/workspace/product",
        source_ids=["mem_source_1", "mem_source_1", "mem_source_2"],
        similarity_threshold=0.4,
        max_proposal_length=500,
    )

    assert captured == {
        "args": [
            "improve",
            "run",
            "--similarity-threshold",
            "0.4",
            "--max-proposal-length",
            "500",
            "--json",
            "--project",
            "/workspace/product",
            "--source-id",
            "mem_source_1",
            "--source-id",
            "mem_source_2",
        ],
        "timeout": 60,
    }
    assert result["approval_required"] is True
    assert result["proposals"][0]["memory"]["status"] == "pending"


def test_merged_retrieval_requires_explicit_pending_review(monkeypatch):
    with pytest.raises(PluginLifecycleError, match="requires explicit review"):
        retrieve_context_memories_merged("release", status="pending")

    captured = {}

    def fake_run(args, *, env=None, timeout=15):
        captured.update(args=args, timeout=timeout)
        return {
            "schema_version": "across-context-merged-retrieval/1.0",
            "strategy": "weighted-reciprocal-rank-fusion",
            "results": [],
        }

    monkeypatch.setattr(plugin_runtime, "_run_context_cli_json", fake_run)
    result = retrieve_context_memories_merged(
        "release",
        routes=["keyword", "loop_recall"],
        status="pending",
        review_pending=True,
        include_route_results=True,
        limit=5,
    )

    assert captured == {
        "args": [
            "retrieve",
            "release",
            "--routes",
            "keyword,loop_recall",
            "--limit",
            "5",
            "--json",
            "--status",
            "pending",
            "--review-pending",
            "--include-route-results",
        ],
        "timeout": 30,
    }
    assert result["strategy"] == "weighted-reciprocal-rank-fusion"


@pytest.mark.parametrize(
    "call",
    [
        lambda: improve_context_memory(project_root="relative/project"),
        lambda: improve_context_memory(project_root="/project", include_projects=True),
        lambda: improve_context_memory(source_ids=["invalid id"]),
        lambda: retrieve_context_memories_merged("release", routes=["keyword", "keyword"]),
        lambda: retrieve_context_memories_merged("release", review_pending=True),
    ],
)
def test_context_vnext_memory_calls_reject_ambiguous_or_invalid_input(call):
    with pytest.raises(PluginLifecycleError):
        call()


def test_rollback_and_status_approval_use_governed_context_commands(monkeypatch):
    calls = []

    def fake_run(args, *, env=None, timeout=15):
        calls.append((args, timeout))
        if args[:2] == ["improve", "rollback"]:
            return {
                "schema_version": "across-context-distilled-memory-rollback/1.0",
                "proposal_id": "mem_proposal_1",
                "status": "archived",
                "restored_source_ids": ["mem_source_1"],
            }
        return {
            "schema_version": "across-context-distilled-memory-approval/1.0",
            "proposal_id": "mem_proposal_1",
            "status": "active",
            "archived_source_ids": ["mem_source_1"],
        }

    monkeypatch.setattr(plugin_runtime, "_run_context_cli_json", fake_run)

    approved = update_context_memory_status("mem_proposal_1", "active")
    rolled_back = rollback_distilled_context_memory("mem_proposal_1")

    assert calls == [
        (["approve", "mem_proposal_1", "--json"], 15),
        (["improve", "rollback", "mem_proposal_1", "--json"], 15),
    ]
    assert approved["archived_source_ids"] == ["mem_source_1"]
    assert approved["id"] == "mem_proposal_1"
    assert rolled_back["restored_source_ids"] == ["mem_source_1"]


def test_context_cli_timeout_and_missing_memory_errors_do_not_echo_details(monkeypatch, tmp_path):
    across_home = tmp_path / "across"
    command = across_home / "bin" / "across-context"
    command.parent.mkdir(parents=True)
    command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    command.chmod(0o755)
    env = {"ACROSS_HOME": str(across_home)}

    def timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"], stderr="private diagnostics")

    monkeypatch.setattr(plugin_runtime.subprocess, "run", timeout_run)
    with pytest.raises(PluginLifecycleError, match="^across-context command timed out$"):
        plugin_runtime._run_context_cli_json(["improve", "run", "--json"], env=env, timeout=1)

    def missing_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, stdout="", stderr="Memory not found: /private/record")

    monkeypatch.setattr(plugin_runtime.subprocess, "run", missing_run)
    with pytest.raises(PluginLifecycleError, match="^Across Context memory was not found$"):
        plugin_runtime._run_context_cli_json(["improve", "rollback", "mem_missing", "--json"], env=env)
