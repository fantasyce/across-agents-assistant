"""Across-owned Goal Contract protocol and host-governed services."""

from .protocol import (
    criterion_id,
    normalize_goal_change_proposal,
    normalize_goal_contract,
    stable_goal_hash,
)

__all__ = [
    "criterion_id",
    "normalize_goal_change_proposal",
    "normalize_goal_contract",
    "stable_goal_hash",
]
