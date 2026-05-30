import concurrent.futures
from pathlib import Path
from types import SimpleNamespace

import pytest

from across_agents_assistant.agent_bridge.agent import AgentSession
from across_agents_assistant.tools import builtin_tools  # noqa: F401 - registers built-in tools


def test_execution_prompt_discourages_clarifying_questions():
    session = AgentSession(agent_id="claude", client=object())

    prompt = session._build_execution_prompt(
        "Design FastAPI backend architecture",
        "/tmp/demo-project",
    )

    assert "Do not ask the user clarifying questions during execution." in prompt
    assert "choose the most standard implementation" in prompt
    assert "Do not preemptively complete downstream subtasks" in prompt
    assert "Project directory: /tmp/demo-project" in prompt
    assert "Design FastAPI backend architecture" in prompt


def test_execution_prompt_lists_local_agent_writable_assignment():
    session = AgentSession(agent_id="claude", client=object())

    prompt = session._build_execution_prompt(
        "Build dashboard JavaScript",
        "/tmp/demo-project",
        context={"allowed_writable_files": ["web/app.js", "/tmp/outside"]},
    )

    assert "Writable file assignment:" in prompt
    assert "- web/app.js" in prompt
    assert "/tmp/outside" not in prompt
    assert "Do not create or edit any other files" in prompt


def test_local_agent_invocation_forwards_bridge_timeout_to_client():
    captured = {}

    class FakeClient:
        def send(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text="done")

    session = AgentSession(agent_id="hermes", client=FakeClient())

    response = session.invoke("Repair quality gates", timeout=37.0, project_dir="/tmp/demo-project")

    assert response.success is True
    assert captured["timeout"] == 37.0


def test_cloud_tool_prompt_instructs_chunked_large_file_writes():
    session = AgentSession(agent_id="deepseek", client=object())

    prompt = session._build_cloud_tool_prompt("Build frontend", "/tmp/demo-project")

    assert "split the content across multiple write_file calls" in prompt
    assert "append=false for the first chunk" in prompt
    assert "append=true for later chunks" in prompt


def test_cloud_tool_prompt_lists_writable_file_assignment():
    session = AgentSession(agent_id="deepseek", client=object())

    prompt = session._build_cloud_tool_prompt(
        "Build app behavior",
        "/tmp/demo-project",
        allowed_writable_files=["web/app.js", "../ignored", "/tmp/outside.txt"],
    )

    assert "Writable file assignment:" in prompt
    assert "- web/app.js" in prompt
    assert "../ignored" not in prompt
    assert "/tmp/outside.txt" not in prompt
    assert "Do not create or edit any other files" in prompt


def test_workspace_write_file_tool_description_warns_about_large_arguments(tmp_path):
    session = AgentSession(agent_id="deepseek", client=object())
    project_dir = tmp_path / "workspace"
    project_dir.mkdir()

    registry = session._build_workspace_tool_registry(str(project_dir))
    write_tool = registry.get_tool("write_file")

    assert write_tool is not None
    assert "below about 6000 characters" in write_tool.description
    assert "append=true" in write_tool.description


def test_workspace_write_guard_rejects_unassigned_files(tmp_path):
    session = AgentSession(agent_id="deepseek", client=object())
    project_dir = tmp_path / "workspace"
    project_dir.mkdir()

    registry = session._build_workspace_tool_registry(
        str(project_dir),
        allowed_writable_files=["web/app.js"],
    )
    write_tool = registry.get_tool("write_file")

    with pytest.raises(ValueError) as exc:
        write_tool.handler(path="cli/quality-check.mjs", content="bad")

    assert "outside this subtask's writable file assignment" in str(exc.value)
    assert not (project_dir / "cli" / "quality-check.mjs").exists()


def test_workspace_write_guard_allows_assigned_file(tmp_path):
    session = AgentSession(agent_id="deepseek", client=object())
    project_dir = tmp_path / "workspace"
    project_dir.mkdir()

    registry = session._build_workspace_tool_registry(
        str(project_dir),
        allowed_writable_files=["web/app.js"],
    )
    write_tool = registry.get_tool("write_file")

    result = write_tool.handler(path="web/app.js", content="console.log('ok')\n")

    assert "Successfully wrote" in result["output"]
    assert (project_dir / "web" / "app.js").read_text(encoding="utf-8") == "console.log('ok')\n"


def test_cloud_tool_outcome_treats_iteration_limit_with_artifacts_as_success():
    session = AgentSession(agent_id="deepseek", client=object())
    result = SimpleNamespace(
        success=False,
        error="max_iterations_exceeded",
        final_answer="已达到最大迭代次数",
    )

    success, error, output = session._resolve_cloud_tool_outcome(
        result=result,
        created_files=["/tmp/demo/app/main.py", "/tmp/demo/requirements.txt"],
        modified_files=[],
        tool_failures=[],
    )

    assert success is True
    assert error is None
    assert "/tmp/demo/app/main.py" in output
    assert "Created files:" in output


def test_cloud_tool_outcome_tolerates_tool_failures_when_filesystem_artifacts_exist():
    session = AgentSession(agent_id="deepseek", client=object())
    result = SimpleNamespace(
        success=False,
        error="max_iterations_exceeded",
        final_answer="已达到最大迭代次数",
    )

    success, error, output = session._resolve_cloud_tool_outcome(
        result=result,
        created_files=["/tmp/demo/docker-compose.yml"],
        modified_files=[],
        tool_failures=[{"tool_name": "read_file", "message": "Error: transient"}],
    )

    assert success is True
    assert error is None
    assert "docker-compose.yml" in output


def test_cloud_tool_outcome_treats_review_diff_with_artifacts_as_success():
    session = AgentSession(agent_id="deepseek", client=object())
    result = SimpleNamespace(
        success=False,
        error="┊ review diff\na/frontend/index.html -> b/frontend/index.html",
        final_answer="",
    )

    success, error, output = session._resolve_cloud_tool_outcome(
        result=result,
        created_files=["/tmp/demo/frontend/index.html"],
        modified_files=[],
        tool_failures=[],
    )

    assert success is True
    assert error is None
    assert "/tmp/demo/frontend/index.html" in output


def test_cloud_llm_timeout_does_not_wait_for_executor_shutdown(monkeypatch):
    class FakeFuture:
        cancelled = False

        def result(self, timeout):
            raise concurrent.futures.TimeoutError()

        def cancel(self):
            self.cancelled = True

    class FakeExecutor:
        last = None

        def __init__(self, max_workers):
            self.max_workers = max_workers
            self.future = FakeFuture()
            self.shutdown_calls = []
            FakeExecutor.last = self

        def submit(self, fn):
            return self.future

        def shutdown(self, wait=True, cancel_futures=False):
            self.shutdown_calls.append({"wait": wait, "cancel_futures": cancel_futures})

    monkeypatch.setattr(concurrent.futures, "ThreadPoolExecutor", FakeExecutor)

    session = AgentSession(agent_id="deepseek", client=object(), llm_gateway=object())
    response = session._invoke_cloud_llm(
        message="Do work",
        context={},
        timeout=1,
        request_id="req-test",
        start_time=0,
        project_dir="/tmp/demo",
    )

    assert response.success is False
    assert "Timeout after" in response.error
    assert FakeExecutor.last.future.cancelled is True
    assert FakeExecutor.last.shutdown_calls == [{"wait": False, "cancel_futures": True}]


def test_diff_project_files_detects_created_and_modified_files(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    existing = project_dir / "existing.txt"
    existing.write_text("before")
    before = AgentSession._snapshot_project_files(str(project_dir))

    existing.write_text("after")
    created = project_dir / "new.txt"
    created.write_text("hello")

    created_files, modified_files = AgentSession._diff_project_files(str(project_dir), before)

    assert str(created.resolve()) in created_files
    assert str(existing.resolve()) in modified_files


def test_diff_project_files_ignores_runtime_and_diagnostic_noise(tmp_path):
    project_dir = tmp_path / "demo"
    project_dir.mkdir()
    before = AgentSession._snapshot_project_files(str(project_dir))

    keep = project_dir / "backend" / "app.py"
    keep.parent.mkdir()
    keep.write_text("print('ok')\n", encoding="utf-8")

    noisy_files = [
        project_dir / ".venv" / "lib" / "python3.14" / "site-packages" / "pkg.py",
        project_dir / ".pytest_cache" / "v" / "cache" / "nodeids",
        project_dir / "backend" / "__pycache__" / "app.cpython-314.pyc",
        project_dir / "backend" / "uploads" / "receipt.png",
        project_dir / "backend" / "instance" / "expenses.db",
        project_dir / "_install_deps.py",
        project_dir / "check_env.py",
        project_dir / "run_check_imports.py",
    ]
    for path in noisy_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("noise", encoding="utf-8")

    created_files, modified_files = AgentSession._diff_project_files(str(project_dir), before)

    assert str(keep.resolve()) in created_files
    assert modified_files == []
    for path in noisy_files:
        assert str(path.resolve()) not in created_files


def test_workspace_tool_wrapper_reparses_raw_arguments(tmp_path):
    session = AgentSession(agent_id="deepseek", client=object())
    project_dir = tmp_path / "workspace"
    project_dir.mkdir()

    captured = {}

    def fake_write_file(path: str, content: str):
        captured["path"] = path
        captured["content"] = content
        return "ok"

    wrapped = session._wrap_workspace_tool(fake_write_file, str(project_dir))
    result = wrapped(raw_arguments='{"path":"notes/todo.txt","content":"hello"}')

    assert captured["path"] == str((project_dir / "notes/todo.txt").resolve())
    assert captured["content"] == "hello"
    assert result["metadata"]["requested_path"] == "notes/todo.txt"
    assert result["output"] == "ok"
