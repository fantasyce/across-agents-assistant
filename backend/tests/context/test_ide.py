# backend/tests/context/test_ide.py
import pytest
from across_agents_assistant.context.collectors.ide import XcodeContext, VSCodeContext

def test_xcode_context_source_name():
    ctx = XcodeContext()
    assert ctx.source_name == "ide_xcode"

def test_vscode_context_source_name():
    ctx = VSCodeContext()
    assert ctx.source_name == "ide_vscode"

def test_ide_context_is_available():
    # 取决于环境
    ctx = XcodeContext()
    assert isinstance(ctx.is_available(), bool)
