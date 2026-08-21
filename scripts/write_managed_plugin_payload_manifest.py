from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


FIRST_PARTY_PLUGIN_IDS = (
    "across-context",
    "across-orchestrator",
    "across-autopilot",
)

_HEX_40 = re.compile(r"[0-9a-f]{40}")
_HEX_64 = re.compile(r"[0-9a-f]{64}")


def _boolean(value: str) -> bool:
    lowered = str(value).strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def _required(value: str, *, name: str, pattern: re.Pattern[str] | None = None) -> str:
    clean = str(value or "").strip()
    if not clean or (pattern is not None and pattern.fullmatch(clean) is None):
        raise ValueError(f"invalid managed payload manifest value: {name}")
    return clean


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    architecture = _required(args.architecture, name="architecture")
    node_version = _required(args.node_version, name="node_version")
    context_version = _required(args.context_version, name="context_version")
    orchestrator_version = _required(args.orchestrator_version, name="orchestrator_version")
    autopilot_version = _required(args.autopilot_version, name="autopilot_version")
    context_commit = _required(args.context_commit, name="context_commit", pattern=_HEX_40)
    orchestrator_commit = _required(
        args.orchestrator_commit,
        name="orchestrator_commit",
        pattern=_HEX_40,
    )
    autopilot_commit = _required(args.autopilot_commit, name="autopilot_commit", pattern=_HEX_40)
    node_sha256 = _required(args.node_sha256, name="node_sha256", pattern=_HEX_64)
    context_sha256 = _required(args.context_sha256, name="context_sha256", pattern=_HEX_64)
    orchestrator_sha256 = _required(
        args.orchestrator_sha256,
        name="orchestrator_sha256",
        pattern=_HEX_64,
    )
    orchestrator_source_sha256 = _required(
        args.orchestrator_source_sha256,
        name="orchestrator_source_sha256",
        pattern=_HEX_64,
    )
    autopilot_sha256 = _required(args.autopilot_sha256, name="autopilot_sha256", pattern=_HEX_64)

    plugins = {
        "across-context": {
            "version": context_version,
            "commit": context_commit,
            "source_kind": _required(args.context_source_kind, name="context_source_kind"),
            "source_dirty": args.context_source_dirty,
            "runtime": "node",
            "archive": f"packages/across-context-{context_version}.tar.gz",
            "sha256": context_sha256,
            "metadata": "package.json",
            "package_name": "@across/context",
            "entrypoint": "src/cli.js",
        },
        "across-orchestrator": {
            "version": orchestrator_version,
            "commit": orchestrator_commit,
            "source_kind": _required(
                args.orchestrator_source_kind,
                name="orchestrator_source_kind",
            ),
            "source_dirty": args.orchestrator_source_dirty,
            "runtime": "native",
            "executable": (
                f"runtimes/orchestrator-{orchestrator_version}/across-orchestrator"
            ),
            "sha256": orchestrator_sha256,
            "source_archive": (
                f"packages/across-orchestrator-{orchestrator_version}.tar.gz"
            ),
            "source_sha256": orchestrator_source_sha256,
        },
        "across-autopilot": {
            "version": autopilot_version,
            "commit": autopilot_commit,
            "source_kind": _required(args.autopilot_source_kind, name="autopilot_source_kind"),
            "source_dirty": args.autopilot_source_dirty,
            "runtime": "node",
            "archive": f"packages/across-autopilot-{autopilot_version}.tar.gz",
            "sha256": autopilot_sha256,
            "metadata": "package.json",
            "package_name": "@across/autopilot",
            "entrypoint": "src/cli.js",
        },
    }
    if tuple(plugins) != FIRST_PARTY_PLUGIN_IDS:
        raise ValueError("managed payload manifest first-party plugin set is invalid")
    return {
        "schema_version": "across-managed-plugin-payloads/1.0",
        "platform": "macos",
        "architecture": architecture,
        "runtimes": {
            "node": {
                "version": node_version,
                "path": f"runtimes/node-{node_version}",
                "executable": "bin/node",
                "sha256": node_sha256,
            }
        },
        "plugins": plugins,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write the managed plugin payload manifest.")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--architecture", required=True)
    parser.add_argument("--node-version", required=True)
    parser.add_argument("--node-sha256", required=True)
    for plugin in ("context", "orchestrator", "autopilot"):
        parser.add_argument(f"--{plugin}-version", required=True)
        parser.add_argument(f"--{plugin}-commit", required=True)
        parser.add_argument(f"--{plugin}-source-kind", required=True)
        parser.add_argument(f"--{plugin}-source-dirty", required=True, type=_boolean)
        parser.add_argument(f"--{plugin}-sha256", required=True)
    parser.add_argument("--orchestrator-source-sha256", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = build_manifest(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
