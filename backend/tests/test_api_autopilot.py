import json
from pathlib import Path

from fastapi.testclient import TestClient

from across_agents_assistant.api_server import app


def _write_fake_autopilot(across_home: Path) -> Path:
    bin_dir = across_home / "bin"
    bin_dir.mkdir(parents=True)
    path = bin_dir / "across-autopilot"
    path.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        "  status) printf '{\"schema_version\":\"across-autopilot-state/1.0\",\"autonomy_level\":1,\"stable_slot\":{\"version\":\"0.1.0\"},\"candidate_slot\":null}\\n' ;;\n"
        "  review) printf '{\"schema_version\":\"across-autopilot-review/1.0\",\"mode\":\"host\",\"source_count\":2,\"findings\":[{\"id\":\"stable-candidate-control\"}],\"candidate_backlog\":[{\"id\":\"radar\",\"target_product\":\"across-autopilot\"}]}\\n' ;;\n"
        "  candidate-plan) printf '{\"schema_version\":\"across-autopilot-candidate-plan/1.0\",\"goal\":\"Ship Autopilot\",\"target_product\":\"across-autopilot\",\"execution\":{\"engine\":\"across-orchestrator\"},\"memory_policy\":{\"provider\":\"across-context\"}}\\n' ;;\n"
        "  *) printf '{}\\n' ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def test_autopilot_status_review_and_candidate_plan_endpoints(monkeypatch, tmp_path):
    across_home = tmp_path / "across"
    _write_fake_autopilot(across_home)
    monkeypatch.setenv("ACROSS_HOME", str(across_home))
    monkeypatch.setenv("PATH", "")

    client = TestClient(app)

    status = client.get("/api/autopilot/status")
    assert status.status_code == 200
    assert status.json()["stable_slot"]["version"] == "0.1.0"

    review = client.post("/api/autopilot/review", json={"fetch": False})
    assert review.status_code == 200
    assert review.json()["schema_version"] == "across-autopilot-review/1.0"
    assert review.json()["findings"][0]["id"] == "stable-candidate-control"

    plan = client.post(
        "/api/autopilot/candidate-plan",
        json={"goal": "Ship Autopilot", "target_product": "across-autopilot"},
    )
    assert plan.status_code == 200
    assert plan.json()["execution"]["engine"] == "across-orchestrator"
    assert plan.json()["memory_policy"]["provider"] == "across-context"


def test_autopilot_endpoint_reports_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("ACROSS_HOME", str(tmp_path / "across"))
    monkeypatch.setenv("PATH", "")

    response = TestClient(app).get("/api/autopilot/status")

    assert response.status_code == 503
    assert response.json()["detail"] == "Across Autopilot plugin is not available"
