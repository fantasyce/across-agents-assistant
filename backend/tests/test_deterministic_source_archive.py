from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "create_deterministic_source_archive.py"
PINNED_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "create_pinned_source_archive.py"
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


def test_pinned_source_archive_is_commit_bound_reproducible_and_transactional(tmp_path: Path) -> None:
    producer = tmp_path / "producer"
    (producer / "src").mkdir(parents=True)
    (producer / "src" / "cli.js").write_text("console.log('pinned')\n", encoding="utf-8")
    (producer / "package.json").write_text('{"version":"1.0.0"}\n', encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(producer)], check=True)
    subprocess.run(["git", "-C", str(producer), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(producer), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(producer), "add", "."], check=True)
    subprocess.run(["git", "-C", str(producer), "commit", "-qm", "fixture"], check=True)
    commit = subprocess.run(
        ["git", "-C", str(producer), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    canonical = tmp_path / "canonical.tar.gz"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--source",
            str(producer),
            "--output",
            str(canonical),
            "--archive-root",
            "across-fixture",
            "--exclude",
            ".git",
        ],
        check=True,
    )
    expected = _digest(canonical)

    output = tmp_path / "pinned.tar.gz"
    command = [
        sys.executable,
        str(PINNED_SCRIPT),
        "--repository",
        str(producer),
        "--commit",
        commit,
        "--output",
        str(output),
        "--archive-root",
        "across-fixture",
        "--expected-sha256",
        expected,
        "--version-file",
        "package.json",
        "--expected-version",
        "1.0.0",
        "--exclude",
        ".git",
    ]
    subprocess.run(command, check=True)
    assert _digest(output) == expected

    (producer / "src" / "cli.js").write_text("console.log('new head')\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(producer), "add", "."], check=True)
    subprocess.run(["git", "-C", str(producer), "commit", "-qm", "new head"], check=True)
    output.write_text("corrupt cache", encoding="utf-8")
    subprocess.run(command, check=True)
    assert _digest(output) == expected

    before = output.read_bytes()
    wrong_checksum = command.copy()
    wrong_checksum[wrong_checksum.index("--expected-sha256") + 1] = "0" * 64
    failed = subprocess.run(wrong_checksum, capture_output=True, text=True)
    assert failed.returncode != 0
    assert output.read_bytes() == before
    assert str(producer) not in failed.stderr

    wrong_version = command.copy()
    wrong_version[wrong_version.index("--expected-version") + 1] = "9.9.9"
    failed = subprocess.run(wrong_version, capture_output=True, text=True)
    assert failed.returncode != 0
    assert output.read_bytes() == before
    assert str(producer) not in failed.stderr


def test_released_plugin_payloads_do_not_trust_codeload_archive_bytes() -> None:
    source = PAYLOAD_SCRIPT.read_text(encoding="utf-8")

    assert "codeload.github.com" not in source
    assert source.count("create_pinned_source_archive.py") == 3
    assert source.count("--expected-version") == 3
