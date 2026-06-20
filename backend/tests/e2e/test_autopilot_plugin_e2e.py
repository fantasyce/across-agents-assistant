import os
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from across_agents_assistant.api_server import app


def test_autopilot_managed_plugin_end_to_end(tmp_path, monkeypatch):
    source = os.environ.get("ACROSS_AUTOPILOT_SOURCE")
    if not source:
        pytest.skip("ACROSS_AUTOPILOT_SOURCE is required for live Autopilot plugin E2E")
    source_root = Path(source).expanduser().resolve()
    cli = source_root / "src" / "cli.js"
    if not cli.is_file():
        pytest.skip("ACROSS_AUTOPILOT_SOURCE does not point at an Across Autopilot checkout")

    across_home = tmp_path / "across"
    install = subprocess.run(
        ["node", str(cli), "install", "host-plugin", "--across-home", str(across_home)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert install.returncode == 0, install.stderr

    monkeypatch.setenv("ACROSS_HOME", str(across_home))
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))

    client = TestClient(app)
    plugins = client.get("/api/plugins", params={"probe": "true"})
    assert plugins.status_code == 200
    autopilot = next(item for item in plugins.json()["plugins"] if item["plugin_id"] == "across-autopilot")
    assert autopilot["available"] is True
    assert autopilot["capabilities"]["autonomousReview"] is True

    review = client.post("/api/autopilot/review", json={"fetch": False, "mode": "e2e"})
    assert review.status_code == 200
    assert review.json()["schema_version"] == "across-autopilot-review/1.0"
    assert review.json()["candidate_backlog"]

    plan = client.post(
        "/api/autopilot/candidate-plan",
        json={
            "goal": "Review Across ecosystem and propose the next safe autonomous iteration",
            "target_product": "across-autopilot",
        },
    )
    assert plan.status_code == 200
    assert plan.json()["execution"]["engine"] == "across-orchestrator"
    assert plan.json()["memory_policy"]["provider"] == "across-context"
