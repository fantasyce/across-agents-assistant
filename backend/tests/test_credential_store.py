"""Tests for CredentialStore — backend-owned credentials file manager."""

import json
import os
import stat
import time

from across_agents_assistant.credentials.store import (
    CredentialStore,
    KNOWN_PROVIDER_IDS,
    ProviderCredential,
)


def test_load_all_returns_empty_when_file_missing(tmp_path):
    store = CredentialStore(path=tmp_path / "missing.json")
    result = store.load_all()
    assert result == {}


def test_save_many_writes_atomic_json_with_0600_permissions(tmp_path):
    store = CredentialStore(path=tmp_path / "creds.json")
    saved = store.save_many({"deepseek": "unit-valid-deepseek-key"}, source="frontend_save")

    assert "deepseek" in saved
    assert saved["deepseek"] == "unit-valid-deepseek-key"
    assert tmp_path.joinpath("creds.json").exists()

    st_mode = os.stat(tmp_path / "creds.json").st_mode
    assert oct(st_mode & 0o777) in ("0o600", "0o600")

    with open(tmp_path / "creds.json") as f:
        data = json.load(f)
    assert data["version"] == 1
    assert data["providers"]["deepseek"]["api_key"] == "unit-valid-deepseek-key"
    assert data["providers"]["deepseek"]["source"] == "frontend_save"


def test_save_many_rejects_placeholder_values(tmp_path):
    store = CredentialStore(path=tmp_path / "creds.json")
    saved = store.save_many({"minimax": "placeholder-secret"}, source="frontend_save")

    assert saved == {}
    assert store.load_all() == {}


def test_delete_removes_provider_but_keeps_other_keys(tmp_path):
    store = CredentialStore(path=tmp_path / "creds.json")
    store.save_many({"deepseek": "unit-valid-ds", "minimax": "unit-valid-mm"}, source="frontend_save")

    store.delete("deepseek")
    result = store.load_all()
    assert "deepseek" not in result
    assert result["minimax"].api_key == "unit-valid-mm"


def test_load_all_ignores_blank_values(tmp_path):
    store = CredentialStore(path=tmp_path / "creds.json")
    store.save_many({"deepseek": "unit-valid", "minimax": ""}, source="frontend_save")

    result = store.load_all()
    assert "deepseek" in result
    assert "minimax" not in result


def test_load_all_handles_invalid_json_without_crashing(tmp_path):
    p = tmp_path / "creds.json"
    p.write_text("{invalid json!!!")
    store = CredentialStore(path=p)

    result = store.load_all()
    assert result == {}


def test_save_many_updates_existing_provider(tmp_path):
    store = CredentialStore(path=tmp_path / "creds.json")
    store.save_many({"deepseek": "unit-valid-v1"}, source="frontend_save")
    store.save_many({"deepseek": "unit-valid-v2"}, source="frontend_save")

    result = store.load_all()
    assert result["deepseek"].api_key == "unit-valid-v2"


def test_get_returns_none_for_missing(tmp_path):
    store = CredentialStore(path=tmp_path / "creds.json")
    assert store.get("nonexistent") is None


def test_get_returns_key_for_configured(tmp_path):
    store = CredentialStore(path=tmp_path / "creds.json")
    store.save_many({"deepseek": "unit-valid"}, source="frontend_save")
    assert store.get("deepseek") == "unit-valid"


def test_delete_nonexistent_provider_does_not_raise(tmp_path):
    store = CredentialStore(path=tmp_path / "creds.json")
    store.delete("nonexistent")  # should not raise


def test_load_all_skips_unknown_providers(tmp_path):
    store = CredentialStore(path=tmp_path / "creds.json")
    store.save_many({"deepseek": "unit-valid", "unknown_provider": "unit-valid-ignored"}, source="frontend_save")

    result = store.load_all()
    assert "deepseek" in result
    assert "unknown_provider" not in result


def test_ensure_permissions_fixes_broad_permissions(tmp_path):
    p = tmp_path / "creds.json"
    p.write_text('{"version": 1, "providers": {}}')
    os.chmod(p, 0o644)

    store = CredentialStore(path=p)
    store.ensure_permissions()

    st_mode = os.stat(p).st_mode
    assert oct(st_mode & 0o777) in ("0o600", "0o600")


def test_load_all_parses_provider_sources(tmp_path):
    store = CredentialStore(path=tmp_path / "creds.json")
    store.save_many({"deepseek": "unit-valid-ds"}, source="keychain_import")

    result = store.load_all()
    assert result["deepseek"].source == "keychain_import"


def test_init_schema_creates_credential_metadata_table():
    """Verify credential_metadata DDL is present in database.py."""
    import pathlib
    db_py = pathlib.Path(__file__).resolve().parent.parent / "src" / "across_agents_assistant" / "persistence" / "database.py"
    text = db_py.read_text()
    assert "credential_metadata" in text
    assert "provider_id TEXT PRIMARY KEY" in text
    assert "is_configured INTEGER" in text
