"""Backend-owned credential store for cloud LLM API keys.

The credentials live in ``~/.across/data/across-agents-assistant/credentials.json`` with ``0600``
permissions.  The backend owns reading, writing, validating, and permission-
checking this file.  The database stores metadata only (never raw keys).
"""

from __future__ import annotations

import json
import logging
import os
import stat
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from ..paths import data_file
from .validation import is_usable_secret, normalize_secret
from ..llm_gateway.provider_registry import get_default_provider_ids

logger = logging.getLogger("across_agents_assistant.credentials")


DEFAULT_CREDENTIALS_PATH = data_file("credentials.json")
_CREDENTIALS_FILE_ENV = "ACROSS_AGENTS_CREDENTIALS_FILE"

KNOWN_PROVIDER_IDS = set(get_default_provider_ids())


@dataclass
class ProviderCredential:
    provider_id: str
    api_key: str
    source: str
    updated_at: str


class CredentialStore:
    """File-backed credential store for cloud LLM provider API keys.

    Writes are atomic (write to temp file, then ``os.replace``).
    File permissions are enforced to ``0600``.
    Malformed files produce empty results and a warning log — they do
    not crash the backend.
    """

    def __init__(self, path: Optional[Path] = None):
        self.path = path or _default_credentials_path()

    # -- Public API -----------------------------------------------------------

    def load_all(self) -> Dict[str, ProviderCredential]:
        """Load all non-empty provider credentials from the store.

        Returns a dict keyed by provider_id.  Unknown provider IDs,
        blank keys, and malformed files are silently skipped.
        """
        if not self.path.exists():
            return {}

        try:
            with open(self.path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to parse credentials file %s: %s", self.path, e)
            return {}

        providers_raw = data.get("providers") or {}
        result: Dict[str, ProviderCredential] = {}
        for pid, info in providers_raw.items():
            if pid not in KNOWN_PROVIDER_IDS:
                continue
            api_key = normalize_secret(info.get("api_key"))
            if not is_usable_secret(api_key):
                continue
            result[pid] = ProviderCredential(
                provider_id=pid,
                api_key=api_key,
                source=str(info.get("source", "unknown")),
                updated_at=str(info.get("updated_at", "")),
            )
        return result

    def get(self, provider_id: str) -> Optional[str]:
        """Return the raw API key for *provider_id*, or None."""
        all_creds = self.load_all()
        cred = all_creds.get(provider_id)
        return cred.api_key if cred else None

    def save_many(
        self,
        values: Dict[str, str],
        source: str,
    ) -> Dict[str, str]:
        """Save multiple provider keys with a single atomic write.

        Args:
            values: ``{provider_id: api_key}`` — blank keys become deletes.
            source: Origin label (``frontend_save``, ``keychain_import``, …).

        Returns:
            Dict of ``{provider_id: api_key}`` that were actually saved
            (non-blank, known provider).
        """
        existing = self._read_existing()
        providers = existing.get("providers", {})
        now = _now_iso()
        saved: Dict[str, str] = {}

        for pid, raw_key in values.items():
            key = normalize_secret(raw_key)
            if key and is_usable_secret(key) and pid in KNOWN_PROVIDER_IDS:
                providers[pid] = {
                    "api_key": key,
                    "source": source,
                    "updated_at": now,
                }
                saved[pid] = key
            elif pid in KNOWN_PROVIDER_IDS and pid in providers:
                providers.pop(pid, None)

        self._atomic_write({"version": 1, "providers": providers})
        return saved

    def delete(self, provider_id: str) -> None:
        """Remove a provider's credential from the store."""
        existing = self._read_existing()
        providers = existing.get("providers", {})
        if provider_id in providers:
            providers.pop(provider_id, None)
        self._atomic_write({"version": 1, "providers": providers})

    def ensure_permissions(self) -> None:
        """Ensure credentials file has ``0600`` permissions; fix if not."""
        if not self.path.exists():
            return
        st_mode = os.stat(self.path).st_mode
        if st_mode & 0o777 != 0o600:
            logger.warning(
                "Fixing credentials file permissions from %s to 0600: %s",
                oct(st_mode & 0o777), self.path,
            )
            os.chmod(self.path, 0o600)

    # -- Internal helpers -----------------------------------------------------

    def _read_existing(self) -> dict:
        """Read the current file content as a dict, or return empty skeleton."""
        if not self.path.exists():
            return {"version": 1, "providers": {}}
        try:
            with open(self.path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"version": 1, "providers": {}}

    def _atomic_write(self, data: dict) -> None:
        """Write *data* atomically to the credentials file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(
            prefix="credentials_",
            suffix=".tmp",
            dir=self.path.parent,
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, str(self.path))
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _default_credentials_path() -> Path:
    override = os.environ.get(_CREDENTIALS_FILE_ENV)
    if override and override.strip():
        return Path(override).expanduser().resolve()
    return DEFAULT_CREDENTIALS_PATH
