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


def test_backend_requirements_reject_incompatible_mcp_major_versions():
    root = pathlib.Path(__file__).resolve().parents[2]

    for relative_path in (
        pathlib.Path("backend/requirements.txt"),
        pathlib.Path("backend/requirements_no_pyobjc.txt"),
    ):
        requirements = (root / relative_path).read_text(encoding="utf-8").splitlines()
        mcp_requirement = next(line for line in requirements if line.startswith("mcp[cli]"))

        assert mcp_requirement == "mcp[cli]>=1.28.1,<2"
