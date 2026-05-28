import re
import tomllib
from pathlib import Path

from across_agents_assistant import __version__


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_python_package_version_matches_pyproject():
    pyproject = tomllib.loads((PROJECT_ROOT / "backend/pyproject.toml").read_text(encoding="utf-8"))

    assert __version__ == pyproject["project"]["version"]


def test_build_app_uses_project_version_for_macos_bundle():
    script = (PROJECT_ROOT / "build_app.sh").read_text(encoding="utf-8")

    assert 'APP_VERSION="' in script
    assert re.search(r"<key>CFBundleShortVersionString</key>\s*<string>\$APP_VERSION</string>", script)
    assert re.search(r"<key>CFBundleVersion</key>\s*<string>\$APP_VERSION</string>", script)
