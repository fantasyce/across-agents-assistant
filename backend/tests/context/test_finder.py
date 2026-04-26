# backend/tests/context/test_finder.py
import pytest
from unittest.mock import patch, MagicMock
from across_agents_assistant.context.collectors.finder import FinderContext

def test_finder_context_source_name():
    ctx = FinderContext()
    assert ctx.source_name == "finder"

def test_finder_context_is_available():
    ctx = FinderContext()
    # 取决于当前环境
    assert isinstance(ctx.is_available(), bool)

@patch('subprocess.run')
def test_finder_context_collect(mock_run):
    mock_run.return_value = MagicMock(stdout="/Users/test", strip=lambda: "/Users/test")
    ctx = FinderContext()
    result = ctx.collect()
    assert "current_directory" in result
    assert "selected_files" in result