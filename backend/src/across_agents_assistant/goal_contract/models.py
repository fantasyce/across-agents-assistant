from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass
class GoalProjectionFacts:
    """Authoritative inputs used to derive, never assign, a goal state."""

    contract: Mapping[str, Any]
    dependencies: dict[str, str] = field(default_factory=dict)
    criterion_evidence: dict[str, str] = field(default_factory=dict)
    reviews: dict[str, str] = field(default_factory=dict)
    pending_decisions: tuple[str, ...] = ()
    active_lease_count: int = 0
    execution_state: str = "not_started"
