# backend/src/across_agents_assistant/context/collectors/ide.py
import subprocess
import os
from typing import Dict, Any, Optional, List

from ..base import ContextCollector

class IDEContext(ContextCollector):
    """IDE 上下文采集器基类"""

    @property
    def source_name(self) -> str:
        return "ide"

    def is_available(self) -> bool:
        return self._check_app()

    def _check_app(self) -> bool:
        """检查 IDE 是否运行"""
        try:
            script = f'tell application "{self._app_name()}" to return name'
            subprocess.run(['osascript', '-e', script], capture_output=True, timeout=2)
            return True
        except Exception:
            return False

    def _app_name(self) -> str:
        raise NotImplementedError

    def collect(self) -> Dict[str, Any]:
        raise NotImplementedError


class XcodeContext(IDEContext):
    """Xcode 上下文"""

    def _app_name(self) -> str:
        return "Xcode"

    @property
    def source_name(self) -> str:
        return "ide_xcode"

    def collect(self) -> Dict[str, Any]:
        return {
            "current_file": self._get_current_file(),
            "file_content": self._get_file_content(),
            "selected_code": self._get_selected_code()
        }

    def _get_current_file(self) -> str:
        """获取当前文件路径"""
        try:
            script = '''
            tell application "Xcode"
                if (count of documents) > 0 then
                    return path of document 1
                else
                    return ""
                end if
            end tell
            '''
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=2)
            return result.stdout.strip()
        except Exception:
            return ""

    def _get_file_content(self, max_lines: int = 500) -> str:
        """获取当前文件内容"""
        file_path = self._get_current_file()
        if not file_path or not os.path.exists(file_path):
            return ""
        try:
            with open(file_path, 'r', errors='ignore') as f:
                lines = [next(f) for _ in range(max_lines)]
                return ''.join(lines)
        except Exception:
            return ""

    def _get_selected_code(self) -> str:
        """获取选中的代码"""
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


class VSCodeContext(IDEContext):
    """VSCode 上下文"""

    def _app_name(self) -> str:
        return "Visual Studio Code"

    @property
    def source_name(self) -> str:
        return "ide_vscode"

    def collect(self) -> Dict[str, Any]:
        return {
            "current_file": self._get_current_file(),
            "file_content": self._get_file_content()
        }

    def _get_current_file(self) -> str:
        """通过 AppleScript 获取 VSCode 当前文件"""
        try:
            script = '''
            tell application "Visual Studio Code"
                if active document exists then
                    return URI of active document
                else
                    return ""
                end if
            end tell
            '''
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=2)
            uri = result.stdout.strip()
            if uri.startswith("file://"):
                return uri.replace("file://", "")
            return uri
        except Exception:
            return ""

    def _get_file_content(self, max_lines: int = 500) -> str:
        """获取当前文件内容"""
        file_path = self._get_current_file()
        if not file_path or not os.path.exists(file_path):
            return ""
        try:
            with open(file_path, 'r', errors='ignore') as f:
                lines = [next(f) for _ in range(max_lines)]
                return ''.join(lines)
        except Exception:
            return ""
