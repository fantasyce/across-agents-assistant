import pathlib
import re

import across_agents_assistant


def test_release_version_sources_are_consistent_for_v0_4_3():
    root = pathlib.Path(__file__).resolve().parents[2]
    pyproject = root / "backend" / "pyproject.toml"
    match = re.search(r'^version = "([^"]+)"', pyproject.read_text(), re.MULTILINE)

    assert match is not None
    assert match.group(1) == "0.4.3"
    assert across_agents_assistant.__version__ == "0.4.3"
