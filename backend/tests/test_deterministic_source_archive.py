from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "create_deterministic_source_archive.py"
PAYLOAD_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "prepare_managed_plugin_payloads.sh"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_local_source_archive_is_reproducible_and_excludes_build_state(tmp_path: Path) -> None:
    source = tmp_path / "across-plugin"
    (source / "src").mkdir(parents=True)
    (source / "src" / "cli.js").write_text("console.log('ready')\n", encoding="utf-8")
    (source / "package.json").write_text('{"version":"1.0.0"}\n', encoding="utf-8")
    (source / "node_modules" / "ignored").mkdir(parents=True)
    (source / "node_modules" / "ignored" / "index.js").write_text("ignored", encoding="utf-8")

    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    command = [
        sys.executable,
        str(SCRIPT),
        "--source",
        str(source),
        "--exclude",
        "node_modules",
    ]
    subprocess.run([*command, "--output", str(first)], check=True)

    timestamp = time.time() + 120
    os.utime(source / "src" / "cli.js", (timestamp, timestamp))
    subprocess.run([*command, "--output", str(second)], check=True)

    assert _digest(first) == _digest(second)
    with tarfile.open(second, "r:gz") as archive:
        names = archive.getnames()
        assert "across-plugin/src/cli.js" in names
        assert all("node_modules" not in name for name in names)
        assert all(member.mtime == 0 for member in archive.getmembers())


def test_orchestrator_runtime_build_uses_reproducible_pyinstaller_environment() -> None:
    source = PAYLOAD_SCRIPT.read_text(encoding="utf-8")

    reproducible_prefix = "PYTHONHASHSEED=1 SOURCE_DATE_EPOCH=0 PYTHONPATH="
    assert reproducible_prefix in source
    assert source.index(reproducible_prefix) < source.index('"$BUILD_PYTHON" -m PyInstaller')
