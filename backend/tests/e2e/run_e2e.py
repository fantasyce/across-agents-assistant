#!/usr/bin/env python3
"""Convenience runner for E2E regression test suite.

Usage:
  # Run all E2E tests against the packaged app backend Unix socket
  python3 tests/e2e/run_e2e.py

  # Custom backend URL
  ACROSS_AGENTS_API=http://localhost:9988 python3 tests/e2e/run_e2e.py

  # Custom packaged-app socket
  ACROSS_AGENTS_SOCKET=~/.across/run/across-agents-assistant/across-agents.sock python3 tests/e2e/run_e2e.py

  # Run a specific tier
  python3 tests/e2e/run_e2e.py --tier minimal
  python3 tests/e2e/run_e2e.py --tier rest-api
  python3 tests/e2e/run_e2e.py --tier complex
"""

import os
import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from client import base_label, configured_providers, request


def check_backend() -> bool:
    """Quick health check before running tests."""
    try:
        request("GET", "/api/llm/status")
        return True
    except Exception:
        return False


def check_keys() -> dict:
    """Return provider -> status mapping."""
    try:
        return {provider: "configured" for provider in configured_providers()}
    except Exception as e:
        return {"error": str(e)}


def check_orchestrator_runtime() -> tuple[bool, str]:
    """Return external Orchestrator availability and a human-readable note."""
    try:
        status = request("GET", "/api/orchestrator/plugin")
    except Exception as e:
        return False, f"Unable to inspect /api/orchestrator/plugin: {e}"
    runtime = status.get("runtime") if isinstance(status.get("runtime"), dict) else status
    available = bool(runtime.get("available"))
    mode = runtime.get("mode") or "unknown"
    implementation = runtime.get("implementation") or "unknown"
    transport = runtime.get("transport") or "none"
    note = runtime.get("connection_note") or runtime.get("error") or "No connection note reported."
    return available, f"mode={mode}, implementation={implementation}, transport={transport}, note={note}"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run E2E regression tests")
    parser.add_argument("--tier", choices=["all", "minimal", "rest-api", "complex"],
                        default="all")
    args = parser.parse_args()

    if not check_backend():
        print("❌ Backend is not reachable. Start the app first.")
        print(f"   Expected at: {base_label()}")
        sys.exit(1)

    keys = check_keys()
    configured = [k for k, v in keys.items() if v == "configured"]
    print(f"✅ Backend reachable at {base_label()}")
    print(f"🔑 Configured providers: {configured or 'NONE'}")
    if not configured:
        print("⚠️  No API keys — only readiness check will pass.\n")
    else:
        print(f"   (keys: {', '.join(configured)})\n")

    orchestrator_available, orchestrator_note = check_orchestrator_runtime()
    print(f"🧭 External Orchestrator: {orchestrator_note}")
    if not orchestrator_available:
        print("❌ External Across Orchestrator runtime is required for live task E2E.")
        print("   Install/configure the plugin or set ACROSS_AGENTS_ORCHESTRATOR_ENDPOINT.")
        sys.exit(2)
    print()

    test_files = {
        "minimal": ["e2e/test_e2e_minimal_task.py"],
        "rest-api": ["e2e/test_e2e_rest_api.py"],
        "complex": ["e2e/test_e2e_complex_multi_wave.py"],
        "all": [
            "e2e/test_e2e_minimal_task.py",
            "e2e/test_e2e_rest_api.py",
            "e2e/test_e2e_complex_multi_wave.py",
        ],
    }

    files = test_files[args.tier]
    print(f"▶️  Running {args.tier} E2E tests ({len(files)} test files)...\n")

    # Run each test file sequentially
    for f in files:
        print(f"{'='*60}")
        print(f"  Running: {f}")
        print(f"{'='*60}")
        env = os.environ.copy()
        env["ACROSS_AGENTS_RUN_LIVE_E2E"] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "pytest", f, "-v", "--tb=short"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))) or ".",
            env=env,
        )
        if result.returncode != 0:
            print(f"\n❌ {f} FAILED (exit code {result.returncode})")
            sys.exit(result.returncode)
        print()

    print("✅ All E2E tests passed!")


if __name__ == "__main__":
    main()
