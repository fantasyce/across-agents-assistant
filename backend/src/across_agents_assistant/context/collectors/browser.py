# backend/src/across_agents_assistant/context/collectors/browser.py
import subprocess
from typing import Dict, Any, Optional

from ..base import ContextCollector

class BrowserContext(ContextCollector):
    """浏览器上下文采集器"""

    def __init__(self, browser: str = "Chrome"):
        self._browser = browser

    @property
    def source_name(self) -> str:
        return f"browser_{self._browser.lower()}"

    def is_available(self) -> bool:
        try:
            script = f'id of application "{self._browser}"'
            result = subprocess.run(['osascript', '-e', script], capture_output=True, timeout=2)
            return result.returncode == 0
        except Exception:
            return False

    def collect(self) -> Dict[str, Any]:
        return {
            "url": self._get_url(),
            "title": self._get_title(),
            "selected_text": self._get_selected_text()
        }

    def _get_url(self) -> str:
        """获取当前 URL"""
        try:
            if self._browser == "Safari":
                script = 'tell application "Safari" to return URL of front document'
            else:
                script = 'tell application "Google Chrome" to return URL of active tab of front window'
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=2)
            return result.stdout.strip()
        except Exception:
            return ""

    def _get_title(self) -> str:
        """获取页面标题"""
        try:
            if self._browser == "Safari":
                script = 'tell application "Safari" to return name of front document'
            else:
                script = 'tell application "Google Chrome" to return title of active tab of front window'
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=2)
            return result.stdout.strip()
        except Exception:
            return ""

    def _get_selected_text(self) -> str:
        """获取选中文本"""
        try:
            script = '''
            tell application "System Events"
                keystroke "c" using command down
            end tell
            delay 0.1
            '''
            subprocess.run(['osascript', '-e', script], capture_output=True, timeout=1)
            result = subprocess.run(['pbpaste'], capture_output=True, text=True, timeout=1)
            return result.stdout.strip()[:500]
        except Exception:
            return ""


class ChromeContext(BrowserContext):
    """Chrome 上下文"""
    def __init__(self):
        super().__init__("Chrome")


class SafariContext(BrowserContext):
    """Safari 上下文"""
    def __init__(self):
        super().__init__("Safari")