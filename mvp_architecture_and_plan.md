# MVP 架构与开发计划 (MVP Architecture and Plan)

## 核心定位
**macOS 语音触发代理执行器 (macOS Voice-triggered Agent Executer)**，具备强大的上下文打包能力 (Context Pack) 和用户安全审批界面 (Approval UI)。

## 1. 核心功能描述
1. **语音触发**: 用户可以通过全局快捷键或唤醒词激活，通过语音直接下达指令。
2. **上下文打包 (Context Pack)**: 在用户下达指令的瞬间，自动抓取当前屏幕状态、剪贴板内容、当前活动应用程序等系统级上下文，与用户指令一并发送给大模型。
3. **安全审批界面 (Approval UI)**: Agent 在执行任何具有破坏性或敏感操作（如删除文件、发送邮件、修改系统配置）前，必须通过 UI 弹窗向用户展示执行计划，并等待用户授权确认。

## 2. 技术架构 (Technical Architecture)

### 2.1 表现层 (Presentation Layer)
- **技术栈**: 推荐使用 Tauri + React/Vue，以兼顾系统调用能力与开发效率；或者使用 Swift / SwiftUI (原生 macOS 应用体验)。
- **组件**: 
  - 悬浮球/状态栏图标 (Status Bar Item)。
  - 语音录制与反馈界面。
  - 审批拦截弹窗 (Approval UI)。

### 2.2 逻辑层 (Logic Layer)
- **语音识别 (STT)**: 集成 Whisper API 或本地小模型进行实时语音转文本。
- **大模型引擎 (LLM Engine)**: 对接 OpenAI / Anthropic 等主流模型，负责意图理解和任务拆解。
- **上下文收集器 (Context Collector)**:
  - 屏幕截图 (Screen Capture API)。
  - 剪贴板读取 (Clipboard API)。
  - 辅助功能 API (Accessibility API) 用于获取当前活跃窗口信息。

### 2.3 执行层 (Execution Layer)
- **Agent 执行环境**: 沙盒化的脚本执行器（Python/Node.js/Shell）。
- **审批网关 (Approval Gateway)**: 拦截执行层的敏感调用，挂起进程，直到表现层返回用户的同意信号。

## 3. 技术难点与挑战 (Hurdles & Challenges)

1. **macOS 权限限制**:
   - 屏幕录制、辅助功能控制、麦克风等权限需要用户手动在“系统偏好设置”中开启，新用户引导体验较重。
2. **上下文抓取的性能与隐私**:
   - 抓取屏幕和解析上下文需要在毫秒级完成，否则会产生明显的交互延迟。
   - 需要确保敏感信息（如密码输入框）在发送给 LLM 前被脱敏或过滤。
3. **Agent 行为边界控制**:
   - 如何精准定义哪些操作需要 Approval，哪些可以直接静默执行，是一个复杂的策略问题。

## 4. 阶段性开发计划 (Phased Development Plan)

### Phase 1: 核心基础链路验证 (Weeks 1-2)
- 搭建基础的 macOS App 框架（状态栏应用）。
- 实现全局快捷键唤醒录音，并集成 STT（语音转文本）。
- 实现最基础的文本指令发送至 LLM 并获取回复。

### Phase 2: 上下文打包器 (Weeks 3-4)
- 开发 Context Collector 模块。
- 实现获取当前活跃窗口名称、选中文本、剪贴板内容。
- 探索轻量级屏幕截图与 OCR 结合，将其打包为 Prompt 附件。

### Phase 3: 审批界面与执行器 (Weeks 5-6)
- 构建 Agent 本地脚本执行能力（如执行简单的 Shell 命令）。
- 开发 Approval Gateway，设计并实现拦截机制。
- 完成 Approval UI 弹窗，实现“拦截 -> 展示 -> 确认/拒绝 -> 继续执行”的闭环。

### Phase 4: 打磨与内测 (Weeks 7-8)
- 优化语音交互体验（如加入语音合成 TTS 反馈）。
- 完善权限请求引导流程。
- 邀请种子用户进行内测，收集 Agent 执行准确率和 Approval 体验反馈。