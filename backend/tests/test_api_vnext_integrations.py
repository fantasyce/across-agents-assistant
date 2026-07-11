from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

import across_agents_assistant.api_server as api_server
from across_agents_assistant.api_server import app
from across_agents_assistant.plugin_runtime import PluginLifecycleError, run_autopilot_cli_json


def test_local_agent_client_singleton_is_safe_for_parallel_workspace_start(monkeypatch):
    import across_agents_assistant.local_agent.client as local_client

    created = []

    class FakeClient:
        def __init__(self, manager):
            created.append(manager)

    monkeypatch.setattr(local_client, "UniversalAgentClient", FakeClient)
    monkeypatch.setattr(api_server, "_local_agent_client", None)

    with ThreadPoolExecutor(max_workers=8) as executor:
        clients = list(executor.map(lambda _index: api_server.get_local_agent_client(), range(32)))

    assert len({id(client) for client in clients}) == 1
    assert created == [api_server.agent_manager]


def test_quality_gate_endpoint_returns_structured_blocked_result(monkeypatch, tmp_path: Path):
    captured = {}

    class FakeAutopilotClient:
        def gate(self, repo_root, **kwargs):
            captured.update(repo_root=repo_root, **kwargs)
            return {
                "schema_version": "across-autopilot-gate-result/1.0",
                "repository": {"path": repo_root},
                "findings": [{"id": "secret", "state": "blocked", "severity": "critical"}],
                "gate_verdict": "blocked",
                "evidence_hash": "a" * 64,
            }

    monkeypatch.setattr(api_server, "get_autopilot_client", lambda: FakeAutopilotClient())

    response = TestClient(app).post(
        "/api/quality-gates/run",
        json={
            "repo_root": str(tmp_path),
            "base_ref": "main",
            "head_ref": "HEAD",
            "branch": "feature/quality",
            "commit": "abc123",
            "draft_pr": True,
            "max_repairs": 2,
            "timeout_seconds": 120,
        },
    )

    assert response.status_code == 200
    assert response.json()["gate_verdict"] == "blocked"
    assert captured == {
        "repo_root": str(tmp_path),
        "base_ref": "main",
        "head_ref": "HEAD",
        "branch": "feature/quality",
        "commit": "abc123",
        "ci_path": None,
        "ci_wait_seconds": 0,
        "draft_pr": True,
        "push_branch": False,
        "approve_remote": False,
        "watch_ci": None,
        "ci_idle_timeout_seconds": None,
        "ci_max_wall_timeout_seconds": None,
        "max_repairs": 2,
        "timeout": 120,
    }


def test_quality_gate_endpoint_forwards_remote_intent_without_accepting_credentials(monkeypatch, tmp_path: Path):
    captured = {}

    class FakeAutopilotClient:
        def gate(self, repo_root, **kwargs):
            captured.update(repo_root=repo_root, **kwargs)
            return {
                "schema_version": "across-autopilot-gate-result/1.0",
                "gate_verdict": "pass",
                "github_remote": {
                    "status": "failed",
                    "recoverable": True,
                    "authorization": {
                        "approval_token_env": "ACROSS_REPO_GATE_APPROVAL_TOKEN",
                        "approval_token_verified": True,
                        "credential_present": True,
                        "secret_material_included": False,
                    },
                    "ci_watch": {
                        "status": "idle_timeout",
                        "heartbeats": [{"sequence": 4, "observed_at": "2026-07-11T02:00:00Z"}],
                    },
                    "operations": [
                        {
                            "id": "draft_pr",
                            "status": "unknown_after_attempt",
                            "recovery": "rerun_with_same_idempotency_key",
                        }
                    ],
                    "approval_token": "plain-approval-material",
                    "errors": ["request failed with github_pat_fixture_response_credential"],
                },
            }

    monkeypatch.setattr(api_server, "get_autopilot_client", lambda: FakeAutopilotClient())
    client = TestClient(app)
    response = client.post(
        "/api/quality-gates/run",
        json={
            "repo_root": str(tmp_path),
            "base_ref": "main",
            "head_ref": "HEAD",
            "branch": "feature/remote-gate",
            "draft_pr": True,
            "push_branch": True,
            "approve_remote": True,
            "watch_ci": True,
            "ci_idle_timeout_seconds": 300,
            "ci_max_wall_timeout_seconds": 7_200,
            "timeout_seconds": 8_000,
        },
    )

    assert response.status_code == 200
    assert captured["push_branch"] is True
    assert captured["approve_remote"] is True
    assert captured["watch_ci"] is True
    assert captured["ci_idle_timeout_seconds"] == 300
    assert captured["ci_max_wall_timeout_seconds"] == 7_200
    payload = response.json()
    serialized = response.text
    assert "plain-approval-material" not in serialized
    assert "github_pat_fixture_response_credential" not in serialized
    assert payload["github_remote"]["approval_token"] == "[redacted]"
    assert payload["github_remote"]["ci_watch"]["heartbeats"][0]["sequence"] == 4
    assert payload["github_remote"]["operations"][0]["recovery"] == "rerun_with_same_idempotency_key"

    rejected = client.post(
        "/api/quality-gates/run",
        json={"repo_root": str(tmp_path), "gh_token": "must-not-cross-api-boundary"},
    )
    assert rejected.status_code == 422


def test_memory_search_endpoint_keeps_pending_behind_explicit_status(monkeypatch):
    calls = []

    def fake_search(query, **kwargs):
        calls.append((query, kwargs))
        return {"results": [], "status_filter": kwargs.get("status")}

    monkeypatch.setattr(api_server, "search_context_memories", fake_search)
    client = TestClient(app)

    ordinary = client.post("/api/memory/search", json={"query": "release evidence"})
    pending = client.post(
        "/api/memory/search",
        json={"query": "release evidence", "status": "pending", "mode": "keyword", "limit": 5},
    )
    invalid = client.post(
        "/api/memory/search",
        json={"query": "release evidence", "status": "archived"},
    )

    assert ordinary.status_code == 200
    assert pending.status_code == 200
    assert invalid.status_code == 400
    assert calls[0][1]["status"] is None
    assert calls[1][1]["status"] == "pending"


def test_memory_vnext_endpoints_connect_improve_merged_retrieval_and_rollback(monkeypatch):
    calls = []

    def fake_improve(**kwargs):
        calls.append(("improve", kwargs))
        return {
            "schema_version": "across-context-memory-distillation/1.0",
            "approval_required": True,
            "project_root": "/Users/example/private-project",
            "access_token": "sensitive-value",
            "proposals": [
                {
                    "memory": {"id": "mem_proposal_1", "status": "pending"},
                    "proposal": {"summary": "Use /tmp/private-output and password=sensitive-value"},
                }
            ],
        }

    def fake_retrieve(query, **kwargs):
        calls.append(("retrieve", {"query": query, **kwargs}))
        return {
            "schema_version": "across-context-merged-retrieval/1.0",
            "strategy": "weighted-reciprocal-rank-fusion",
            "results": [{"entry": {"id": "mem_active_1", "status": "active"}}],
        }

    def fake_rollback(memory_id):
        calls.append(("rollback", {"memory_id": memory_id}))
        return {
            "schema_version": "across-context-distilled-memory-rollback/1.0",
            "proposal_id": memory_id,
            "status": "archived",
            "restored_source_ids": ["mem_source_1"],
        }

    monkeypatch.setattr(api_server, "improve_context_memory", fake_improve)
    monkeypatch.setattr(api_server, "retrieve_context_memories_merged", fake_retrieve)
    monkeypatch.setattr(api_server, "rollback_distilled_context_memory", fake_rollback)
    client = TestClient(app)

    improved = client.post(
        "/api/memory/improve",
        json={
            "projectRoot": "/workspace/product",
            "sourceIds": ["mem_source_1"],
            "similarityThreshold": 0.4,
            "maxProposalLength": 500,
        },
    )
    retrieved = client.post(
        "/api/memory/retrieve/merged",
        json={"query": "release timeout", "routes": ["keyword", "loop_recall"], "limit": 5},
    )
    rolled_back = client.post("/api/memory/distilled/mem_proposal_1/rollback")

    assert improved.status_code == 200
    assert improved.json()["approval_required"] is True
    assert improved.json()["proposals"][0]["memory"]["status"] == "pending"
    assert improved.json()["project_root"] == "[local-path]"
    assert improved.json()["access_token"] == "[redacted]"
    assert "/tmp/" not in improved.json()["proposals"][0]["proposal"]["summary"]
    assert "sensitive-value" not in improved.json()["proposals"][0]["proposal"]["summary"]
    assert retrieved.status_code == 200
    assert retrieved.json()["strategy"] == "weighted-reciprocal-rank-fusion"
    assert rolled_back.status_code == 200
    assert rolled_back.json()["restored_source_ids"] == ["mem_source_1"]
    assert calls == [
        (
            "improve",
            {
                "project_root": "/workspace/product",
                "include_projects": False,
                "source_ids": ["mem_source_1"],
                "similarity_threshold": 0.4,
                "max_proposal_length": 500,
            },
        ),
        (
            "retrieve",
            {
                "query": "release timeout",
                "routes": ["keyword", "loop_recall"],
                "project_root": None,
                "include_projects": False,
                "status": None,
                "review_pending": False,
                "limit": 5,
                "include_route_results": False,
            },
        ),
        ("rollback", {"memory_id": "mem_proposal_1"}),
    ]


def test_merged_memory_endpoint_keeps_pending_behind_review_flag(monkeypatch):
    calls = []

    def fake_retrieve(query, **kwargs):
        calls.append((query, kwargs))
        return {"results": [], "pending_review": True}

    monkeypatch.setattr(api_server, "retrieve_context_memories_merged", fake_retrieve)
    client = TestClient(app)

    blocked = client.post(
        "/api/memory/retrieve/merged",
        json={"query": "candidate", "status": "pending"},
    )
    reviewed = client.post(
        "/api/memory/retrieve/merged",
        json={"query": "candidate", "status": "pending", "reviewPending": True},
    )

    assert blocked.status_code == 400
    assert reviewed.status_code == 200
    assert len(calls) == 1
    assert calls[0][1]["status"] == "pending"
    assert calls[0][1]["review_pending"] is True


def test_memory_vnext_endpoint_maps_plugin_failures_without_echo(monkeypatch):
    client = TestClient(app)

    monkeypatch.setattr(
        api_server,
        "improve_context_memory",
        lambda **_: (_ for _ in ()).throw(PluginLifecycleError("across-context plugin is not installed at /Users/example")),
    )
    unavailable = client.post("/api/memory/improve", json={})

    monkeypatch.setattr(
        api_server,
        "retrieve_context_memories_merged",
        lambda *_, **__: (_ for _ in ()).throw(PluginLifecycleError("across-context command timed out: sensitive-value")),
    )
    timed_out = client.post("/api/memory/retrieve/merged", json={"query": "release"})

    monkeypatch.setattr(
        api_server,
        "rollback_distilled_context_memory",
        lambda *_: (_ for _ in ()).throw(PluginLifecycleError("Memory not found: /private/record")),
    )
    missing = client.post("/api/memory/distilled/mem_missing/rollback")

    assert unavailable.status_code == 503
    assert timed_out.status_code == 504
    assert missing.status_code == 404
    responses = unavailable.text + timed_out.text + missing.text
    assert "/Users/" not in responses
    assert "/private/" not in responses
    assert "sensitive-value" not in responses


def test_autopilot_json_runner_accepts_completed_blocked_exit_code(tmp_path: Path):
    across_home = tmp_path / ".across"
    command = across_home / "bin" / "across-autopilot"
    command.parent.mkdir(parents=True)
    command.write_text(
        "#!/bin/sh\nprintf '%s\\n' '{\"schema_version\":\"across-autopilot-gate-result/1.0\",\"gate_verdict\":\"blocked\"}'\nexit 2\n",
        encoding="utf-8",
    )
    command.chmod(0o755)

    result = run_autopilot_cli_json(
        ["gate", "--repo", str(tmp_path), "--json"],
        env={"ACROSS_HOME": str(across_home)},
        allowed_returncodes=frozenset({0, 2}),
    )

    assert result["gate_verdict"] == "blocked"
