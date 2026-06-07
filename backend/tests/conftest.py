import os
from pathlib import Path

import pytest


LIVE_E2E_ENV = "ACROSS_AGENTS_RUN_LIVE_E2E"
LIVE_E2E_FILES = {
    Path("e2e/test_e2e_complex_multi_wave.py"),
    Path("e2e/test_e2e_minimal_task.py"),
    Path("e2e/test_e2e_rest_api.py"),
}


def pytest_collection_modifyitems(config, items):
    if os.environ.get(LIVE_E2E_ENV) == "1":
        return

    skip_live_e2e = pytest.mark.skip(
        reason=f"live app E2E requires {LIVE_E2E_ENV}=1"
    )
    tests_root = Path(__file__).resolve().parent

    for item in items:
        try:
            relative_path = Path(item.fspath).resolve().relative_to(tests_root)
        except ValueError:
            continue
        if relative_path in LIVE_E2E_FILES:
            item.add_marker(skip_live_e2e)
