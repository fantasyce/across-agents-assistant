from __future__ import annotations

from pathlib import Path
from types import TracebackType
from typing import Optional, Type
import logging
import os
import shutil
import tempfile


logger = logging.getLogger("across_agents_assistant.managed_plugin_lifecycle")


class ManagedPluginLifecycleRecoveryError(RuntimeError):
    """Raised when a failed lifecycle mutation cannot restore its snapshot."""


class ManagedPluginLifecycleCleanupError(RuntimeError):
    """Raised when transaction evidence cannot be removed after completion."""


class ManagedPluginFilesystemTransaction:
    """Recover one managed plugin directory and wrapper as a single host action."""

    def __init__(
        self,
        *,
        plugin_id: str,
        plugin_dir: Path,
        wrapper_path: Path,
        transaction_root: Path,
    ) -> None:
        self.plugin_id = str(plugin_id)
        self.plugin_dir = Path(plugin_dir)
        self.wrapper_path = Path(wrapper_path)
        self.transaction_root = Path(transaction_root)
        self._workspace: Optional[Path] = None
        self._plugin_existed = False
        self._wrapper_existed = False

    def __enter__(self) -> "ManagedPluginFilesystemTransaction":
        self._validate_runtime_roots()
        self.transaction_root.mkdir(parents=True, exist_ok=True)
        self._workspace = Path(
            tempfile.mkdtemp(prefix=f"{self.plugin_id}-", dir=str(self.transaction_root))
        )
        try:
            self._plugin_existed = self.plugin_dir.is_dir()
            self._wrapper_existed = self.wrapper_path.is_file()
            if self._plugin_existed:
                shutil.copytree(self.plugin_dir, self._workspace / "plugin", symlinks=True)
            if self._wrapper_existed:
                shutil.copy2(self.wrapper_path, self._workspace / "wrapper")
        except Exception:
            self._cleanup()
            raise
        return self

    def _validate_runtime_roots(self) -> None:
        for label, path, expected_kind in (
            ("plugin directory", self.plugin_dir, "directory"),
            ("wrapper", self.wrapper_path, "file"),
        ):
            if path.is_symlink():
                raise ValueError(f"Managed plugin {label} must not be a symbolic link")
            if path.exists():
                valid = path.is_dir() if expected_kind == "directory" else path.is_file()
                if not valid:
                    raise ValueError(f"Managed plugin {label} has an unexpected filesystem type")

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> bool:
        if exc_type is None:
            self._cleanup()
            return False
        try:
            self._restore()
        except Exception as recovery_error:
            recovery_path = str(self._workspace) if self._workspace is not None else "unavailable"
            raise ManagedPluginLifecycleRecoveryError(
                f"Failed to recover {self.plugin_id} after lifecycle failure; "
                f"snapshot preserved at {recovery_path}"
            ) from recovery_error
        try:
            self._cleanup()
        except ManagedPluginLifecycleCleanupError as cleanup_error:
            logger.error(str(cleanup_error), exc_info=cleanup_error)
            if exc is not None:
                add_note = getattr(exc, "add_note", None)
                if callable(add_note):
                    add_note(str(cleanup_error))
        return False

    def _restore(self) -> None:
        if self._workspace is None:
            raise RuntimeError("Managed plugin transaction was not started")
        if self.plugin_dir.exists() or self.plugin_dir.is_symlink():
            if self.plugin_dir.is_dir() and not self.plugin_dir.is_symlink():
                shutil.rmtree(self.plugin_dir)
            else:
                self.plugin_dir.unlink()
        if self.wrapper_path.exists() or self.wrapper_path.is_symlink():
            self.wrapper_path.unlink()

        if self._plugin_existed:
            self.plugin_dir.parent.mkdir(parents=True, exist_ok=True)
            os.replace(self._workspace / "plugin", self.plugin_dir)
        if self._wrapper_existed:
            self.wrapper_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(self._workspace / "wrapper", self.wrapper_path)

    def _cleanup(self) -> None:
        if self._workspace is None:
            return
        workspace = self._workspace
        try:
            shutil.rmtree(workspace)
        except Exception as cleanup_error:
            raise ManagedPluginLifecycleCleanupError(
                f"Failed to clean up {self.plugin_id} lifecycle workspace; "
                f"snapshot retained at {workspace}"
            ) from cleanup_error
        self._workspace = None
