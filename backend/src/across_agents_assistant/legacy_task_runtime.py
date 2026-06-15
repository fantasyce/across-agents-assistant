from __future__ import annotations

import asyncio
import threading
from typing import Any

from .task_manager.orchestration.orchestrator import TaskOrchestrator
from .task_manager.orchestration.owner_agent import OwnerAgent
from .task_manager.orchestration.validator import ContractValidator


class SyncLLMWrapper:
    """Synchronous wrapper for the async LLMGateway used by legacy OwnerAgent."""

    def __init__(self, gateway: Any):
        self._gateway = gateway
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _ensure_loop(self) -> None:
        with self._lock:
            if self._loop and self._loop.is_running() and self._thread and self._thread.is_alive():
                return
            loop = asyncio.new_event_loop()
            ready = threading.Event()

            def _runner() -> None:
                asyncio.set_event_loop(loop)
                ready.set()
                loop.run_forever()

            self._loop = loop
            self._thread = threading.Thread(target=_runner, name="legacy-llm-gateway", daemon=True)
            self._thread.start()
            if not ready.wait(timeout=5):
                raise RuntimeError("Legacy LLM gateway loop did not start")

    def __call__(self, system_prompt: str, message: str, temperature: float):
        self._ensure_loop()

        async def _chat():
            return await self._gateway.chat(
                message=message,
                system_prompt=system_prompt,
                temperature=temperature,
            )

        if self._loop is None:
            raise RuntimeError("Legacy LLM gateway loop is not available")
        future = asyncio.run_coroutine_threadsafe(_chat(), self._loop)
        return future.result(timeout=300)


def build_legacy_task_orchestrator(*, state: Any, dispatcher: Any, gateway: Any) -> TaskOrchestrator:
    validator = ContractValidator(state)
    owner_agent = OwnerAgent(SyncLLMWrapper(gateway), state)
    return TaskOrchestrator(
        state=state,
        dispatcher=dispatcher,
        validator=validator,
        owner_agent=owner_agent,
    )
