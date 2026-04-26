# backend/src/across_agents_assistant/context/collectors/system.py
import subprocess
import datetime
import locale
from typing import Dict, Any

from ..base import ContextCollector

class SystemContext(ContextCollector):
    """系统上下文采集器 (Tier 1)"""

    @property
    def source_name(self) -> str:
        return "system"

    def is_available(self) -> bool:
        return True

    def collect(self) -> Dict[str, Any]:
        return {
            "frontmost_app": self._get_frontmost_app(),
            "window_title": self._get_window_title(),
            "clipboard": self._get_clipboard(),
            "timestamp": datetime.datetime.now().isoformat(),
            "locale": self._get_locale()
        }

    def _get_frontmost_app(self) -> str:
        """获取前台应用"""
        try:
            script = 'tell application "System Events" to get name of first process whose frontmost is true'
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=2)
            return result.stdout.strip() or "Unknown"
        except Exception:
            return "Unknown"

    def _get_window_title(self) -> str:
        """获取窗口标题"""
        try:
            script = '''
            tell application "System Events"
                tell (first process whose frontmost is true)
                    if window 1 exists then
                        return name of window 1
                    end if
                end tell
            end tell
            '''
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=2)
            return result.stdout.strip() or ""
        except Exception:
            return ""

    def _get_clipboard(self) -> str:
        """获取剪贴板内容"""
        try:
            result = subprocess.run(['pbpaste'], capture_output=True, text=True, timeout=1)
            return result.stdout.strip()[:1000]  # 限制长度
        except Exception:
            return ""

    def _get_locale(self) -> str:
        """获取语言环境"""
        try:
            return locale.getlocale()[0] or "en_US"
        except Exception:
            return "en_US"