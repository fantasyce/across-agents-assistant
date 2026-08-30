import json
import pathlib
import re
import tomllib

import across_agents_assistant
from across_agents_assistant.plugin_runtime import KNOWN_PLUGINS


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


def test_bundled_plugin_source_versions_match_host_install_sources():
    root = pathlib.Path(__file__).resolve().parents[2]
    preparation = (root / "scripts" / "prepare_managed_plugin_payloads.sh").read_text(
        encoding="utf-8"
    )
    bundled_versions = {
        "across-context": re.search(r'^CONTEXT_VERSION="([^"]+)"$', preparation, re.MULTILINE),
        "across-orchestrator": re.search(
            r'^ORCHESTRATOR_VERSION="([^"]+)"$', preparation, re.MULTILINE
        ),
        "across-autopilot": re.search(
            r'^AUTOPILOT_VERSION="([^"]+)"$', preparation, re.MULTILINE
        ),
    }

    assert all(match is not None for match in bundled_versions.values())
    for plugin in KNOWN_PLUGINS:
        source_version = re.search(r"[#@]v(\d+\.\d+\.\d+)$", plugin.default_install_source or "")
        assert source_version is not None
        assert bundled_versions[plugin.plugin_id].group(1) == source_version.group(1)


def test_product_manifest_tracks_agent_runtime_proof_as_external_plugin():
    root = pathlib.Path(__file__).resolve().parents[2]
    product = json.loads((root / "across.product.json").read_text(encoding="utf-8"))

    assert product["current_releases"]["agent_runtime_proof"]["version"] == "v1.0.1"
    component = product["components"]["agent_runtime_proof"]
    assert component["repository"] == "fantasyce/agent-runtime-proof"
    assert component["integration"] == "generic external MCP plugin"
    assert component["managed_by_aaa"] is False


def test_worker_catalog_matches_current_managed_producer_versions():
    root = pathlib.Path(__file__).resolve().parents[2]
    preparation = (root / "scripts" / "prepare_managed_plugin_payloads.sh").read_text(
        encoding="utf-8"
    )
    catalog = json.loads(
        (
            root
            / "backend"
            / "src"
            / "across_agents_assistant"
            / "assets"
            / "worker-release-catalog.json"
        ).read_text(encoding="utf-8")
    )
    orchestrator_version = re.search(
        r'^ORCHESTRATOR_VERSION="([^"]+)"$', preparation, re.MULTILINE
    )
    autopilot_version = re.search(
        r'^AUTOPILOT_VERSION="([^"]+)"$', preparation, re.MULTILINE
    )

    assert orchestrator_version is not None
    assert autopilot_version is not None
    assert orchestrator_version.group(1) == "0.12.0"
    assert catalog["published"] is True
    assert catalog["version"] == orchestrator_version.group(1)
    assert catalog["bootstrap"]["sha256"] == (
        "925d2dea6d1b992e6fafd34861a9fa8fc9193785ba9d07c2559683b60a859f76"
    )
    for platform, asset in catalog["assets"].items():
        assert platform in {"macos-arm64", "macos-x86_64", "linux-arm64", "linux-x86_64"}
        assert "/v0.12.0/" in asset["url"]
        assert asset["sha256"] == (
            "c04b142eb5d42f188a0486fbaaabcec5fe086ea2b8d1982c0963c3a262b8914b"
        )
    scenario_url = catalog["workflow_packs"]["scenario-simulation"]["url"]
    assert f"/v{autopilot_version.group(1)}/" in scenario_url
    assert f"-{autopilot_version.group(1)}.tar.gz" in scenario_url
