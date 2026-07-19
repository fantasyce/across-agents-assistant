import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import across_agents_assistant
import across_agents_assistant.api_server as api_server
from across_agents_assistant.task_api_models import TaskInfo, TaskSummaryInfo
from across_agents_assistant.task_history.state import TaskState


PACKAGE_ROOT = Path(across_agents_assistant.__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parents[2]


def _missing_module_spec(module_name: str):
    try:
        return importlib.util.find_spec(module_name)
    except ModuleNotFoundError:
        return None


def test_removed_runtime_module_is_not_packaged():
    assert _missing_module_spec("across_agents_assistant.legacy_task_runtime") is None
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
        PACKAGE_ROOT / "task_manager",
        PACKAGE_ROOT / "task_manager/orchestration/orchestrator.py",
        PACKAGE_ROOT / "task_manager/orchestration/owner_agent.py",
        PACKAGE_ROOT / "task_manager/orchestration/validator.py",
        PACKAGE_ROOT / "task_manager/dispatcher.py",
        PACKAGE_ROOT / "task_manager/task_decomposer.py",
    ):
        assert not module_path.exists()

    for module_name in (
        "across_agents_assistant.task_manager",
        "across_agents_assistant.task_manager.models",
        "across_agents_assistant.task_manager.state",
        "across_agents_assistant.task_manager.orchestration",
        "across_agents_assistant.task_manager.orchestration.orchestrator",
        "across_agents_assistant.task_manager.orchestration.owner_agent",
        "across_agents_assistant.task_manager.orchestration.validator",
        "across_agents_assistant.task_manager.dispatcher",
        "across_agents_assistant.task_manager.task_decomposer",
    ):
        assert _missing_module_spec(module_name) is None


def test_removed_desktop_runtime_entrypoints_are_removed():
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


def test_packaged_build_isolates_build_time_runtime_state_from_formal_user_data():
    script = (PROJECT_ROOT / "build_app.sh").read_text(encoding="utf-8")
    isolation_index = script.index('export ACROSS_HOME="$BUILD_RUNTIME_DIR/across-home"')
    pyinstaller_index = script.index('echo "Running PyInstaller..."')

    assert isolation_index < pyinstaller_index
    assert 'export ACROSS_AGENTS_HOME="$BUILD_RUNTIME_DIR/across-agents-home"' in script
    assert 'export ACROSS_CONTEXT_HOME="$BUILD_RUNTIME_DIR/across-context-home"' in script
    assert 'export ACROSS_AUTOPILOT_HOME="$BUILD_RUNTIME_DIR/across-autopilot-home"' in script
    assert 'export ACROSS_ORCHESTRATOR_HOME="$BUILD_RUNTIME_DIR/across-orchestrator-home"' in script
    assert "trap cleanup_build_runtime EXIT" in script


def test_readme_does_not_describe_historical_task_orchestrator_residue():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "historical in-app `TaskOrchestrator` code remains" not in readme
    assert "legacy task data inspection" not in readme


def test_task_api_defaults_are_external():
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


def test_removed_task_manager_package_is_removed():
    assert not (PACKAGE_ROOT / "task_manager").exists()
    for module_name in (
        "across_agents_assistant.task_manager",
        "across_agents_assistant.task_manager.models",
        "across_agents_assistant.task_manager.state",
        "across_agents_assistant.task_manager.orchestration",
    ):
        assert _missing_module_spec(module_name) is None


def test_removed_task_history_package_name_is_removed():
    assert not (PACKAGE_ROOT / "legacy_task_history").exists()
    for module_name in (
        "across_agents_assistant.legacy_task_history",
        "across_agents_assistant.legacy_task_history.models",
        "across_agents_assistant.legacy_task_history.state",
    ):
        assert _missing_module_spec(module_name) is None


def test_local_agent_package_does_not_export_removed_alias():
    import across_agents_assistant.local_agent as local_agent_pkg

    assert hasattr(local_agent_pkg, "UniversalAgentClient")
    assert "UniversalAgentClient" in getattr(local_agent_pkg, "__all__", [])
    assert not hasattr(local_agent_pkg, "LocalAgentClient")
    assert "LocalAgentClient" not in getattr(local_agent_pkg, "__all__", [])


def test_tests_use_task_review_path_except_removed_boundary_tests():
    offenders: dict[str, list[str]] = {}
    for path in (PROJECT_ROOT / "backend/tests").rglob("*.py"):
        rel = path.relative_to(PROJECT_ROOT)
        if path.name == "test_removed_runtime_boundary.py":
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


def test_task_history_owns_task_state_and_models_source():
    for module_name in ("models", "state"):
        spec = importlib.util.find_spec(f"across_agents_assistant.task_history.{module_name}")
        assert spec is not None
        assert spec.origin is not None
        assert f"task_history/{module_name}.py" in spec.origin

    state_source = (PACKAGE_ROOT / "task_history/state.py").read_text(encoding="utf-8")
    models_source = (PACKAGE_ROOT / "task_history/models.py").read_text(encoding="utf-8")
    assert "class TaskState" in state_source
    assert "class OrchestratorState" in models_source


def test_production_code_uses_task_history_not_task_manager_state_or_models():
    offenders: dict[str, list[str]] = {}
    for path in PACKAGE_ROOT.rglob("*.py"):
        rel = path.relative_to(PACKAGE_ROOT)
        rel_text = str(rel)
        if rel_text.startswith("task_history/"):
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


def test_production_code_does_not_reference_task_manager_namespace():
    offenders: dict[str, list[str]] = {}
    for path in PACKAGE_ROOT.rglob("*.py"):
        rel = path.relative_to(PACKAGE_ROOT)
        source = path.read_text(encoding="utf-8")
        matches = [
            token
            for token in (
                "task_manager",
                "task manager",
            )
            if token in source
        ]
        if matches:
            offenders[str(rel)] = matches

    assert offenders == {}


def test_production_code_does_not_reference_source_tree_import_prefix():
    offenders: dict[str, list[str]] = {}
    for path in PACKAGE_ROOT.rglob("*.py"):
        rel = path.relative_to(PACKAGE_ROOT)
        source = path.read_text(encoding="utf-8")
        matches = [
            token
            for token in (
                "backend.src.",
                "from backend.src",
                "import backend.src",
            )
            if token in source
        ]
        if matches:
            offenders[str(rel)] = matches

    assert offenders == {}


def test_tests_use_task_history_path_except_removed_boundary_tests():
    offenders: dict[str, list[str]] = {}
    for path in (PROJECT_ROOT / "backend/tests").rglob("*.py"):
        rel = path.relative_to(PROJECT_ROOT)
        if path.name == "test_removed_runtime_boundary.py":
            continue
        source = path.read_text(encoding="utf-8")
        matches = [
            token
            for token in (
                "across_agents_assistant.task_manager.models",
                "across_agents_assistant.task_manager.state",
                "across_agents_assistant.legacy_task_history",
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
