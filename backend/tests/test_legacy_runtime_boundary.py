from pathlib import Path
import threading
import time

import across_agents_assistant.api_server as api_server
import across_agents_assistant.legacy_task_runtime as legacy_task_runtime
from across_agents_assistant.legacy_task_runtime import SyncLLMWrapper


def test_api_server_does_not_import_historical_task_orchestrator_directly():
    source = Path(api_server.__file__).read_text(encoding="utf-8")

    assert "task_manager.orchestration.orchestrator import TaskOrchestrator" not in source
    assert "from .legacy_task_runtime import build_legacy_task_orchestrator" in source


def test_legacy_runtime_module_owns_historical_task_orchestrator_import():
    source = Path(legacy_task_runtime.__file__).read_text(encoding="utf-8")

    assert "task_manager.orchestration.orchestrator import TaskOrchestrator" in source


def test_sync_llm_wrapper_starts_one_loop_under_concurrent_first_use(monkeypatch):
    class Gateway:
        async def chat(self, **_kwargs):
            return "ok"

    wrapper = SyncLLMWrapper(Gateway())
    real_new_event_loop = legacy_task_runtime.asyncio.new_event_loop
    calls = 0
    calls_lock = threading.Lock()

    def slow_new_event_loop():
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return real_new_event_loop()

    monkeypatch.setattr(legacy_task_runtime.asyncio, "new_event_loop", slow_new_event_loop)
    errors: list[BaseException] = []

    def ensure_loop():
        try:
            wrapper._ensure_loop()
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=ensure_loop) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=2)

    try:
        assert errors == []
        assert calls == 1
    finally:
        if wrapper._loop and wrapper._loop.is_running():
            wrapper._loop.call_soon_threadsafe(wrapper._loop.stop)
        if wrapper._thread:
            wrapper._thread.join(timeout=2)
