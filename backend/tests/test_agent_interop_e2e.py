import threading
import time

from across_agents_assistant.agent_interop_e2e import AgentInteropE2ERunCoordinator


def test_agent_interop_run_coordinator_returns_immediately_and_deduplicates_active_run():
    coordinator = AgentInteropE2ERunCoordinator()
    release = threading.Event()
    started = threading.Event()
    calls = []

    def runner():
        calls.append("run")
        started.set()
        release.wait(timeout=2)
        return {"status": "passed", "summary": {"failed_count": 0}}

    first = coordinator.start(runner)
    assert started.wait(timeout=1)
    second = coordinator.start(runner)

    assert first["status"] == "running"
    assert second["status"] == "running"
    assert calls == ["run"]

    release.set()
    deadline = time.monotonic() + 2
    while coordinator.status()["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)

    assert coordinator.status()["status"] == "passed"
    assert coordinator.status()["failed_count"] == 0


def test_agent_interop_run_coordinator_exposes_bounded_failure_state():
    coordinator = AgentInteropE2ERunCoordinator()

    def runner():
        raise RuntimeError("private local failure details")

    coordinator.start(runner)
    deadline = time.monotonic() + 2
    while coordinator.status()["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.01)

    assert coordinator.status()["status"] == "failed"
    assert coordinator.status()["failed_count"] == 1
    assert "private local failure details" not in str(coordinator.status())
