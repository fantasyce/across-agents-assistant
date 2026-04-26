# backend/tests/context/test_browser.py
import pytest
from unittest.mock import patch, MagicMock
from across_agents_assistant.context.collectors.browser import BrowserContext, ChromeContext, SafariContext

def test_chrome_context_source_name():
    ctx = ChromeContext()
    assert ctx.source_name == "browser_chrome"

def test_safari_context_source_name():
    ctx = SafariContext()
    assert ctx.source_name == "browser_safari"

def test_browser_context_not_available():
    ctx = BrowserContext("NonExistent")
    assert ctx.is_available() == False

@patch('subprocess.run')
def test_browser_context_collect(mock_run):
    mock_run.return_value = MagicMock(stdout="https://example.com", strip=lambda: "https://example.com")
    ctx = ChromeContext()
    result = ctx.collect()
    assert "url" in result
    assert "title" in result