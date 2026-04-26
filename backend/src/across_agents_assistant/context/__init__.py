# backend/src/across_agents_assistant/context/__init__.py
from .base import ContextCollector
from .registry import ContextCollectorRegistry, registry

__all__ = ["ContextCollector", "ContextCollectorRegistry", "registry"]