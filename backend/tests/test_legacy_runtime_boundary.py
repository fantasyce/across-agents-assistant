import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import across_agents_assistant
import across_agents_assistant.api_server as api_server
from across_agents_assistant.task_api_models import TaskInfo, TaskSummaryInfo
from across_agents_assistant.legacy_task_history.state import TaskState


PACKAGE_ROOT = Path(across_agents_assistant.__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parents[2]


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
    assert "TaskDispatcher(" not in source
    assert "def get_task_dispatcher" not in source


def test_production_code_does_not_import_historical_runtime_construction():
    forbidden = {
        "legacy_task_runtime",
        "task_manager.dispatcher",
        "task_manager.task_decomposer",
        "task_manager.orchestration.orchestrator import TaskOrchestrator",
        "task_manager.orchestration.owner_agent import OwnerAgent",
        "task_manager.orchestration.validator import ContractValidator",
    }
    offenders: dict[str, list[str]] = {}
    for path in PACKAGE_ROOT.rglob("*.py"):
        rel = path.relative_to(PACKAGE_ROOT)
        source = path.read_text(encoding="utf-8")
        matches = sorted(token for token in forbidden if token in source)
        if matches:
            offenders[str(rel)] = matches

    assert offenders == {}


def test_historical_runtime_source_modules_are_removed():
    for module_path in (
        PACKAGE_ROOT / "task_manager/orchestration/orchestrator.py",
        PACKAGE_ROOT / "task_manager/orchestration/owner_agent.py",
        PACKAGE_ROOT / "task_manager/orchestration/validator.py",
        PACKAGE_ROOT / "task_manager/dispatcher.py",
        PACKAGE_ROOT / "task_manager/task_decomposer.py",
    ):
        assert not module_path.exists()

    for module_name in (
        "across_agents_assistant.task_manager.orchestration.orchestrator",
        "across_agents_assistant.task_manager.orchestration.owner_agent",
        "across_agents_assistant.task_manager.orchestration.validator",
        "across_agents_assistant.task_manager.dispatcher",
        "across_agents_assistant.task_manager.task_decomposer",
    ):
        assert importlib.util.find_spec(module_name) is None


def test_legacy_desktop_runtime_entrypoints_are_removed():
    for module_path in (
        PACKAGE_ROOT / "app.py",
        PACKAGE_ROOT / "main_ui.py",
        PACKAGE_ROOT / "menubar.py",
    ):
        assert not module_path.exists()

    cli_source = (PACKAGE_ROOT / "cli.py").read_text(encoding="utf-8")
    assert "AcrossAgentsAssistantApp" not in cli_source
    assert "TaskDecomposer" not in cli_source
    assert "TaskDispatcher" not in cli_source
    assert "run_menubar" not in cli_source


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


def test_packaged_build_no_longer_needs_historical_runtime_surgery():
    script = (PROJECT_ROOT / "build_app.sh").read_text(encoding="utf-8")

    for module_name in (
        "across_agents_assistant.task_manager.orchestration.orchestrator",
        "across_agents_assistant.task_manager.orchestration.owner_agent",
        "across_agents_assistant.task_manager.orchestration.validator",
    ):
        assert module_name not in script

    assert "LEGACY_ORCHESTRATION_MODULES" not in script


def test_packaged_build_cleans_python_bytecode_before_collecting_package():
    script_lines = (PROJECT_ROOT / "build_app.sh").read_text(encoding="utf-8").splitlines()

    pycache_cleanup = 'find src/across_agents_assistant -type d -name "__pycache__" -prune -exec rm -rf {} +'
    pyc_cleanup = 'find src/across_agents_assistant -type f -name "*.pyc" -delete'
    collect_package = "--collect-all across_agents_assistant"

    pycache_index = script_lines.index(pycache_cleanup)
    pyc_index = script_lines.index(pyc_cleanup)
    collect_index = next(
        index
        for index, line in enumerate(script_lines)
        if line.strip().startswith(collect_package)
    )

    assert pycache_index < collect_index
    assert pyc_index < collect_index


def test_readme_does_not_describe_historical_task_orchestrator_residue():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "historical in-app `TaskOrchestrator` code remains" not in readme
    assert "legacy task data inspection" not in readme


def test_task_api_defaults_are_external_not_legacy():
    assert TaskInfo.model_fields["delivery_mode"].default == "external"
    assert TaskSummaryInfo.model_fields["delivery_mode"].default == "external"
    assert TaskState._normalize_delivery_task_types(None) == ([], "external")


def test_api_server_does_not_reference_missing_created_status():
    source = Path(api_server.__file__).read_text(encoding="utf-8")

    assert "TaskStatus.CREATED" not in source


def test_aaa_chat_tool_loop_is_named_apart_from_task_agent_loop():
    import across_agents_assistant.agent_loop as chat_loop_pkg

    bridge_source = (PACKAGE_ROOT / "agent_bridge/agent.py").read_text(encoding="utf-8")
    api_source = Path(api_server.__file__).read_text(encoding="utf-8")
    harness_exports = (PACKAGE_ROOT / "harness/__init__.py").read_text(encoding="utf-8")

    assert hasattr(chat_loop_pkg, "ChatToolLoop")
    assert "AgentLoop" not in getattr(chat_loop_pkg, "__all__", [])
    assert "ChatToolLoop(" in bridge_source
    assert "AgentLoop(" not in bridge_source
    assert "async def _run_chat_tool_loop" in api_source
    assert "async def _run_agent_loop" not in api_source
    assert "ChatToolLoopStateMachine" in harness_exports
    assert "AgentLoopStateMachine" not in harness_exports


def test_task_review_helpers_are_exposed_outside_orchestration_namespace():
    review_spec = importlib.util.find_spec("across_agents_assistant.task_review.contract_acceptance")
    assert review_spec is not None
    assert review_spec.origin is not None
    assert "task_review/contract_acceptance.py" in review_spec.origin

    legacy_init = (PACKAGE_ROOT / "task_manager/orchestration/__init__.py").read_text(encoding="utf-8")
    assert "Deprecated compatibility import path" in legacy_init
    assert "does not dispatch" in legacy_init


def test_task_review_modules_own_their_implementation_source():
    review_dir = PACKAGE_ROOT / "task_review"
    offenders = {}
    for path in review_dir.glob("*.py"):
        if path.name == "__init__.py":
            continue
        source = path.read_text(encoding="utf-8")
        if "task_manager.orchestration" in source:
            offenders[path.name] = "re-exports historical orchestration module"

    assert offenders == {}


def test_legacy_orchestration_modules_are_compatibility_shims_only():
    legacy_dir = PACKAGE_ROOT / "task_manager/orchestration"
    offenders = {}
    for path in legacy_dir.glob("*.py"):
        if path.name == "__init__.py":
            continue
        source = path.read_text(encoding="utf-8")
        expected_import = f"from across_agents_assistant.task_review.{path.stem} import *"
        if expected_import not in source or len(source.splitlines()) > 6:
            offenders[path.name] = "not a minimal task_review compatibility shim"

    assert offenders == {}


def test_tests_use_task_review_path_except_compatibility_boundary_tests():
    offenders: dict[str, list[str]] = {}
    for path in (PROJECT_ROOT / "backend/tests").rglob("*.py"):
        rel = path.relative_to(PROJECT_ROOT)
        if path.name == "test_legacy_runtime_boundary.py":
            continue
        source = path.read_text(encoding="utf-8")
        matches = [
            token
            for token in (
                "across_agents_assistant.task_manager.orchestration",
                "from across_agents_assistant.task_manager import orchestration",
            )
            if token in source
        ]
        if matches:
            offenders[str(rel)] = matches

    assert offenders == {}


def test_legacy_task_history_owns_task_state_and_models_source():
    for module_name in ("models", "state"):
        spec = importlib.util.find_spec(f"across_agents_assistant.legacy_task_history.{module_name}")
        assert spec is not None
        assert spec.origin is not None
        assert f"legacy_task_history/{module_name}.py" in spec.origin

    legacy_state_source = (PACKAGE_ROOT / "legacy_task_history/state.py").read_text(encoding="utf-8")
    legacy_models_source = (PACKAGE_ROOT / "legacy_task_history/models.py").read_text(encoding="utf-8")
    assert "class TaskState" in legacy_state_source
    assert "class OrchestratorState" in legacy_models_source


def test_task_manager_models_and_state_are_compatibility_shims_only():
    expected = {
        "models.py": "from across_agents_assistant.legacy_task_history.models import *",
        "state.py": "from across_agents_assistant.legacy_task_history.state import *",
    }
    offenders = {}
    for file_name, expected_import in expected.items():
        source = (PACKAGE_ROOT / f"task_manager/{file_name}").read_text(encoding="utf-8")
        if expected_import not in source or len(source.splitlines()) > 6:
            offenders[file_name] = "not a minimal legacy_task_history compatibility shim"

    assert offenders == {}


def test_production_code_uses_legacy_task_history_not_task_manager_state_or_models():
    offenders: dict[str, list[str]] = {}
    for path in PACKAGE_ROOT.rglob("*.py"):
        rel = path.relative_to(PACKAGE_ROOT)
        rel_text = str(rel)
        if rel_text.startswith("task_manager/") or rel_text.startswith("legacy_task_history/"):
            continue

        source = path.read_text(encoding="utf-8")
        matches = [
            token
            for token in (
                "task_manager.models",
                "task_manager.state",
                "from .task_manager",
            )
            if token in source
        ]
        if matches:
            offenders[rel_text] = matches

    assert offenders == {}


def test_tests_use_legacy_task_history_path_except_boundary_tests():
    offenders: dict[str, list[str]] = {}
    for path in (PROJECT_ROOT / "backend/tests").rglob("*.py"):
        rel = path.relative_to(PROJECT_ROOT)
        if path.name == "test_legacy_runtime_boundary.py":
            continue
        source = path.read_text(encoding="utf-8")
        matches = [
            token
            for token in (
                "across_agents_assistant.task_manager.models",
                "across_agents_assistant.task_manager.state",
            )
            if token in source
        ]
        if matches:
            offenders[str(rel)] = matches

    assert offenders == {}


def test_production_code_uses_task_review_facade_not_legacy_orchestration_path():
    offenders: dict[str, list[str]] = {}
    for path in PACKAGE_ROOT.rglob("*.py"):
        rel = path.relative_to(PACKAGE_ROOT)
        rel_text = str(rel)
        if rel_text.startswith("task_manager/orchestration/") or rel_text.startswith("task_review/"):
            continue

        source = path.read_text(encoding="utf-8")
        matches = [
            token
            for token in (
                "task_manager.orchestration",
                "task_manager/orchestration",
            )
            if token in source
        ]
        if matches:
            offenders[rel_text] = matches

    assert offenders == {}
