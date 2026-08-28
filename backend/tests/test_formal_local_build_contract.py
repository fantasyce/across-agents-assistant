from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_formal_local_build_prefers_all_adjacent_plugin_producers() -> None:
    script = (ROOT / "scripts" / "build_and_run.sh").read_text(encoding="utf-8")

    expected_sources = {
        "ACROSS_BUILD_CONTEXT_SOURCE_ROOT": "../across-context",
        "ACROSS_BUILD_AUTOPILOT_SOURCE_ROOT": "../across-autopilot",
        "ACROSS_BUILD_ORCHESTRATOR_SOURCE_ROOT": "../across-orchestrator",
    }
    for variable, relative_source in expected_sources.items():
        assert variable in script
        assert relative_source in script

    assert script.index("ACROSS_BUILD_CONTEXT_SOURCE_ROOT") < script.index(
        '"$PROJECT_ROOT/build_app.sh"'
    )
    assert script.index("ACROSS_BUILD_AUTOPILOT_SOURCE_ROOT") < script.index(
        '"$PROJECT_ROOT/build_app.sh"'
    )
    assert script.index("ACROSS_BUILD_ORCHESTRATOR_SOURCE_ROOT") < script.index(
        '"$PROJECT_ROOT/build_app.sh"'
    )


def test_formal_local_build_cleans_orphaned_worker_control_runtime() -> None:
    script = (ROOT / "scripts" / "build_and_run.sh").read_text(encoding="utf-8")

    assert "seq 1 100" in script
    assert "worker-control-server --socket" in script
    assert "worker-control.sock" in script


def test_formal_local_build_stops_task_owned_descendants_before_rebuild() -> None:
    script = (ROOT / "scripts" / "build_and_run.sh").read_text(encoding="utf-8")

    assert "descendant_pids()" in script
    assert 'pgrep -P "$parent_pid"' in script
    assert "kill $all_pids" in script


def test_formal_local_build_preserves_verified_rollback_before_atomic_install() -> None:
    script = (ROOT / "scripts" / "build_and_run.sh").read_text(encoding="utf-8")

    assert "ROLLBACK_PATH=" in script
    assert "INSTALL_STAGING=" in script
    assert "PREVIOUS_INSTALL=" in script
    assert "restore_previous_install()" in script
    assert 'codesign --verify --deep --strict "$ROLLBACK_STAGING"' in script
    assert 'codesign --verify --deep --strict "$INSTALL_STAGING"' in script
    assert script.index('ditto "$INSTALL_PATH" "$ROLLBACK_STAGING"') < script.index(
        'mv "$INSTALL_PATH" "$PREVIOUS_INSTALL"'
    )
    assert script.index('mv "$INSTALL_PATH" "$PREVIOUS_INSTALL"') < script.index(
        'mv "$INSTALL_STAGING" "$INSTALL_PATH"'
    )
    assert script.count('rm -rf "$INSTALL_PATH"') == 1
    assert script.index('rm -rf "$INSTALL_PATH"') < script.index(
        'echo "=== 3. Installing local build to /Applications ==="'
    )
