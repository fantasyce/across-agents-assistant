# backend/src/across_agents_assistant/context/__init__.py
from .base import ContextCollector
from .registry import ContextCollectorRegistry, registry
from .collectors.system import SystemContext
from .collectors.browser import ChromeContext, SafariContext
from .collectors.finder import FinderContext
from .collectors.ide import XcodeContext, VSCodeContext
from .collectors.screen import ScreenContext

# 注册所有采集器
def register_all_collectors():
    """注册所有内置采集器"""
    registry.register(SystemContext())
    registry.register(ChromeContext())
    registry.register(SafariContext())
    registry.register(FinderContext())
    registry.register(XcodeContext())
    registry.register(VSCodeContext())
    registry.register(ScreenContext())

# 自动注册
register_all_collectors()

__all__ = [
    'ContextCollector',
    'ContextCollectorRegistry',
    'registry',
    'SystemContext',
    'ChromeContext',
    'SafariContext',
    'FinderContext',
    'XcodeContext',
    'VSCodeContext',
    'ScreenContext',
    'register_all_collectors',
]
