# backend/src/across_agents_assistant/context/collectors/finder.py
import subprocess
import os
from typing import Dict, Any, List

from ..base import ContextCollector

class FinderContext(ContextCollector):
    """Finder 上下文采集器 (增强)"""

    @property
    def source_name(self) -> str:
        return "finder"

    def is_available(self) -> bool:
        try:
            script = 'tell application "Finder" to return name'
            subprocess.run(['osascript', '-e', script], capture_output=True, timeout=2)
            return True
        except Exception:
            return False

    def collect(self) -> Dict[str, Any]:
        return {
            "current_directory": self._get_current_directory(),
            "selected_files": self._get_selected_files(),
            "file_previews": self._get_file_previews()
        }

    def _get_current_directory(self) -> str:
        """获取当前目录"""
        try:
            script = '''
            tell application "Finder"
                if exists Finder window 1 then
                    try
                        return POSIX path of (target of Finder window 1 as alias)
                    on error
                        return POSIX path of (desktop as alias)
                    end try
                else
                    return POSIX path of (desktop as alias)
                end if
            end tell
            '''
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=2)
            return result.stdout.strip()
        except Exception:
            return ""

    def _get_selected_files(self) -> List[str]:
        """获取选中文件"""
        try:
            script = '''
            tell application "Finder"
                set theSelection to selection
                if (count of theSelection) > 0 then
                    set pathList to {}
                    repeat with anItem in theSelection
                        set end of pathList to POSIX path of (anItem as text)
                    end repeat
                    return pathList as string
                else
                    return ""
                end if
            end tell
            '''
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=2)
            output = result.stdout.strip()
            if not output:
                return []
            return [p.strip() for p in output.split(',')]
        except Exception:
            return []

    def _get_file_previews(self) -> Dict[str, str]:
        """获取文件内容预览"""
        previews = {}
        for file_path in self._get_selected_files()[:5]:  # 最多5个文件
            try:
                if os.path.isfile(file_path):
                    size = os.path.getsize(file_path)
                    if size < 50000:  # 小于50KB
                        with open(file_path, 'r', errors='ignore') as f:
                            content = f.read(1000)
                            previews[file_path] = content
                    else:
                        previews[file_path] = f"[文件过大: {size} bytes]"
            except Exception:
                previews[file_path] = "[无法读取]"
        return previews