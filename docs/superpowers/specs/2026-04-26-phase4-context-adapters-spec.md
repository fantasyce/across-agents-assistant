# Phase 4: 应用适配与可选视觉上下文 - 设计规格

## 1. 概述

**目标：** 提升上下文质量和场景覆盖，支持从多种应用读取上下文，并为未来截图 OCR 能力预留架构。

**架构位置：** Phase 4 扩展现有 context collectors，添加新的应用适配器。

## 2. 现有能力

根据 `Context_Pack_and_Tool_Protocol.md`：

**Tier 1 上下文 (已实现):**
- 前台应用 (frontmost_app)
- 窗口标题 (window_title)
- 剪贴板 (clipboard)
- 时间 (timestamp)
- 语言环境 (locale)

**Tier 2 上下文 (已实现):**
- 浏览器 URL (browser_url)
- Finder 上下文 (finder_context)
- Xcode 文件 (xcode_file)

## 3. 新增能力

### 3.1 截图 OCR (Tier 3 视觉上下文)

```python
class ScreenCaptureTool:
    """截图工具"""
    def capture_screen(self, region: Optional[str] = None) -> bytes:
        """截取屏幕指定区域，返回 PNG 字节"""

    def capture_window(self, window_id: int) -> bytes:
        """截取指定窗口"""

class OCRTool:
    """OCR 工具"""
    def extract_text(self, image_bytes: bytes) -> str:
        """从截图提取文本"""
```

### 3.2 Finder 适配增强

**已有能力:**
- 获取当前目录路径
- 获取选中文件列表

**新增能力:**
- 获取文件内容预览（文本文件）
- 获取文件元数据（大小、修改时间）
- 支持多选文件批量处理

```python
class FinderAdapter:
    def get_selection_content(self, max_size_kb: int = 100) -> List[str]:
        """获取选中文件的内容预览"""

    def get_file_metadata(self, path: str) -> Dict[str, Any]:
        """获取文件元数据"""
```

### 3.3 浏览器适配增强

**已有能力:**
- 获取当前 URL 和标题

**新增能力:**
- 获取页面主要内容（文本提取）
- 获取页面结构化信息

```python
class BrowserAdapter:
    def get_page_content(self) -> str:
        """获取页面主要内容（去除导航/广告）"""

    def get_selected_text(self) -> Optional[str]:
        """获取页面中选中的文本"""
```

### 3.4 IDE 适配增强

**已有能力:**
- 获取 Xcode 当前打开文件路径

**新增能力:**
- 获取当前文件内容
- 获取选中代码片段
- 支持更多 IDE (VSCode, JetBrains)

```python
class IDEAdapter:
    def get_current_file_content(self, max_lines: int = 500) -> Optional[str]:
        """获取当前文件内容"""

    def get_selected_code(self) -> Optional[str]:
        """获取选中的代码片段"""

    def get_diagnostics(self) -> List[Dict[str, Any]]:
        """获取当前文件的诊断信息（错误/警告）"""
```

## 4. 架构设计

### 4.1 ContextCollector 统一接口

```python
from abc import ABC, abstractmethod

class ContextCollector(ABC):
    """上下文采集器基类"""
    @property
    @abstractmethod
    def source_name(self) -> str:
        """数据来源名称"""
        pass

    @abstractmethod
    def collect(self) -> Dict[str, Any]:
        """采集上下文"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查是否可用"""
        pass
```

### 4.2 采集器注册表

```python
class ContextCollectorRegistry:
    def __init__(self):
        self._collectors: Dict[str, ContextCollector] = {}

    def register(self, collector: ContextCollector):
        """注册采集器"""

    def collect_all(self) -> Dict[str, Any]:
        """采集所有可用上下文"""

    def collect_by_source(self, source_name: str) -> Dict[str, Any]:
        """采集指定来源上下文"""
```

### 4.3 现有采集器集成

Tier 1 采集器将作为内置采集器注册到系统中。

## 5. 文件结构

```
backend/src/across_agents_assistant/
├── context/
│   ├── __init__.py
│   ├── base.py              # ContextCollector ABC
│   ├── registry.py          # ContextCollectorRegistry
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── system.py        # SystemContext (Tier 1)
│   │   ├── browser.py        # BrowserContext (Chrome/Safari)
│   │   ├── finder.py        # FinderContext (增强)
│   │   ├── ide.py           # IDEContext (Xcode/VSCode)
│   │   └── screen.py        # ScreenContext (截图/OCR)
│   └── tests/
│       ├── __init__.py
│       ├── test_registry.py
│       ├── test_browser.py
│       ├── test_finder.py
│       ├── test_ide.py
│       └── test_screen.py
```

## 6. API 设计

### 6.1 上下文采集 API

```python
# 采集所有可用上下文
GET /api/v1/context

# 采集指定来源
GET /api/v1/context/{source_name}

# 检查采集器状态
GET /api/v1/context/status

# 可用的采集器
GET /api/v1/context/collectors
```

### 6.2 响应格式

```json
{
  "timestamp": "2026-04-26T12:00:00Z",
  "sources": {
    "system": {
      "frontmost_app": "Xcode",
      "window_title": "main.py - AcrossAgents",
      "clipboard": "...",
      "locale": "zh_CN"
    },
    "browser": {
      "url": "https://github.com/...",
      "title": "Repository | GitHub",
      "content_preview": "..."
    },
    "finder": {
      "current_directory": "/Users/.../Documents",
      "selected_files": ["file1.txt", "file2.md"],
      "file_previews": {...}
    },
    "ide": {
      "current_file": "/path/to/file.py",
      "file_content": "...",
      "selected_code": "...",
      "diagnostics": []
    }
  }
}
```

## 7. OCR 实现

### 7.1 技术方案

使用 macOS Vision 框架进行 OCR：

```python
import Vision
import AppKit

def perform_ocr(image_data: bytes) -> str:
    """使用 Vision 框架提取文本"""
    # 1. 从 image_data 创建 NSImage
    # 2. 创建 VNRecognizeTextRequest
    # 3. 执行请求
    # 4. 提取文本结果
```

### 7.2 文本处理

- 移除导航栏、页眉、页脚等非主要内容
- 保留代码块和段落结构
- 限制单次提取的最大字符数

## 8. 权限处理

### 8.1 权限列表

| 能力 | 权限 | 获取时机 |
|------|------|----------|
| 屏幕录制 | Screen Recording | 首次截图时 |
| OCR | 无特殊权限 | 使用 Vision 框架 |
| Accessibility | Accessibility | 首次获取窗口信息时 |
| AppleScript | Automation | 首次执行浏览器/Finder 脚本时 |

### 8.2 降级策略

| 权限缺失 | 降级行为 |
|----------|----------|
| Screen Recording | 返回错误提示，询问用户授权 |
| Accessibility | 仅返回基本信息，无详细窗口内容 |
| Automation | 提示用户手动授权特定应用 |

## 9. 验收标准

| ID | 标准 | 验证方式 | 状态 |
|----|------|----------|------|
| P4-1 | system context 采集正常 | 单元测试 | ✅ |
| P4-2 | browser context 支持 Chrome/Safari | 单元测试 | ✅ |
| P4-3 | finder context 支持文件预览 | 单元测试 | ✅ |
| P4-4 | IDE context 支持 Xcode/VSCode | 单元测试 | ✅ |
| P4-5 | screen context 支持截图/OCR | 单元测试 | ✅ |
| P4-6 | 所有采集器注册到全局注册表 | 导入测试 | ✅ |

## 10. 已实现的采集器

| 采集器 | source_name | 说明 |
|--------|-------------|------|
| SystemContext | system | Tier 1 系统上下文 |
| ChromeContext | browser_chrome | Chrome 浏览器 |
| SafariContext | browser_safari | Safari 浏览器 |
| FinderContext | finder | Finder 文件管理器 |
| XcodeContext | ide_xcode | Xcode IDE |
| VSCodeContext | ide_vscode | Visual Studio Code |
| ScreenContext | screen | 截图/OCR |

## 10. 技术限制

- Phase 4 暂不实现截图自动触发（由用户手动触发）
- OCR 精度受截图质量和语言影响
- AppleScript 在无障碍权限缺失时可能失败
- 部分 IDE 可能不支持自动化接口