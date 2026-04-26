# backend/tests/context/test_registry.py
import pytest
from typing import Dict, Any
from unittest.mock import MagicMock
from across_agents_assistant.context.base import ContextCollector
from across_agents_assistant.context.registry import ContextCollectorRegistry

class MockCollector(ContextCollector):
    def __init__(self, name: str, available: bool = True):
        self._name = name
        self._available = available

    @property
    def source_name(self) -> str:
        return self._name

    def collect(self) -> Dict[str, Any]:
        return {"data": f"collected from {self._name}"}

    def is_available(self) -> bool:
        return self._available

def test_registry_register():
    reg = ContextCollectorRegistry()
    collector = MockCollector("test")
    reg.register(collector)
    assert "test" in reg.get_all_sources()

def test_registry_collect_all():
    reg = ContextCollectorRegistry()
    reg.register(MockCollector("source1"))
    reg.register(MockCollector("source2"))
    result = reg.collect_all()
    assert "source1" in result
    assert "source2" in result

def test_registry_get_available():
    reg = ContextCollectorRegistry()
    reg.register(MockCollector("available", True))
    reg.register(MockCollector("unavailable", False))
    assert "available" in reg.get_available_sources()
    assert "unavailable" not in reg.get_available_sources()

def test_registry_collect_by_source():
    reg = ContextCollectorRegistry()
    reg.register(MockCollector("browser"))
    result = reg.collect_by_source("browser")
    assert result is not None
    assert result.get("data") == "collected from browser"

def test_registry_unknown_source():
    reg = ContextCollectorRegistry()
    result = reg.collect_by_source("unknown")
    assert result is None