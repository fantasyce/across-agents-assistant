# Across Agents Assistant - 技术架构设计文档

## 1. 架构概览
本项目在 MVP 阶段进行重大架构调整。为实现最佳的 macOS 原生体验和极低的资源消耗，UI 层由原先的跨平台方案迁移至 **SwiftUI**。核心业务逻辑（Agent 控制、大模型交互、本地工具执行）推荐以 Swift 为主导的架构，或在初期采用 Swift + Python 后端（通过本地通信）的混合架构。

## 2. 核心技术栈
- **UI 框架**: SwiftUI (macOS 13.0+)
- **系统集成**: AppKit (用于 Menu Bar 驻留、全局快捷键注册等)
- **大模型通信**: Swift 原生网络库 (URLSession) 或基于 Python 的微服务。
- **数据存储**: UserDefaults / SQLite (用于本地配置和历史记录)。

## 3. 核心模块设计

### 3.1 唤醒与事件模块
- 取消原有的连续语音监听（唤醒词）模块，彻底移除相关的音频流处理后台任务。
- 引入全局快捷键监听器（如使用 `NSEvent.addGlobalMonitorForEvents` 或第三方库）。
- Menu Bar Controller 管理状态栏图标及其生命周期。

### 3.2 Agent 控制引擎 (受控半自动模式)
- **状态机设计**：Agent 处于 `Idle` -> `Thinking` -> `WaitingForApproval` -> `Executing` -> `Idle` 的状态流转。
- **工具调用拦截器 (Tool Call Interceptor)**：
  - 接收到大模型的工具调用请求后，首先经过“白名单过滤器 (Whitelist Filter)”。
  - 拦截器判断该工具是否属于高风险操作。如果属于，将 Agent 状态置为 `WaitingForApproval` 并通过 SwiftUI 触发授权 UI。
  - 用户确认后，将状态推进至 `Executing`；用户拒绝则返回中断信号给大模型。

### 3.3 渐进式上下文引擎 (Staged Context Engine)
- **基础上下文接口**（快速、低延迟）：获取活动窗口名、系统时间等。
- **深度上下文接口**（按需调用）：利用 AppleScript 抓取 Xcode/VSCode/Cursor 的当前文件内容和行号；或利用 Accessibility API 抓取选中文本。
- **上下文数据组装器**：在发送给大模型的 Prompt 中，明确区分不同阶段获取的上下文，避免上下文窗口被无关信息填满。

### 3.4 工具执行沙盒 (Tool Execution Sandbox)
- **白名单配置**：以 JSON 格式硬编码或配置在应用内部，定义允许的工具包和命令前缀（如 `["cat", "ls", "git"]`）。
- **命令解析器**：在执行前验证命令是否符合白名单模式，严防命令注入。

## 4. 迁移计划 (向 SwiftUI 演进)
1. **项目初始化**：创建新的 macOS SwiftUI App 工程。
2. **UI 原型开发**：使用 SwiftUI 重构主聊天窗口、Menu Bar 弹出框和设置页面。
3. **快捷键与 Menu Bar 接入**：实现快捷键唤醒和状态栏点击交互。
4. **核心逻辑重构/对接**：
   - 考虑到 MVP 快速迭代，可先将现有的 Python 核心打包为本地后台服务，SwiftUI 作为前端与之通信。
   - 长期目标是逐步用 Swift 重写核心对话和工具调用逻辑。
5. **权限与白名单实施**：在执行层加入严格的白名单和审批流拦截。

## 5. 安全与性能考量
- **安全**：沙盒机制、权限请求（Accessibility、文件系统读取）需在 Info.plist 中明确声明，并通过 macOS 系统的 TCC 机制引导用户授权。
- **性能**：放弃全局唤醒词和重量级 Web 容器后，预期内存占用大幅下降，CPU 后台常驻占用接近 0%。