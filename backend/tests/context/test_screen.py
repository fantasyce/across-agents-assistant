# backend/tests/context/test_screen.py
import pytest
from across_agents_assistant.context.collectors.screen import ScreenContext

def test_screen_context_source_name():
    ctx = ScreenContext()
    assert ctx.source_name == "screen"

def test_screen_context_is_available():
    ctx = ScreenContext()
    # 取决于 Vision 框架是否可用
    assert isinstance(ctx.is_available(), bool)