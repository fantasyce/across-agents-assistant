import subprocess
from typing import Dict

class PermissionChecker:
    """macOS 权限检查器"""

    @staticmethod
    def check_accessibility() -> bool:
        """检查辅助功能权限"""
        try:
            result = subprocess.run(
                ['system_profiler', 'SPAccessibilityDataType'],
                capture_output=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def check_screen_recording() -> bool:
        """检查屏幕录制权限"""
        try:
            result = subprocess.run(
                ['screencapture', '-x', '/dev/null'],
                capture_output=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def check_microphone() -> bool:
        """检查麦克风权限"""
        try:
            result = subprocess.run(
                ['system_profiler', 'SPMicrophoneDataType'],
                capture_output=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def open_accessibility_settings():
        """打开辅助功能设置"""
        subprocess.run(['open', 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility'])

    @staticmethod
    def open_screen_recording_settings():
        """打开屏幕录制设置"""
        subprocess.run(['open', 'x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture'])

    @staticmethod
    def open_microphone_settings():
        """打开麦克风设置"""
        subprocess.run(['open', 'x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone'])

    @staticmethod
    def get_all_permissions_status() -> Dict[str, bool]:
        """获取所有权限状态"""
        return {
            'accessibility': PermissionChecker.check_accessibility(),
            'screen_recording': PermissionChecker.check_screen_recording(),
            'microphone': PermissionChecker.check_microphone()
        }