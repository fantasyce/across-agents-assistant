import pathlib
import re
import tomllib

import across_agents_assistant


def test_release_version_sources_are_consistent():
    root = pathlib.Path(__file__).resolve().parents[2]
    pyproject = root / "backend" / "pyproject.toml"
    metadata = tomllib.loads(pyproject.read_text())
    project_version = metadata["project"]["version"]

    assert re.fullmatch(r"\d+\.\d+\.\d+", project_version)
    assert across_agents_assistant.__version__ == project_version
