# backend/src/across_agents_assistant/context/collectors/screen.py
import subprocess
import os
import tempfile
from typing import Dict, Any, Optional

try:
    import Foundation
    import Vision
    import AppKit
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

from ..base import ContextCollector

class ScreenContext(ContextCollector):
    """屏幕上下文采集器 (截图/OCR)"""

    @property
    def source_name(self) -> str:
        return "screen"

    def is_available(self) -> bool:
        return VISION_AVAILABLE

    def collect(self) -> Dict[str, Any]:
        """采集屏幕截图和 OCR 结果"""
        screenshot = self._capture_screen()
        if not screenshot:
            return {"error": "截图失败"}

        ocr_text = self._perform_ocr(screenshot)
        return {
            "screenshot_available": True,
            "ocr_text": ocr_text,
            "ocr_available": VISION_AVAILABLE
        }

    def _capture_screen(self) -> Optional[bytes]:
        """截取屏幕"""
        try:
            # 使用 screencapture 命令
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                temp_path = f.name

            result = subprocess.run(
                ['screencapture', '-x', temp_path],
                capture_output=True,
                timeout=5
            )

            if result.returncode != 0:
                return None

            with open(temp_path, 'rb') as f:
                image_data = f.read()

            os.unlink(temp_path)
            return image_data
        except Exception:
            return None

    def _perform_ocr(self, image_data: bytes) -> str:
        """使用 Vision 框架进行 OCR"""
        if not VISION_AVAILABLE:
            return "[OCR 不可用]"

        try:
            # 从 image_data 创建 NSImage
            image = AppKit.NSImage.alloc().initWithData_(image_data)
            if not image:
                return "[无法解析图像]"

            # 转换为 CGImage
            rep = image.representations()[0]
            cg_image = rep.CGImage()

            # 创建 OCR 请求
            request = Vision.VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(Vision.kVNRecognitionLevelAccurate)

            # 执行请求
            handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
                cg_image, {}
            )
            handler.performRequests_error_([request], None)

            # 提取结果
            observations = request.results()
            if not observations:
                return "[未识别到文本]"

            text_parts = []
            for observation in observations:
                text_parts.append(observation.text())

            return '\n'.join(text_parts)
        except Exception as e:
            return f"[OCR 错误: {str(e)}]"

    def capture_window(self, window_id: int) -> Optional[bytes]:
        """截取指定窗口"""
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                temp_path = f.name

            result = subprocess.run(
                ['screencapture', '-x', '-w', str(window_id), temp_path],
                capture_output=True,
                timeout=5
            )

            if result.returncode != 0:
                return None

            with open(temp_path, 'rb') as f:
                return f.read()
        except Exception:
            return None