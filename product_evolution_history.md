# 产品演进历史 (Product Evolution History)

## 概述
本文档记录了项目在探索过程中的各类产品转型方向、优缺点分析，以及未来可能的发展路径。

## 探讨过的产品方向与转型 (Discussed Pivot Directions)

### 1. 基础命令行 AI 助手 (Basic CLI AI Assistant)
- **说明**: 纯文本界面的命令行工具，通过输入指令触发 LLM 完成简单的脚本生成或问答。
- **优点 (Pros)**: 
  - 开发成本极低，易于快速验证核心 LLM 能力。
  - 适合极客和开发者群体。
- **缺点 (Cons)**: 
  - 用户体验单一，缺乏交互性。
  - 无法获取足够的系统级上下文，功能受限。
  - 难以吸引非技术用户。

### 2. 基于 Web 的跨平台 AI 代理 (Web-based Cross-platform AI Agent)
- **说明**: 构建一个跨平台的 Web 应用程序，用户可以通过浏览器界面与 AI 代理交互。
- **优点 (Pros)**:
  - 跨平台兼容性好（Windows/macOS/Linux均可使用）。
  - UI 表现力强，适合复杂的数据可视化和多模态交互。
- **缺点 (Cons)**:
  - 难以深度集成到操作系统底层（如直接读取本地文件、控制本地应用等）。
  - 权限获取困难，作为“本地助手”的体验不够无缝。

### 3. macOS 本地原生系统级助手 (macOS Native System-level Assistant)
- **说明**: 深度集成于 macOS 的原生应用，具备全局快捷键、系统级权限获取能力。
- **优点 (Pros)**:
  - 极致的用户体验，响应迅速。
  - 能够深度获取系统上下文（当前活动窗口、屏幕内容、剪贴板等）。
- **缺点 (Cons)**:
  - 平台绑定严重，无法直接复用到 Windows。
  - 需要处理复杂的 macOS 权限和原生开发技术栈。

## 确定的 MVP 方向：macOS 语音触发代理执行器 (Chosen MVP)
综合评估后，我们决定聚焦于 **macOS 语音触发代理执行器，附带上下文打包与审批界面 (macOS Voice-triggered Agent Executer with Context Pack & Approval UI)**。
详细架构与计划请参见 `mvp_architecture_and_plan.md`。

## 未来可能性 (Future Possibilities)

### 1. Siri 深度集成 (Siri Integration)
- **概念**: 利用 Apple 的 App Intents 或 Shortcuts 机制，将我们的 Agent 能力直接接入 Siri。
- **价值**: 用户可以直接通过 "Hey Siri, let the agent do..." 来唤起复杂的自动化工作流，实现真正的无感交互。

### 2. 复杂多智能体编排器 (Complex Multi-agent Orchestrators)
- **概念**: 从单一的 Agent 演进为一个平台，能够调度多个垂直领域的专业 Agent（例如：代码 Agent、设计 Agent、数据分析 Agent）协同工作。
- **价值**: 解决单一 LLM 能力瓶颈，通过角色分工和多轮辩论/协作，完成超大规模的复杂任务。