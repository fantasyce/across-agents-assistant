# backend/tests/context/test_system.py
import pytest
from across_agents_assistant.context.collectors.system import SystemContext

def test_system_context_source_name():
    ctx = SystemContext()
    assert ctx.source_name == "system"

def test_system_context_is_available():
    ctx = SystemContext()
    assert ctx.is_available() == True

def test_system_context_collect():
    ctx = SystemContext()
    result = ctx.collect()
    assert "frontmost_app" in result
    assert "clipboard" in result
    assert "timestamp" in result
    assert "locale" in result