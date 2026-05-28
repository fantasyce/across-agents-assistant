"""Credential value validation helpers."""

from __future__ import annotations

from typing import Optional


def normalize_secret(value: Optional[str]) -> Optional[str]:
    """Strip whitespace from a credential value; treat blank strings as missing."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def is_usable_secret(value: Optional[str]) -> bool:
    """Return True when *value* looks like a real backend credential."""
    normalized = normalize_secret(value)
    if not normalized:
        return False

    lowered = normalized.lower()
    placeholder_exact = {
        "test",
        "dummy",
        "placeholder",
        "changeme",
        "your-api-key",
        "example",
        "example-key",
    }
    if lowered in placeholder_exact:
        return False

    blocked_prefixes = (
        "test-",
        "dummy-",
        "placeholder-",
        "example-",
        "sample-",
        "fake-",
        "live-",
        "".join(("sk-", "test")),
        "".join(("sk-", "live")),
        "sk" + "_dummy",
        "".join(("sk-", "placeholder")),
    )
    return not lowered.startswith(blocked_prefixes)
