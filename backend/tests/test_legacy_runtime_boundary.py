import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import across_agents_assistant
import across_agents_assistant.api_server as api_server


PACKAGE_ROOT = Path(across_agents_assistant.__file__).resolve().parent


def test_legacy_runtime_module_is_not_packaged():
    assert importlib.util.find_spec("across_agents_assistant.legacy_task_runtime") is None
    assert not (PACKAGE_ROOT / "legacy_task_runtime.py").exists()


def test_api_server_exposes_only_external_orchestrator_boundary():
    source = Path(api_server.__file__).read_text(encoding="utf-8")

    assert "task_manager.orchestration.orchestrator import TaskOrchestrator" not in source
    assert "from .legacy_task_runtime import build_legacy_task_orchestrator" not in source
    assert "build_legacy_task_orchestrator" not in source
    assert "get_task_orchestrator" not in source
    assert "_task_orchestrator" not in source
    assert "/api/legacy/tasks" not in source
    assert "historical in-app TaskOrchestrator" not in source


def test_production_code_does_not_import_historical_runtime_construction():
    forbidden = {
        "legacy_task_runtime",
        "task_manager.orchestration.orchestrator import TaskOrchestrator",
        "task_manager.orchestration.owner_agent import OwnerAgent",
        "task_manager.orchestration.validator import ContractValidator",
    }
    offenders: dict[str, list[str]] = {}
    for path in PACKAGE_ROOT.rglob("*.py"):
        rel = path.relative_to(PACKAGE_ROOT)
        if rel.parts[:2] == ("task_manager", "orchestration"):
            continue
        source = path.read_text(encoding="utf-8")
        matches = sorted(token for token in forbidden if token in source)
        if matches:
            offenders[str(rel)] = matches

    assert offenders == {}


def test_api_import_does_not_load_historical_runtime_modules():
    script = """
import sys
import across_agents_assistant.api_server
forbidden = [
    "across_agents_assistant.task_manager.orchestration.orchestrator",
    "across_agents_assistant.task_manager.orchestration.owner_agent",
    "across_agents_assistant.task_manager.orchestration.validator",
]
loaded = [name for name in forbidden if name in sys.modules]
if loaded:
    raise SystemExit("loaded historical runtime modules: " + ", ".join(loaded))
"""
    env = dict(os.environ)
    package_src = str(PACKAGE_ROOT.parent)
    env["PYTHONPATH"] = f"{package_src}{os.pathsep}{env.get('PYTHONPATH', '')}"

    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
