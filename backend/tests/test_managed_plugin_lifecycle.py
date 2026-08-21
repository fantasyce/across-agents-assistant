from __future__ import annotations

import importlib
import shutil
import threading
import time

import pytest
from fastapi.testclient import TestClient


def test_filesystem_transaction_restores_runtime_and_wrapper_after_failure(tmp_path):
    lifecycle = importlib.import_module("across_agents_assistant.managed_plugin_lifecycle")
    plugin_dir = tmp_path / "across" / "plugins" / "across-context"
    wrapper = tmp_path / "across" / "bin" / "across-context"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="post-install probe failed"):
        with lifecycle.ManagedPluginFilesystemTransaction(
            plugin_id="across-context",
            plugin_dir=plugin_dir,
            wrapper_path=wrapper,
            transaction_root=tmp_path / "transactions",
        ):
            shutil.rmtree(plugin_dir)
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "runtime.txt").write_text("version-b\n", encoding="utf-8")
            wrapper.write_text("wrapper-b\n", encoding="utf-8")
            raise RuntimeError("post-install probe failed")

    assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-a\n"
    assert wrapper.read_text(encoding="utf-8") == "wrapper-a\n"


def test_filesystem_transaction_preserves_snapshot_when_restore_fails(tmp_path, monkeypatch):
    lifecycle = importlib.import_module("across_agents_assistant.managed_plugin_lifecycle")
    plugin_dir = tmp_path / "across" / "plugins" / "across-context"
    wrapper = tmp_path / "across" / "bin" / "across-context"
    transaction_root = tmp_path / "transactions"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")

    def failed_replace(source, destination):
        raise OSError(f"cannot restore {destination}")

    monkeypatch.setattr(lifecycle.os, "replace", failed_replace)

    with pytest.raises(lifecycle.ManagedPluginLifecycleRecoveryError):
        with lifecycle.ManagedPluginFilesystemTransaction(
            plugin_id="across-context",
            plugin_dir=plugin_dir,
            wrapper_path=wrapper,
            transaction_root=transaction_root,
        ):
            shutil.rmtree(plugin_dir)
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "runtime.txt").write_text("version-b\n", encoding="utf-8")
            wrapper.write_text("wrapper-b\n", encoding="utf-8")
            raise RuntimeError("post-install probe failed")

    workspaces = list(transaction_root.iterdir())
    assert len(workspaces) == 1
    assert (workspaces[0] / "plugin" / "runtime.txt").read_text(encoding="utf-8") == "version-a\n"
    assert (workspaces[0] / "wrapper").read_text(encoding="utf-8") == "wrapper-a\n"


def test_filesystem_transaction_cleans_workspace_when_snapshot_copy_fails(tmp_path, monkeypatch):
    lifecycle = importlib.import_module("across_agents_assistant.managed_plugin_lifecycle")
    plugin_dir = tmp_path / "across" / "plugins" / "across-context"
    wrapper = tmp_path / "across" / "bin" / "across-context"
    transaction_root = tmp_path / "transactions"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")

    monkeypatch.setattr(
        lifecycle.shutil,
        "copytree",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("snapshot copy failed")),
    )

    with pytest.raises(OSError, match="snapshot copy failed"):
        with lifecycle.ManagedPluginFilesystemTransaction(
            plugin_id="across-context",
            plugin_dir=plugin_dir,
            wrapper_path=wrapper,
            transaction_root=transaction_root,
        ):
            raise AssertionError("transaction must not start")

    assert list(transaction_root.iterdir()) == []


def test_filesystem_transaction_reports_and_retains_failed_commit_cleanup(tmp_path, monkeypatch):
    lifecycle = importlib.import_module("across_agents_assistant.managed_plugin_lifecycle")
    plugin_dir = tmp_path / "across" / "plugins" / "across-context"
    wrapper = tmp_path / "across" / "bin" / "across-context"
    transaction_root = tmp_path / "transactions"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    transaction = lifecycle.ManagedPluginFilesystemTransaction(
        plugin_id="across-context",
        plugin_dir=plugin_dir,
        wrapper_path=wrapper,
        transaction_root=transaction_root,
    )
    original_rmtree = lifecycle.shutil.rmtree

    def fail_workspace_cleanup(path, *args, **kwargs):
        if transaction._workspace is not None and path == transaction._workspace:
            raise OSError("workspace is busy")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(lifecycle.shutil, "rmtree", fail_workspace_cleanup)

    with pytest.raises(lifecycle.ManagedPluginLifecycleCleanupError, match="snapshot retained"):
        with transaction:
            pass

    assert transaction._workspace is not None
    assert transaction._workspace.is_dir()


def test_filesystem_transaction_preserves_lifecycle_error_when_rollback_cleanup_fails(
    tmp_path,
    monkeypatch,
    caplog,
):
    lifecycle = importlib.import_module("across_agents_assistant.managed_plugin_lifecycle")
    plugin_dir = tmp_path / "across" / "plugins" / "across-context"
    wrapper = tmp_path / "across" / "bin" / "across-context"
    transaction_root = tmp_path / "transactions"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    transaction = lifecycle.ManagedPluginFilesystemTransaction(
        plugin_id="across-context",
        plugin_dir=plugin_dir,
        wrapper_path=wrapper,
        transaction_root=transaction_root,
    )
    original_rmtree = lifecycle.shutil.rmtree

    def fail_workspace_cleanup(path, *args, **kwargs):
        if transaction._workspace is not None and path == transaction._workspace:
            raise OSError("workspace is busy")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(lifecycle.shutil, "rmtree", fail_workspace_cleanup)

    with pytest.raises(RuntimeError, match="post-install probe failed"):
        with transaction:
            (plugin_dir / "runtime.txt").write_text("version-b\n", encoding="utf-8")
            raise RuntimeError("post-install probe failed")

    assert "snapshot retained" in caplog.text
    assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-a\n"
    assert transaction._workspace is not None
    assert transaction._workspace.is_dir()


@pytest.mark.parametrize("symlink_root", ["plugin", "wrapper"])
def test_filesystem_transaction_rejects_symlinked_runtime_roots(tmp_path, symlink_root):
    lifecycle = importlib.import_module("across_agents_assistant.managed_plugin_lifecycle")
    plugin_dir = tmp_path / "across" / "plugins" / "across-context"
    wrapper = tmp_path / "across" / "bin" / "across-context"
    external_plugin = tmp_path / "external-plugin"
    external_wrapper = tmp_path / "external-wrapper"
    external_plugin.mkdir()
    external_wrapper.write_text("external-wrapper\n", encoding="utf-8")
    wrapper.parent.mkdir(parents=True)
    plugin_dir.parent.mkdir(parents=True)
    if symlink_root == "plugin":
        plugin_dir.symlink_to(external_plugin, target_is_directory=True)
        wrapper.write_text("wrapper-a\n", encoding="utf-8")
    else:
        plugin_dir.mkdir()
        (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
        wrapper.symlink_to(external_wrapper)

    with pytest.raises(ValueError, match="symbolic link"):
        with lifecycle.ManagedPluginFilesystemTransaction(
            plugin_id="across-context",
            plugin_dir=plugin_dir,
            wrapper_path=wrapper,
            transaction_root=tmp_path / "transactions",
        ):
            raise AssertionError("transaction must not start")

    assert external_wrapper.read_text(encoding="utf-8") == "external-wrapper\n"
    assert external_plugin.is_dir()


def test_context_cli_waits_for_its_lifecycle_guard(tmp_path):
    plugin_runtime = importlib.import_module("across_agents_assistant.plugin_runtime")
    across_home = tmp_path / "across"
    marker = tmp_path / "context-entered.txt"
    command = across_home / "bin" / "across-context"
    command.parent.mkdir(parents=True)
    command.write_text(
        "#!/bin/sh\n"
        f"printf entered > {marker}\n"
        "printf '{}\\n'\n",
        encoding="utf-8",
    )
    command.chmod(0o755)
    started = threading.Event()
    errors: list[BaseException] = []

    def run_context() -> None:
        started.set()
        try:
            plugin_runtime._run_context_cli_json(
                ["plugin-status", "--json"],
                env={"ACROSS_HOME": str(across_home), "PATH": ""},
            )
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    with plugin_runtime.managed_plugin_runtime_guard("across-context"):
        thread = threading.Thread(target=run_context)
        thread.start()
        assert started.wait(timeout=1.0)
        time.sleep(0.1)
        assert not marker.exists()

    thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert errors == []
    assert marker.read_text(encoding="utf-8") == "entered"


@pytest.mark.parametrize(
    ("plugin_id", "run_action"),
    [
        ("across-context", "run_context_plugin_lifecycle_action"),
        ("across-autopilot", "run_autopilot_plugin_lifecycle_action"),
    ],
)
def test_node_plugin_lifecycle_waits_for_active_consumer_guard(
    tmp_path,
    plugin_id,
    run_action,
):
    plugin_runtime = importlib.import_module("across_agents_assistant.plugin_runtime")
    across_home = tmp_path / plugin_id
    plugin_dir = across_home / "plugins" / plugin_id
    wrapper = across_home / "bin" / plugin_id
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("installed\n", encoding="utf-8")
    wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
    wrapper.chmod(0o755)
    started = threading.Event()
    errors: list[BaseException] = []

    def uninstall() -> None:
        started.set()
        try:
            getattr(plugin_runtime, run_action)(
                "uninstall",
                env={"ACROSS_HOME": str(across_home), "PATH": ""},
            )
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    with plugin_runtime.managed_plugin_runtime_guard(plugin_id):
        thread = threading.Thread(target=uninstall)
        thread.start()
        assert started.wait(timeout=1.0)
        time.sleep(0.1)
        assert plugin_dir.exists()

    thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert errors == []
    assert not plugin_dir.exists()
    assert not wrapper.exists()


def test_context_api_restores_runtime_when_repair_fails_after_mutation(tmp_path, monkeypatch):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-context"
    wrapper = across_home / "bin" / "across-context"
    data_file = across_home / "data" / "across-context" / "memory.json"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    data_file.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    data_file.write_text("governed-memory\n", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))

    def failed_repair(action: str):
        assert action == "repair"
        shutil.rmtree(plugin_dir)
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "runtime.txt").write_text("version-b\n", encoding="utf-8")
        wrapper.write_text("wrapper-b\n", encoding="utf-8")
        raise api_server.PluginLifecycleError("post-install probe failed")

    monkeypatch.setattr(api_server, "run_context_plugin_lifecycle_action", failed_repair)

    response = TestClient(api_server.app).post(
        "/api/plugins/across-context/actions",
        json={"action": "repair"},
    )

    assert response.status_code == 500
    assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-a\n"
    assert wrapper.read_text(encoding="utf-8") == "wrapper-a\n"
    assert data_file.read_text(encoding="utf-8") == "governed-memory\n"


def test_context_api_rejects_uninstall_that_leaves_dangling_runtime_symlink(
    tmp_path,
    monkeypatch,
):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-context"
    wrapper = across_home / "bin" / "across-context"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))

    def incomplete_uninstall(action: str):
        assert action == "uninstall"
        shutil.rmtree(plugin_dir)
        wrapper.unlink()
        plugin_dir.symlink_to(tmp_path / "missing-plugin", target_is_directory=True)
        return {"plugin_id": "across-context", "status": "not_installed", "removed": True}

    monkeypatch.setattr(api_server, "run_context_plugin_lifecycle_action", incomplete_uninstall)

    response = TestClient(api_server.app).post(
        "/api/plugins/across-context/actions",
        json={"action": "uninstall"},
    )

    assert response.status_code == 500
    assert not plugin_dir.is_symlink()
    assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-a\n"
    assert wrapper.read_text(encoding="utf-8") == "wrapper-a\n"


def test_context_probe_is_read_only_and_does_not_create_transaction_cache(tmp_path, monkeypatch):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    monkeypatch.setenv("ACROSS_HOME", str(across_home))
    monkeypatch.setattr(
        api_server,
        "run_context_plugin_lifecycle_action",
        lambda action: {
            "plugin_id": "across-context",
            "status": "not_installed",
            "installed": False,
            "available": False,
            "integrity_ok": True,
            "probe": True,
        },
    )

    response = TestClient(api_server.app).post(
        "/api/plugins/across-context/actions",
        json={"action": "probe"},
    )

    assert response.status_code == 200
    assert not (across_home / "cache" / "across-agents-assistant").exists()


def test_context_api_rejects_unavailable_repair_and_restores_old_runtime(tmp_path, monkeypatch):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-context"
    wrapper = across_home / "bin" / "across-context"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))

    def unavailable_repair(action: str):
        assert action == "repair"
        shutil.rmtree(plugin_dir)
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "runtime.txt").write_text("version-b\n", encoding="utf-8")
        wrapper.write_text("wrapper-b\n", encoding="utf-8")
        return {
            "plugin_id": "across-context",
            "status": "needs_repair",
            "installed": True,
            "available": False,
            "integrity_ok": False,
            "probe": True,
        }

    monkeypatch.setattr(api_server, "run_context_plugin_lifecycle_action", unavailable_repair)

    response = TestClient(api_server.app).post(
        "/api/plugins/across-context/actions",
        json={"action": "repair"},
    )

    assert response.status_code == 500
    assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-a\n"
    assert wrapper.read_text(encoding="utf-8") == "wrapper-a\n"


def test_context_api_rolls_back_when_governed_memory_probe_is_invalid(tmp_path, monkeypatch):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-context"
    wrapper = across_home / "bin" / "across-context"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))

    def repair(action: str):
        assert action == "repair"
        shutil.rmtree(plugin_dir)
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "runtime.txt").write_text("version-b\n", encoding="utf-8")
        wrapper.write_text("wrapper-b\n", encoding="utf-8")
        return {
            "plugin_id": "across-context",
            "status": "installed",
            "installed": True,
            "available": True,
            "integrity_ok": True,
            "probe": True,
        }

    def failed_memory_probe(**_kwargs):
        assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-b\n"
        return {}

    monkeypatch.setattr(api_server, "run_context_plugin_lifecycle_action", repair)
    monkeypatch.setattr(api_server, "get_agent_loop_memory_metrics", failed_memory_probe)

    response = TestClient(api_server.app).post(
        "/api/plugins/across-context/actions",
        json={"action": "repair"},
    )

    assert response.status_code == 500
    assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-a\n"
    assert wrapper.read_text(encoding="utf-8") == "wrapper-a\n"


def test_autopilot_api_quiesces_and_restores_running_scheduler_for_upgrade(tmp_path, monkeypatch):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-autopilot"
    wrapper = across_home / "bin" / "across-autopilot"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))
    calls: list[object] = []

    class FakeScheduler:
        def status(self):
            calls.append("scheduler-status")
            return {
                "running": True,
                "interval_seconds": 17.0,
                "run_queued_triggers": False,
                "max_runs_per_tick": 3,
                "tick_in_progress": False,
            }

        def stop(self):
            calls.append("scheduler-stop")
            return {"running": False, "tick_in_progress": False}

        def start(self, **kwargs):
            calls.append(("scheduler-start", kwargs))
            return {"running": True, **kwargs}

    def upgrade(action: str):
        calls.append("mutate")
        assert action == "upgrade"
        assert calls[-2] == "scheduler-stop"
        shutil.rmtree(plugin_dir)
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "runtime.txt").write_text("version-b\n", encoding="utf-8")
        wrapper.write_text("wrapper-b\n", encoding="utf-8")
        return {
            "plugin_id": "across-autopilot",
            "status": "installed",
            "installed": True,
            "available": True,
            "integrity_ok": True,
            "probe": True,
        }

    monkeypatch.setattr(api_server, "get_autopilot_trigger_scheduler", lambda: FakeScheduler())
    monkeypatch.setattr(api_server, "run_autopilot_plugin_lifecycle_action", upgrade)

    response = TestClient(api_server.app).post(
        "/api/plugins/across-autopilot/actions",
        json={"action": "upgrade"},
    )

    assert response.status_code == 200
    assert calls == [
        "scheduler-status",
        "scheduler-stop",
        "mutate",
        (
            "scheduler-start",
            {
                "interval_seconds": 17.0,
                "run_queued_triggers": False,
                "max_runs_per_tick": 3,
            },
        ),
    ]
    assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-b\n"


def test_autopilot_api_recovers_runtime_before_restarting_scheduler_on_failure(tmp_path, monkeypatch):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-autopilot"
    wrapper = across_home / "bin" / "across-autopilot"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))
    calls: list[str] = []

    class FakeScheduler:
        def status(self):
            calls.append("scheduler-status")
            return {
                "running": True,
                "interval_seconds": 11.0,
                "run_queued_triggers": True,
                "max_runs_per_tick": 2,
                "tick_in_progress": False,
            }

        def stop(self):
            calls.append("scheduler-stop")
            return {"running": False, "tick_in_progress": False}

        def start(self, **_kwargs):
            assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-a\n"
            assert wrapper.read_text(encoding="utf-8") == "wrapper-a\n"
            calls.append("scheduler-start")
            return {"running": True}

    def failed_upgrade(action: str):
        assert action == "upgrade"
        calls.append("mutate")
        shutil.rmtree(plugin_dir)
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "runtime.txt").write_text("version-b\n", encoding="utf-8")
        wrapper.write_text("wrapper-b\n", encoding="utf-8")
        raise api_server.PluginLifecycleError("post-install probe failed")

    scheduler = FakeScheduler()
    monkeypatch.setattr(api_server, "get_autopilot_trigger_scheduler", lambda: scheduler)
    monkeypatch.setattr(api_server, "run_autopilot_plugin_lifecycle_action", failed_upgrade)

    response = TestClient(api_server.app).post(
        "/api/plugins/across-autopilot/actions",
        json={"action": "upgrade"},
    )

    assert response.status_code == 500
    assert calls == ["scheduler-status", "scheduler-stop", "mutate", "scheduler-start"]
    assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-a\n"


def test_autopilot_api_restores_running_scheduler_when_stop_does_not_quiesce(
    tmp_path,
    monkeypatch,
):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-autopilot"
    wrapper = across_home / "bin" / "across-autopilot"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))
    calls: list[str] = []

    class FakeScheduler:
        def status(self):
            calls.append("scheduler-status")
            return {
                "running": True,
                "interval_seconds": 12.0,
                "run_queued_triggers": True,
                "max_runs_per_tick": 1,
            }

        def stop(self):
            calls.append("scheduler-stop")
            return {"running": False, "tick_in_progress": True}

        def start(self, **_kwargs):
            calls.append("scheduler-start")
            return {"running": True}

    monkeypatch.setattr(api_server, "get_autopilot_trigger_scheduler", lambda: FakeScheduler())

    response = TestClient(api_server.app).post(
        "/api/plugins/across-autopilot/actions",
        json={"action": "upgrade"},
    )

    assert response.status_code == 500
    assert calls == ["scheduler-status", "scheduler-stop", "scheduler-start"]


def test_autopilot_api_serializes_scheduler_quiesce_across_lifecycle_actions(
    tmp_path,
    monkeypatch,
):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-autopilot"
    wrapper = across_home / "bin" / "across-autopilot"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))
    first_mutation_started = threading.Event()
    release_first_mutation = threading.Event()
    second_status_called = threading.Event()
    status_count = 0
    mutation_count = 0
    counter_lock = threading.Lock()

    class FakeScheduler:
        def status(self):
            nonlocal status_count
            with counter_lock:
                status_count += 1
                if status_count == 2:
                    second_status_called.set()
            return {"running": False}

    def upgrade(action: str):
        nonlocal mutation_count
        assert action == "upgrade"
        with counter_lock:
            mutation_count += 1
            current = mutation_count
        if current == 1:
            first_mutation_started.set()
            assert release_first_mutation.wait(timeout=2.0)
        return {
            "plugin_id": "across-autopilot",
            "status": "installed",
            "installed": True,
            "available": True,
            "integrity_ok": True,
            "probe": True,
        }

    scheduler = FakeScheduler()
    monkeypatch.setattr(api_server, "get_autopilot_trigger_scheduler", lambda: scheduler)
    monkeypatch.setattr(api_server, "run_autopilot_plugin_lifecycle_action", upgrade)
    responses: list[int] = []

    def request_upgrade():
        response = TestClient(api_server.app).post(
            "/api/plugins/across-autopilot/actions",
            json={"action": "upgrade"},
        )
        responses.append(response.status_code)

    first = threading.Thread(target=request_upgrade)
    second = threading.Thread(target=request_upgrade)
    first.start()
    assert first_mutation_started.wait(timeout=2.0)
    second.start()
    time.sleep(0.1)
    assert not second_status_called.is_set()
    release_first_mutation.set()
    first.join(timeout=2.0)
    second.join(timeout=2.0)

    assert not first.is_alive()
    assert not second.is_alive()
    assert sorted(responses) == [200, 200]
    assert status_count == 2


def test_autopilot_api_rejects_incomplete_uninstall_and_recovers_scheduler(tmp_path, monkeypatch):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-autopilot"
    wrapper = across_home / "bin" / "across-autopilot"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))
    calls: list[str] = []

    class FakeScheduler:
        def status(self):
            calls.append("scheduler-status")
            return {
                "running": True,
                "interval_seconds": 13.0,
                "run_queued_triggers": True,
                "max_runs_per_tick": 1,
                "tick_in_progress": False,
            }

        def stop(self):
            calls.append("scheduler-stop")
            return {"running": False, "tick_in_progress": False}

        def start(self, **_kwargs):
            calls.append("scheduler-start")
            return {"running": True}

    def incomplete_uninstall(action: str):
        assert action == "uninstall"
        calls.append("mutate")
        return {
            "plugin_id": "across-autopilot",
            "status": "not_installed",
            "removed": True,
        }

    scheduler = FakeScheduler()
    monkeypatch.setattr(api_server, "get_autopilot_trigger_scheduler", lambda: scheduler)
    monkeypatch.setattr(api_server, "run_autopilot_plugin_lifecycle_action", incomplete_uninstall)

    response = TestClient(api_server.app).post(
        "/api/plugins/across-autopilot/actions",
        json={"action": "uninstall"},
    )

    assert response.status_code == 500
    assert calls == ["scheduler-status", "scheduler-stop", "mutate", "scheduler-start"]
    assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-a\n"
    assert wrapper.read_text(encoding="utf-8") == "wrapper-a\n"


def test_autopilot_api_rolls_back_when_scheduler_does_not_restart(tmp_path, monkeypatch):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-autopilot"
    wrapper = across_home / "bin" / "across-autopilot"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))

    class FakeScheduler:
        def status(self):
            return {
                "running": True,
                "interval_seconds": 10.0,
                "run_queued_triggers": True,
                "max_runs_per_tick": 1,
                "tick_in_progress": False,
            }

        def stop(self):
            return {"running": False, "tick_in_progress": False}

        def start(self, **_kwargs):
            return {"running": False}

    def upgrade(action: str):
        assert action == "upgrade"
        shutil.rmtree(plugin_dir)
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "runtime.txt").write_text("version-b\n", encoding="utf-8")
        wrapper.write_text("wrapper-b\n", encoding="utf-8")
        return {
            "plugin_id": "across-autopilot",
            "status": "installed",
            "installed": True,
            "available": True,
            "integrity_ok": True,
            "probe": True,
        }

    scheduler = FakeScheduler()
    monkeypatch.setattr(api_server, "get_autopilot_trigger_scheduler", lambda: scheduler)
    monkeypatch.setattr(api_server, "run_autopilot_plugin_lifecycle_action", upgrade)

    response = TestClient(api_server.app).post(
        "/api/plugins/across-autopilot/actions",
        json={"action": "upgrade"},
    )

    assert response.status_code == 500
    assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-a\n"
    assert wrapper.read_text(encoding="utf-8") == "wrapper-a\n"


def test_autopilot_scheduler_recovery_rejects_non_running_result():
    api_server = importlib.import_module("across_agents_assistant.api_server")

    with pytest.raises(api_server.PluginLifecycleError, match="did not recover"):
        api_server._require_autopilot_scheduler_running(
            {"running": False},
            operation="recover",
        )


def test_autopilot_successful_uninstall_preserves_data_and_keeps_scheduler_stopped(
    tmp_path,
    monkeypatch,
):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-autopilot"
    wrapper = across_home / "bin" / "across-autopilot"
    data_file = across_home / "data" / "across-autopilot" / "runs.json"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    data_file.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    data_file.write_text("preserved\n", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))
    calls: list[str] = []

    class FakeScheduler:
        def status(self):
            calls.append("scheduler-status")
            return {
                "running": True,
                "interval_seconds": 10.0,
                "run_queued_triggers": True,
                "max_runs_per_tick": 1,
                "tick_in_progress": False,
            }

        def stop(self):
            calls.append("scheduler-stop")
            return {"running": False, "tick_in_progress": False}

        def start(self, **_kwargs):  # pragma: no cover - a call fails the test
            raise AssertionError("scheduler must remain stopped after uninstall")

    def uninstall(action: str):
        assert action == "uninstall"
        calls.append("uninstall")
        shutil.rmtree(plugin_dir)
        wrapper.unlink()
        return {
            "plugin_id": "across-autopilot",
            "status": "not_installed",
            "removed": True,
        }

    scheduler = FakeScheduler()
    monkeypatch.setattr(api_server, "get_autopilot_trigger_scheduler", lambda: scheduler)
    monkeypatch.setattr(api_server, "run_autopilot_plugin_lifecycle_action", uninstall)

    response = TestClient(api_server.app).post(
        "/api/plugins/across-autopilot/actions",
        json={"action": "uninstall"},
    )

    assert response.status_code == 200
    assert calls == ["scheduler-status", "scheduler-stop", "uninstall"]
    assert data_file.read_text(encoding="utf-8") == "preserved\n"


def test_orchestrator_api_probes_runtime_before_reconnecting_worker(tmp_path, monkeypatch):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-orchestrator"
    wrapper = across_home / "bin" / "across-orchestrator"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))
    calls: list[str] = []

    class FakeManager:
        def reset_runtime_connection(self):
            calls.append("manager-reset")

        def install_plugin(self):
            calls.append("install")
            shutil.rmtree(plugin_dir)
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "runtime.txt").write_text("version-b\n", encoding="utf-8")
            wrapper.write_text("wrapper-b\n", encoding="utf-8")
            return {"status": "installed", "installed": True, "integrity_ok": True}

        def implementation_status(self, probe: bool = True):
            assert probe is True
            calls.append("runtime-probe")
            return {
                "implementation": "external",
                "available": True,
                "install": {"installed": True, "integrity_ok": True},
            }

    class FakeWorkerRuntime:
        def shutdown(self):
            calls.append("worker-shutdown")

        def reconcile(self):
            calls.append("worker-reconcile")
            return {"status": "running", "listener_pid": 42}

    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakeManager())
    monkeypatch.setattr(api_server, "get_worker_network_runtime", lambda: FakeWorkerRuntime())

    response = TestClient(api_server.app).post(
        "/api/plugins/across-orchestrator/actions",
        json={"action": "repair"},
    )

    assert response.status_code == 200
    assert calls == [
        "worker-shutdown",
        "manager-reset",
        "install",
        "runtime-probe",
        "worker-reconcile",
    ]
    assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-b\n"


def test_orchestrator_quiesce_reset_failure_recovers_existing_consumers(tmp_path, monkeypatch):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-orchestrator"
    wrapper = across_home / "bin" / "across-orchestrator"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))
    calls: list[str] = []

    class FakeManager:
        def __init__(self):
            self.reset_count = 0

        def reset_runtime_connection(self):
            self.reset_count += 1
            calls.append(f"manager-reset-{self.reset_count}")
            if self.reset_count == 1:
                raise RuntimeError("sidecar reset failed")

        def implementation_status(self, probe: bool = True):
            assert probe is True
            calls.append("runtime-probe-recovered")
            return {"available": True, "install": {"installed": True, "integrity_ok": True}}

    class FakeWorkerRuntime:
        def shutdown(self):
            calls.append("worker-shutdown")

        def reconcile(self):
            calls.append("worker-reconcile-recovered")
            return {"status": "running", "last_error": None}

    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakeManager())
    monkeypatch.setattr(api_server, "get_worker_network_runtime", lambda: FakeWorkerRuntime())

    response = TestClient(api_server.app).post(
        "/api/plugins/across-orchestrator/actions",
        json={"action": "upgrade"},
    )

    assert response.status_code == 500
    assert calls == [
        "worker-shutdown",
        "manager-reset-1",
        "manager-reset-2",
        "runtime-probe-recovered",
        "worker-reconcile-recovered",
    ]
    assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-a\n"


def test_orchestrator_observes_preexisting_runtime_inside_lifecycle_guard(tmp_path, monkeypatch):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    plugin_runtime = importlib.import_module("across_agents_assistant.plugin_runtime")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-orchestrator"
    wrapper = across_home / "bin" / "across-orchestrator"
    monkeypatch.setenv("ACROSS_HOME", str(across_home))
    worker_fetched = threading.Event()
    recovery_probe = threading.Event()

    class FakeManager:
        def reset_runtime_connection(self):
            return None

        def install_plugin(self):
            shutil.rmtree(plugin_dir)
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "runtime.txt").write_text("version-b\n", encoding="utf-8")
            wrapper.write_text("wrapper-b\n", encoding="utf-8")
            return {"status": "installed", "installed": True, "integrity_ok": True}

        def implementation_status(self, probe: bool = True):
            assert probe is True
            if (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-a\n":
                recovery_probe.set()
            return {
                "available": True,
                "install": {"installed": True, "integrity_ok": True},
            }

    class FakeWorkerRuntime:
        def __init__(self):
            self.reconcile_count = 0

        def shutdown(self):
            return None

        def reconcile(self):
            self.reconcile_count += 1
            if self.reconcile_count == 1:
                raise RuntimeError("worker reconnect failed")
            return {"status": "running", "last_error": None}

    manager = FakeManager()
    worker = FakeWorkerRuntime()
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: manager)

    def get_worker():
        worker_fetched.set()
        return worker

    monkeypatch.setattr(api_server, "get_worker_network_runtime", get_worker)
    responses: list[int] = []

    def request_upgrade():
        response = TestClient(api_server.app).post(
            "/api/plugins/across-orchestrator/actions",
            json={"action": "upgrade"},
        )
        responses.append(response.status_code)

    with plugin_runtime.managed_plugin_lifecycle_guard("across-orchestrator"):
        thread = threading.Thread(target=request_upgrade)
        thread.start()
        assert worker_fetched.wait(timeout=1.0)
        plugin_dir.mkdir(parents=True)
        wrapper.parent.mkdir(parents=True)
        (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
        wrapper.write_text("wrapper-a\n", encoding="utf-8")

    thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert responses == [500]
    assert recovery_probe.is_set()
    assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-a\n"


def test_orchestrator_manager_reset_clears_cached_runtime_connection(tmp_path):
    orchestrator_plugin = importlib.import_module("across_agents_assistant.orchestrator_plugin")
    manager = orchestrator_plugin.OrchestratorPluginManager(
        orchestrator_plugin.OrchestratorPluginConfig(
            mode="external",
            command=str(tmp_path / "missing-orchestrator"),
            registry_path=tmp_path / "tasks.json",
            plugin_home=tmp_path / "plugins",
        )
    )
    manager._transport = "http"
    manager._endpoint = "http://127.0.0.1:9999"
    manager._sidecar_retry_after = 123.0

    manager.reset_runtime_connection()

    assert manager._transport is None
    assert manager._endpoint is None
    assert manager._sidecar_retry_after == 0.0


def test_orchestrator_runtime_probe_waits_for_managed_runtime_guard(tmp_path, monkeypatch):
    orchestrator_plugin = importlib.import_module("across_agents_assistant.orchestrator_plugin")
    plugin_runtime = importlib.import_module("across_agents_assistant.plugin_runtime")
    command = tmp_path / "across-orchestrator"
    command.write_text("#!/bin/sh\n", encoding="utf-8")
    command.chmod(0o755)
    manager = orchestrator_plugin.OrchestratorPluginManager(
        orchestrator_plugin.OrchestratorPluginConfig(
            mode="external",
            command=str(command),
            registry_path=tmp_path / "tasks.json",
            plugin_home=tmp_path / "plugins",
        )
    )
    probe_started = threading.Event()
    sidecar_entered = threading.Event()
    results: list[dict] = []

    def ensure_sidecar(_command_path: str):
        sidecar_entered.set()
        return "http://127.0.0.1:9999"

    monkeypatch.setattr(manager, "_ensure_sidecar", ensure_sidecar)
    monkeypatch.setattr(manager, "_http_get", lambda _path: {})

    def probe_runtime():
        probe_started.set()
        results.append(manager.implementation_status(probe=True))

    with plugin_runtime.managed_plugin_runtime_guard("across-orchestrator"):
        thread = threading.Thread(target=probe_runtime)
        thread.start()
        assert probe_started.wait(timeout=1.0)
        time.sleep(0.1)
        assert not sidecar_entered.is_set()

    thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert sidecar_entered.is_set()
    assert results[0]["available"] is True


def test_orchestrator_runtime_reset_waits_for_inflight_cli_call(tmp_path, monkeypatch):
    orchestrator_plugin = importlib.import_module("across_agents_assistant.orchestrator_plugin")
    command = tmp_path / "across-orchestrator"
    command.write_text("#!/bin/sh\n", encoding="utf-8")
    command.chmod(0o755)
    manager = orchestrator_plugin.OrchestratorPluginManager(
        orchestrator_plugin.OrchestratorPluginConfig(
            mode="external",
            command=str(command),
            registry_path=tmp_path / "tasks.json",
            plugin_home=tmp_path / "plugins",
        )
    )
    cli_entered = threading.Event()
    release_cli = threading.Event()
    reset_done = threading.Event()

    class Completed:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def blocked_run(*_args, **_kwargs):
        cli_entered.set()
        assert release_cli.wait(timeout=2.0)
        return Completed()

    monkeypatch.setattr(orchestrator_plugin.subprocess, "run", blocked_run)
    cli_thread = threading.Thread(target=lambda: manager._cli_json(["status", "--json"]))
    reset_thread = threading.Thread(
        target=lambda: (manager.reset_runtime_connection(), reset_done.set())
    )
    cli_thread.start()
    assert cli_entered.wait(timeout=1.0)
    reset_thread.start()
    time.sleep(0.1)
    assert not reset_done.is_set()
    release_cli.set()
    cli_thread.join(timeout=2.0)
    reset_thread.join(timeout=2.0)

    assert not cli_thread.is_alive()
    assert not reset_thread.is_alive()
    assert reset_done.is_set()


def test_orchestrator_public_operation_blocks_lifecycle_between_probe_and_dispatch(
    tmp_path,
    monkeypatch,
):
    orchestrator_plugin = importlib.import_module("across_agents_assistant.orchestrator_plugin")
    plugin_runtime = importlib.import_module("across_agents_assistant.plugin_runtime")
    manager = orchestrator_plugin.OrchestratorPluginManager(
        orchestrator_plugin.OrchestratorPluginConfig(
            mode="external",
            endpoint="http://old-runtime.test",
            command=str(tmp_path / "missing-orchestrator"),
            registry_path=tmp_path / "tasks.json",
            plugin_home=tmp_path / "plugins",
            auto_run=False,
        )
    )
    probe_completed = threading.Event()
    lifecycle_attempted = threading.Event()
    lifecycle_completed = threading.Event()
    dispatch_completed = threading.Event()
    dispatched_endpoints: list[str | None] = []
    operation_results: list[dict] = []
    operation_errors: list[BaseException] = []

    def deterministic_ensure_external():
        manager._transport = "http"
        manager._endpoint = "http://old-runtime.test"
        probe_completed.set()
        assert lifecycle_attempted.wait(timeout=1.0)
        lifecycle_completed.wait(timeout=0.25)

    def lifecycle_reset():
        assert probe_completed.wait(timeout=1.0)
        lifecycle_attempted.set()
        with plugin_runtime.managed_plugin_lifecycle_guard("across-orchestrator"):
            with plugin_runtime.managed_plugin_runtime_guard("across-orchestrator"):
                manager._transport = "cli"
                manager._endpoint = "http://new-runtime.test"
                lifecycle_completed.set()

    def dispatch_http(_path, _payload):
        dispatched_endpoints.append(manager._endpoint)
        assert not lifecycle_completed.is_set()
        dispatch_completed.set()
        return {"task_id": "task-1", "status": "cancelled"}

    def dispatch_cli(_args):
        raise AssertionError("lifecycle reset interleaved before public operation dispatch")

    def run_operation():
        try:
            operation_results.append(manager.cancel_task("task-1"))
        except BaseException as exc:
            operation_errors.append(exc)

    monkeypatch.setattr(manager, "_ensure_external", deterministic_ensure_external)
    monkeypatch.setattr(manager, "_http_post_unlocked", dispatch_http)
    monkeypatch.setattr(manager, "_cli_json_unlocked", dispatch_cli)
    lifecycle_thread = threading.Thread(target=lifecycle_reset)
    operation_thread = threading.Thread(target=run_operation)
    lifecycle_thread.start()
    operation_thread.start()
    operation_thread.join(timeout=2.0)
    lifecycle_thread.join(timeout=2.0)

    assert not operation_thread.is_alive()
    assert not lifecycle_thread.is_alive()
    assert operation_errors == []
    assert operation_results == [{"task_id": "task-1", "status": "cancelled"}]
    assert dispatch_completed.is_set()
    assert dispatched_endpoints == ["http://old-runtime.test"]
    assert lifecycle_completed.is_set()
    assert manager._endpoint == "http://new-runtime.test"


def test_worker_reconcile_holds_orchestrator_runtime_guard(tmp_path, monkeypatch):
    worker_control = importlib.import_module("across_agents_assistant.worker_control")
    plugin_runtime = importlib.import_module("across_agents_assistant.plugin_runtime")
    monkeypatch.setenv("ACROSS_HOME", str(tmp_path / "across"))
    reconcile_entered = threading.Event()
    release_reconcile = threading.Event()
    lifecycle_entered = threading.Event()

    class FakeStore:
        def __init__(self):
            self.snapshot_count = 0

        def snapshot(self):
            self.snapshot_count += 1
            if self.snapshot_count == 1:
                reconcile_entered.set()
                assert release_reconcile.wait(timeout=2.0)
            return {"listener": {"enabled": False}, "relay": {"enabled": False}}

    manager = worker_control.WorkerNetworkRuntimeManager(store=FakeStore())
    reconcile_thread = threading.Thread(target=manager.reconcile)

    def enter_lifecycle_runtime():
        with plugin_runtime.managed_plugin_runtime_guard("across-orchestrator"):
            lifecycle_entered.set()

    lifecycle_thread = threading.Thread(target=enter_lifecycle_runtime)
    reconcile_thread.start()
    assert reconcile_entered.wait(timeout=1.0)
    lifecycle_thread.start()
    time.sleep(0.1)
    assert not lifecycle_entered.is_set()
    release_reconcile.set()
    reconcile_thread.join(timeout=2.0)
    lifecycle_thread.join(timeout=2.0)

    assert not reconcile_thread.is_alive()
    assert not lifecycle_thread.is_alive()
    assert lifecycle_entered.is_set()


def test_worker_orchestrator_call_holds_runtime_guard(tmp_path, monkeypatch):
    worker_control = importlib.import_module("across_agents_assistant.worker_control")
    plugin_runtime = importlib.import_module("across_agents_assistant.plugin_runtime")
    monkeypatch.setenv("ACROSS_HOME", str(tmp_path / "across"))
    call_entered = threading.Event()
    release_call = threading.Event()
    lifecycle_entered = threading.Event()
    client = worker_control.WorkerOrchestratorClient(
        command=[str(tmp_path / "across-orchestrator")],
        socket_path=tmp_path / "missing.sock",
    )

    class Completed:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def blocked_run(*_args, **_kwargs):
        call_entered.set()
        assert release_call.wait(timeout=2.0)
        return Completed()

    monkeypatch.setattr(worker_control.subprocess, "run", blocked_run)
    call_thread = threading.Thread(target=lambda: client.call("status"))

    def enter_lifecycle_runtime():
        with plugin_runtime.managed_plugin_runtime_guard("across-orchestrator"):
            lifecycle_entered.set()

    lifecycle_thread = threading.Thread(target=enter_lifecycle_runtime)
    call_thread.start()
    assert call_entered.wait(timeout=1.0)
    lifecycle_thread.start()
    time.sleep(0.1)
    assert not lifecycle_entered.is_set()
    release_call.set()
    call_thread.join(timeout=2.0)
    lifecycle_thread.join(timeout=2.0)

    assert not call_thread.is_alive()
    assert not lifecycle_thread.is_alive()
    assert lifecycle_entered.is_set()


def test_orchestrator_api_restores_runtime_before_recovering_worker_after_reconnect_failure(
    tmp_path,
    monkeypatch,
):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-orchestrator"
    wrapper = across_home / "bin" / "across-orchestrator"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))
    calls: list[str] = []

    class FakeManager:
        def reset_runtime_connection(self):
            calls.append("manager-reset")

        def install_plugin(self):
            calls.append("install")
            shutil.rmtree(plugin_dir)
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "runtime.txt").write_text("version-b\n", encoding="utf-8")
            wrapper.write_text("wrapper-b\n", encoding="utf-8")
            return {"status": "installed", "installed": True, "integrity_ok": True}

        def implementation_status(self, probe: bool = True):
            assert probe is True
            calls.append("runtime-probe")
            return {
                "implementation": "external",
                "available": True,
                "install": {"installed": True, "integrity_ok": True},
            }

    class FakeWorkerRuntime:
        def __init__(self):
            self.reconcile_count = 0

        def shutdown(self):
            calls.append("worker-shutdown")

        def reconcile(self):
            self.reconcile_count += 1
            if self.reconcile_count == 1:
                assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-b\n"
                calls.append("worker-reconcile-failed")
                raise RuntimeError("worker reconnect failed")
            assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-a\n"
            assert wrapper.read_text(encoding="utf-8") == "wrapper-a\n"
            calls.append("worker-reconcile-recovered")
            return {"status": "running", "listener_pid": 41}

    manager = FakeManager()
    worker = FakeWorkerRuntime()
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: manager)
    monkeypatch.setattr(api_server, "get_worker_network_runtime", lambda: worker)

    response = TestClient(api_server.app).post(
        "/api/plugins/across-orchestrator/actions",
        json={"action": "upgrade"},
    )

    assert response.status_code == 500
    assert calls == [
        "worker-shutdown",
        "manager-reset",
        "install",
        "runtime-probe",
        "worker-reconcile-failed",
        "manager-reset",
        "runtime-probe",
        "worker-reconcile-recovered",
    ]
    assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-a\n"


def test_orchestrator_api_rolls_back_when_worker_reconcile_returns_degraded(tmp_path, monkeypatch):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-orchestrator"
    wrapper = across_home / "bin" / "across-orchestrator"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))

    class FakeManager:
        def reset_runtime_connection(self):
            return None

        def install_plugin(self):
            shutil.rmtree(plugin_dir)
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "runtime.txt").write_text("version-b\n", encoding="utf-8")
            wrapper.write_text("wrapper-b\n", encoding="utf-8")
            return {"status": "installed", "installed": True, "integrity_ok": True}

        def implementation_status(self, probe: bool = True):
            assert probe is True
            return {
                "implementation": "external",
                "available": True,
                "install": {"installed": True, "integrity_ok": True},
            }

    class FakeWorkerRuntime:
        def __init__(self):
            self.reconcile_count = 0

        def shutdown(self):
            return None

        def reconcile(self):
            self.reconcile_count += 1
            if self.reconcile_count == 1:
                return {"status": "degraded", "last_error": "orchestrator_start_failed"}
            return {"status": "running", "last_error": None, "listener_pid": 43}

    worker = FakeWorkerRuntime()
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakeManager())
    monkeypatch.setattr(api_server, "get_worker_network_runtime", lambda: worker)

    response = TestClient(api_server.app).post(
        "/api/plugins/across-orchestrator/actions",
        json={"action": "upgrade"},
    )

    assert response.status_code == 500
    assert worker.reconcile_count == 2
    assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-a\n"
    assert wrapper.read_text(encoding="utf-8") == "wrapper-a\n"


def test_orchestrator_rollback_still_recovers_worker_when_restored_probe_fails(
    tmp_path,
    monkeypatch,
):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-orchestrator"
    wrapper = across_home / "bin" / "across-orchestrator"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))

    class FakeManager:
        def __init__(self):
            self.probe_count = 0

        def reset_runtime_connection(self):
            return None

        def install_plugin(self):
            shutil.rmtree(plugin_dir)
            plugin_dir.mkdir(parents=True)
            (plugin_dir / "runtime.txt").write_text("version-b\n", encoding="utf-8")
            wrapper.write_text("wrapper-b\n", encoding="utf-8")
            return {"status": "installed", "installed": True, "integrity_ok": True}

        def implementation_status(self, probe: bool = True):
            assert probe is True
            self.probe_count += 1
            if self.probe_count == 1:
                return {
                    "available": True,
                    "install": {"installed": True, "integrity_ok": True},
                }
            return {"available": False, "install": {"installed": True, "integrity_ok": True}}

    class FakeWorkerRuntime:
        def __init__(self):
            self.reconcile_count = 0

        def shutdown(self):
            return None

        def reconcile(self):
            self.reconcile_count += 1
            if self.reconcile_count == 1:
                raise RuntimeError("new worker runtime failed")
            return {"status": "running", "last_error": None}

    manager = FakeManager()
    worker = FakeWorkerRuntime()
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: manager)
    monkeypatch.setattr(api_server, "get_worker_network_runtime", lambda: worker)

    response = TestClient(api_server.app).post(
        "/api/plugins/across-orchestrator/actions",
        json={"action": "upgrade"},
    )

    assert response.status_code == 500
    assert manager.probe_count == 2
    assert worker.reconcile_count == 2
    assert (plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-a\n"


def test_orchestrator_api_uses_installer_override_paths_for_rollback(tmp_path, monkeypatch):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    custom_plugin_dir = tmp_path / "custom-plugins" / "across-orchestrator"
    custom_wrapper = tmp_path / "custom-bin" / "across-orchestrator"
    custom_plugin_dir.mkdir(parents=True)
    custom_wrapper.parent.mkdir(parents=True)
    (custom_plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    custom_wrapper.write_text("wrapper-a\n", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))

    class FakeInstaller:
        install_dir = custom_plugin_dir
        wrapper_path = custom_wrapper

    class FakeManager:
        installer = FakeInstaller()

        def reset_runtime_connection(self):
            return None

        def install_plugin(self):
            shutil.rmtree(custom_plugin_dir)
            custom_plugin_dir.mkdir(parents=True)
            (custom_plugin_dir / "runtime.txt").write_text("version-b\n", encoding="utf-8")
            custom_wrapper.write_text("wrapper-b\n", encoding="utf-8")
            return {"status": "installed", "installed": True, "integrity_ok": True}

        def implementation_status(self, probe: bool = True):
            assert probe is True
            return {
                "implementation": "external",
                "available": True,
                "install": {"installed": True, "integrity_ok": True},
            }

    class FakeWorkerRuntime:
        def __init__(self):
            self.reconcile_count = 0

        def shutdown(self):
            return None

        def reconcile(self):
            self.reconcile_count += 1
            if self.reconcile_count == 1:
                raise RuntimeError("worker reconnect failed")
            return {"status": "running", "last_error": None}

    worker = FakeWorkerRuntime()
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakeManager())
    monkeypatch.setattr(api_server, "get_worker_network_runtime", lambda: worker)

    response = TestClient(api_server.app).post(
        "/api/plugins/across-orchestrator/actions",
        json={"action": "upgrade"},
    )

    assert response.status_code == 500
    assert (custom_plugin_dir / "runtime.txt").read_text(encoding="utf-8") == "version-a\n"
    assert custom_wrapper.read_text(encoding="utf-8") == "wrapper-a\n"
    assert not (across_home / "plugins" / "across-orchestrator").exists()


def test_orchestrator_successful_uninstall_preserves_data_and_keeps_consumers_stopped(
    tmp_path,
    monkeypatch,
):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-orchestrator"
    wrapper = across_home / "bin" / "across-orchestrator"
    data_file = across_home / "data" / "across-orchestrator" / "tasks.json"
    plugin_dir.mkdir(parents=True)
    wrapper.parent.mkdir(parents=True)
    data_file.parent.mkdir(parents=True)
    (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
    wrapper.write_text("wrapper-a\n", encoding="utf-8")
    data_file.write_text("preserved\n", encoding="utf-8")
    monkeypatch.setenv("ACROSS_HOME", str(across_home))
    calls: list[str] = []

    class FakeManager:
        def reset_runtime_connection(self):
            calls.append("manager-reset")

        def uninstall_plugin(self):
            calls.append("uninstall")
            shutil.rmtree(plugin_dir)
            wrapper.unlink()
            return {"status": "not_installed", "removed": True}

    class FakeWorkerRuntime:
        def shutdown(self):
            calls.append("worker-shutdown")

        def reconcile(self):  # pragma: no cover - a call fails the test
            raise AssertionError("Worker must remain stopped after uninstall")

    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakeManager())
    monkeypatch.setattr(api_server, "get_worker_network_runtime", lambda: FakeWorkerRuntime())

    response = TestClient(api_server.app).post(
        "/api/plugins/across-orchestrator/actions",
        json={"action": "uninstall"},
    )

    assert response.status_code == 200
    assert calls == ["worker-shutdown", "manager-reset", "uninstall"]
    assert data_file.read_text(encoding="utf-8") == "preserved\n"


def test_legacy_orchestrator_install_endpoint_uses_consumer_safe_transaction(tmp_path, monkeypatch):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-orchestrator"
    wrapper = across_home / "bin" / "across-orchestrator"
    monkeypatch.setenv("ACROSS_HOME", str(across_home))
    calls: list[str] = []

    class FakeManager:
        def reset_runtime_connection(self):
            calls.append("manager-reset")

        def install_plugin(self):
            calls.append("install")
            plugin_dir.mkdir(parents=True)
            wrapper.parent.mkdir(parents=True)
            (plugin_dir / "runtime.txt").write_text("version-a\n", encoding="utf-8")
            wrapper.write_text("wrapper-a\n", encoding="utf-8")
            return {"status": "installed", "installed": True, "integrity_ok": True}

        def implementation_status(self, probe: bool = True):
            assert probe is True
            calls.append("runtime-probe")
            return {
                "implementation": "external",
                "available": True,
                "install": {"installed": True, "integrity_ok": True},
            }

        def install_status(self):
            return {"installed": True, "integrity_ok": True}

    class FakeWorkerRuntime:
        def shutdown(self):
            calls.append("worker-shutdown")

        def reconcile(self):
            calls.append("worker-reconcile")
            return {"status": "running", "listener_pid": 55}

    manager = FakeManager()
    worker = FakeWorkerRuntime()
    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: manager)
    monkeypatch.setattr(api_server, "get_worker_network_runtime", lambda: worker)

    response = TestClient(api_server.app).post("/api/orchestrator/plugin/install")

    assert response.status_code == 200
    assert calls == [
        "worker-shutdown",
        "manager-reset",
        "install",
        "runtime-probe",
        "worker-reconcile",
    ]
    assert response.json()["worker_runtime"]["listener_pid"] == 55


def test_orchestrator_api_rejects_available_status_without_installed_runtime_paths(tmp_path, monkeypatch):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    monkeypatch.setenv("ACROSS_HOME", str(tmp_path / "across"))

    class FakeManager:
        def reset_runtime_connection(self):
            return None

        def install_plugin(self):
            return {"status": "installed", "installed": True, "integrity_ok": True}

        def implementation_status(self, probe: bool = True):
            assert probe is True
            return {
                "implementation": "external",
                "available": True,
                "install": {"installed": True, "integrity_ok": True},
            }

    class FakeWorkerRuntime:
        def shutdown(self):
            return None

        def reconcile(self):
            return {"status": "running", "listener_pid": 99}

    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakeManager())
    monkeypatch.setattr(api_server, "get_worker_network_runtime", lambda: FakeWorkerRuntime())

    response = TestClient(api_server.app).post(
        "/api/plugins/across-orchestrator/actions",
        json={"action": "install"},
    )

    assert response.status_code == 500


def test_orchestrator_api_requires_explicit_integrity_after_install(tmp_path, monkeypatch):
    api_server = importlib.import_module("across_agents_assistant.api_server")
    across_home = tmp_path / "across"
    plugin_dir = across_home / "plugins" / "across-orchestrator"
    wrapper = across_home / "bin" / "across-orchestrator"
    monkeypatch.setenv("ACROSS_HOME", str(across_home))

    class FakeManager:
        def reset_runtime_connection(self):
            return None

        def install_plugin(self):
            plugin_dir.mkdir(parents=True)
            wrapper.parent.mkdir(parents=True)
            (plugin_dir / "runtime.txt").write_text("version-b\n", encoding="utf-8")
            wrapper.write_text("wrapper-b\n", encoding="utf-8")
            return {"status": "installed", "installed": True}

        def implementation_status(self, probe: bool = True):
            assert probe is True
            return {
                "implementation": "external",
                "available": True,
                "install": {"installed": True},
            }

    class FakeWorkerRuntime:
        def shutdown(self):
            return None

        def reconcile(self):
            return {"status": "running", "listener_pid": 101}

    monkeypatch.setattr(api_server, "get_orchestrator_plugin_manager", lambda: FakeManager())
    monkeypatch.setattr(api_server, "get_worker_network_runtime", lambda: FakeWorkerRuntime())

    response = TestClient(api_server.app).post(
        "/api/plugins/across-orchestrator/actions",
        json={"action": "install"},
    )

    assert response.status_code == 500
    assert not plugin_dir.exists()
    assert not wrapper.exists()
