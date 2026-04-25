# Across Agents Assistant - 技术架构设计文档

## 1. 文档目标
本文档用于给出 Across Agents Assistant 在 MVP 阶段的推荐技术架构、模块边界、状态机、权限模型、风险控制和分阶段实现方案。目标是指导工程落地，而不是仅提供概念性描述。

## 2. 总体架构判断
### 2.1 推荐架构路线
MVP 推荐采用 **SwiftUI + AppKit 的原生 macOS 应用** 作为前端和系统能力入口，并以以下两种方式之一承载 Agent 核心逻辑：

- **方案 A：Swift 主导**
  - UI、系统能力、上下文采集、Agent 编排、工具执行均由 Swift 实现。
  - 优点是原生整合最强，部署简单。
  - 缺点是初期迭代速度略慢，LLM 生态和已有 Python 代码复用较弱。

- **方案 B：Swift + Python 混合**
  - SwiftUI 负责 UI、权限和系统集成。
  - Python 负责模型调用、工具编排、部分已有能力复用。
  - 两者通过本地 HTTP、Unix Domain Socket 或 stdin/stdout RPC 通信。
  - 优点是便于快速复用已有代码。
  - 缺点是多进程管理、打包和调试更复杂。

### 2.2 MVP 推荐决策
考虑到代码实现现状，MVP 采用 **Python FastAPI 后端 + Swift macOS 客户端** 的分离架构：

- **Python 后端** (`backend/`)：FastAPI API Server，运行在 `127.0.0.1:8000`。负责 Agent 编排、工具执行、数据库管理、MCP 集成。
- **Swift 客户端** (`macOS-Client/`): 独立的 macOS menu bar 应用，通过 HTTP 与后端通信。
- 两者通过本地 HTTP API 通信，不是同一个进程。

核心模块位于 `backend/src/across_agents_assistant/`:
- `api_server.py` - FastAPI HTTP Server（核心入口）
- `app.py` - 独立 Python 应用（包含 TTS、语音处理）
- `agent_manager.py` - Agent 配置管理
- `openclaw/client.py` - OpenClaw Agent 客户端
- `tools/builtin_tools.py` - 内置工具注册
- `tools/mcp_client.py` - MCP 客户端
- `db/database.py` - SQLite 数据库管理

## 3. 核心设计原则
- **受控执行优先**：先保证可解释和可审批，再提升自动化程度。
- **分层上下文优先**：先拿稳定低成本上下文，再按需拉取重型上下文。
- **最小权限优先**：仅在功能需要时申请 macOS 权限。
- **白名单工具优先**：不向模型暴露开放式任意脚本执行。
- **草稿优先于直接外发**：外部写入和发送操作默认要求用户确认。
- **可观测性优先**：所有任务、审批和失败路径均应留下结构化日志。

## 4. 总体架构图
```mermaid
flowchart TD
    A[User Trigger\nShortcut / Menu Bar / Text Input] --> B[UI Layer\nSwiftUI + AppKit]
    B --> C[Session Controller]
    C --> D[Context Engine]
    C --> E[LLM Orchestrator]
    C --> F[Approval Engine]
    C --> G[Tool Runner]
    C --> H[Audit Logger]

    D --> D1[Frontmost App]
    D --> D2[Window Title]
    D --> D3[Clipboard]
    D --> D4[App Adapters]
    D --> D5[Optional Screenshot + OCR]

    E --> E1[Prompt Builder]
    E --> E2[Model Client]
    E --> E3[Tool Intent Parser]

    F --> F1[Risk Classifier]
    F --> F2[Policy Rules]
    F --> F3[Approval UI]

    G --> G1[Read Tools]
    G --> G2[Draft Tools]
    G --> G3[Safe Command Wrapper]

    B --> I[Permission Guide]
    H --> J[Task History / Metrics / Errors]
```

## 5. 分层模块设计

### 5.1 UI 层 (macOS Client)
职责：
- 提供状态栏入口、主浮窗、审批弹窗、设置页面、历史页面。
- 展示录音状态、识别状态、任务执行状态和结果。

技术实现：
- `SwiftUI` + `AppKit` 混合架构。
- 菜单栏应用（Menu Bar App）。
- 通过 HTTP API 与 Python 后端通信。

### 5.2 触发与输入层
职责：
- 统一处理快捷键触发、菜单栏点击、文本输入、语音输入。

### 5.3 会话与编排层 (Python Backend)
职责：
- 管理会话生命周期和 Agent 编排。
- 串联上下文收集、模型调用、审批和执行。

实际组件：
- `api_server.py` - 处理所有 HTTP API 端点
- `app.py` - Python 应用主类，管理 TTS 和语音
- `agent_manager.py` - 管理 Agent 配置
- `openclaw/client.py` - OpenClaw Agent 客户端

### 5.4 上下文引擎
职责：
- 按层级收集上下文，统一输出结构化 `ContextPack`。

分层设计：
- **Tier 1：稳定快速**
  - 前台应用名（frontmost_app）
  - 窗口标题（window_title）
  - 剪贴板文本（clipboard_text）

- **Tier 2：应用适配**
  - IDE 当前文件路径（通过 `get_xcode_context` 工具）
  - 浏览器 URL（通过 `get_active_browser_url` 工具）
  - Finder 当前目录（通过 `get_finder_context` 工具）

- **Tier 3：重型上下文（未实现）**
  - 屏幕截图
  - OCR 文本

### 5.5 模型编排层
职责：
- 构造 Prompt，调用 LLM，解析结构化输出。

实际实现：
- `openclaw/client.py` 的 `UniversalAgentClient` 调用 LLM
- `intent_parser.py` 的 `ToolIntentParser` 解析 LLM 输出的 JSON
- **注意**：LLM 输出的是 JSON 格式的 markdown 代码块（` ```json ... ``` `），而非原生 tool calling

### 5.6 审批引擎
职责：
- 根据规则和工具意图判断风险等级，决定是否展示审批 UI。

实际实现：
- 内置于 `api_server.py` 的 `/api/approve` 端点
- 风险等级使用 `”low”` / `”medium”` 字符串（而非 L0/L1/L2/L3）

### 5.7 工具执行层
职责：
- 承载所有可执行动作，统一校验参数、权限和范围。

实际实现：
- `tools/builtin_tools.py` 中的 `registry` 管理所有内置工具
- `tools/mcp_client.py` 管理 MCP 服务器和工具

### 5.8 审计与存储层
职责：
- 记录任务历史、审批日志、错误信息。

实际实现：
- `db/database.py` 中的 `DatabaseManager` 管理 SQLite 数据库
- 数据库位于 `~/.across_agents/assistant.db`
- 表：`sessions`, `messages`, `audit_logs`, `tool_authorizations`

## 6. 关键数据结构
### 6.1 ContextPack
```json
{
  "frontmost_app": "Google Chrome",
  "window_title": "客户方案 - Notion",
  "clipboard_text": "客户关注交付时间和价格"
}
```

实际实现只有 3 个字段（`api_server.py` 中的 `ContextPack` 类）：
- `frontmost_app`：前台应用名
- `window_title`：窗口标题
- `clipboard_text`：剪贴板文本

### 6.2 ToolDescriptor
```json
{
  "name": "create_email_draft",
  "risk_level": "medium",
  "required_permissions": ["none"],
  "input_schema": {
    "recipient": "string",
    "subject": "string",
    "body": "string"
  },
  "requires_approval": true,
  "timeout_ms": 5000
}
```

注意：实际 risk_level 使用 `"low"` / `"medium"` 字符串，而非 L0/L1/L2/L3。

### 6.3 ApprovalRequest
```json
{
  "tool_name": "create_email_draft",
  "risk_level": "medium",
  "tool_args": {
    "recipient": "example@email.com",
    "subject": "下周会议确认",
    "body": "..."
  },
  "description": "Create an email draft in the macOS Mail app."
}
```

实际实现只有 4 个字段（见 `api_server.py` 中的 `ChatResponse.approval_request`）：
- `tool_name`：工具名称
- `risk_level`：风险等级（"low" / "medium"）
- `tool_args`：工具参数（字典）
- `description`：工具描述

### 6.4 ApprovalDecision
```json
{
  "session_id": "session-001",
  "decision": "approve",
  "tool_name": "create_email_draft",
  "tool_args": {...},
  "agent_id": "openclaw"
}
```

实际实现（`api_server.py` 中的 `ApprovalDecision`）：
- `decision`：可选 "approve", "reject", "always_allow"（不是 approve_once）
- 不支持 "convert_to_draft" 和 "cancel" 选项

## 7. 状态机设计
### 7.1 会话状态
实际实现使用 threading Events 管理状态，而非完整状态机。

`app.py` 中的状态管理：
- `_voice_mode_enabled`：语音模式是否启用
- `_continuous_mode`：连续对话模式是否启用
- `_hotkey_interrupt`：热键中断事件
- `_tts_interrupt`：TTS 打断事件

状态流转通过这些 Events 的 set/clear 组合实现，而非显式状态机。

### 7.2 状态机要求
- 每个状态都必须可取消。
- 任一阶段失败都必须向 UI 返回可解释错误。
- 审批等待状态必须支持超时和用户主动关闭。

注：当前实现未使用完整状态机，但基本满足上述要求。

## 8. 核心执行流程
### 8.1 标准只读任务
1. 用户触发任务。
2. 收集 Tier 1 上下文。
3. 构建 Prompt 并请求 LLM。
4. 返回回复。
5. 记录任务日志。

### 8.2 需要执行的任务
1. 用户触发任务。
2. 收集 Tier 1 上下文。
3. LLM 输出计划和工具意图。
4. 审批引擎进行风险评估。
5. 若需审批则展示审批 UI。
6. 用户同意后执行工具。
7. 汇总结果并展示。
8. 写入审计日志。

### 8.3 权限缺失任务
1. 模块调用系统能力前检查权限。
2. 若权限缺失，则返回结构化错误码。
3. UI 展示权限引导，不应直接崩溃或静默失败。

## 9. 工具系统设计
### 9.1 工具分类
- **读取类工具**
  - `get_frontmost_app`
  - `get_window_title`
  - `read_clipboard`
  - `read_project_file`
  - `list_directory`
  - `get_git_status`

- **草稿类工具**
  - `create_email_draft`
  - `create_note_draft`
  - `write_workspace_file`

- **外部动作类工具**
  - `open_url`
  - `reveal_in_finder`

### 9.2 工具接入规范
每个工具必须声明：
- 名称和版本
- 输入输出 schema
- 所需权限
- 风险等级
- 默认是否审批
- 超时
- 可访问路径或资源范围

### 9.3 Safe Command Wrapper
如果确实需要命令行能力，建议仅通过 `safe_command` 包装器开放极少数命令：
- 白名单命令，例如 `git status`、`git diff --stat`、`ls`。
- 固定工作目录范围。
- 禁止管道、重定向、子命令拼接。
- 限制执行时间、输出大小和环境变量。

MVP 结论：
- 不直接暴露原始 Shell。
- `safe_command` 也应视为高风险边界能力。

## 10. 上下文采集实现建议
### 10.1 通用能力
- 前台应用：通过 `NSWorkspace` 获取。
- 窗口标题：通过 Accessibility API 获取。
- 剪贴板：通过 `NSPasteboard` 获取。

### 10.2 应用适配器
- 浏览器适配器：优先通过 AppleScript 获取 URL 和标签标题。
- Finder 适配器：获取当前目录或选中文件。
- IDE 适配器：优先通过官方能力或 AppleScript 获取当前文件路径；其次尝试 Accessibility。

### 10.3 不稳定点与替代方案
- 选中文本获取不应作为所有 App 的强依赖。
- 当无法获取选中文本时，应提示用户“可先复制到剪贴板后再试”。
- 截图与 OCR 仅在用户显式启用或任务确有必要时执行。

## 11. 权限模型
### 11.1 可能涉及的权限
- 麦克风
- Accessibility
- 屏幕录制

### 11.2 权限申请原则
- 首次启动不一次性申请全部权限。
- 在具体功能触发前给出理由说明，再请求对应权限。
- 权限被拒绝后提供手动开启引导和功能降级路径。

## 12. 安全设计
### 12.1 风险控制
- 工具白名单
- 参数 schema 校验
- 审批网关
- 执行超时
- 范围限制
- 审计日志

### 12.2 日志要求
至少记录以下事件：
- 任务开始与结束
- 上下文来源元数据
- 模型规划结果
- 审批请求与用户决策
- 工具执行结果
- 错误类型与耗时

### 12.3 敏感数据处理
- 剪贴板和截图内容默认短时缓存。
- 历史记录优先保存摘要而非完整原文。
- 允许用户关闭敏感数据持久化。

## 13. 性能设计
### 13.1 响应策略
- 输入结束后立即显示“正在理解”。
- Tier 1 上下文必须轻量快速。
- OCR 和截图应异步化或按需触发，避免阻塞普通任务。

### 13.2 性能目标
- 快捷键到 UI 响应时间小于 100ms。
- 普通问答首屏反馈时间小于 500ms。
- 重型任务尽量在 3 到 6 秒内完成首轮可见反馈。

## 14. 不可直接落地的点与替代方案
### 14.1 通用上下文抓取
问题：
- 无法保证所有应用稳定暴露可读上下文。

替代方案：
- 用应用适配器机制替代“全应用支持”承诺。
- 优先支持浏览器、Finder、IDE、Mail、Notes。

### 14.2 通用 UI 自动化
问题：
- Accessibility 自动化容易因 UI 改版和焦点变化失效。

替代方案：
- 优先提供草稿和建议能力。
- 必要时仅支持少量明确适配的自动操作。

### 14.3 开放式脚本执行
问题：
- 审批和白名单很难完全覆盖任意脚本风险。

替代方案：
- 用受控工具系统替代任意 Shell/Python/Node 执行器。

## 15. 分阶段实施计划
### Phase 1：基础原型
- SwiftUI 状态栏应用
- 全局快捷键
- 文本输入和基础语音输入
- Tier 1 上下文
- LLM 问答

### Phase 2：审批与执行
- 工具注册中心
- 审批引擎
- 草稿型工具
- 日志与历史

### Phase 3：应用适配
- 浏览器适配器
- Finder 适配器
- IDE 适配器
- 可选截图和 OCR

### Phase 4：优化与迁移
- 评估 Python 核心是否迁移到 Swift
- 精简后台资源消耗
- 完善策略系统和用户偏好

## 16. 开发建议结论
结论如下：
- 该方案具备工程可落地性。
- MVP 的关键不是“能力上限”，而是“边界控制”和“体验一致性”。
- 只要坚持原生系统集成、受控工具、渐进式上下文和审批优先，这个项目可以进入真实开发。
- 如果回到“全局唤醒词 + 全自动脚本执行 + 通用 UI 自动化”路线，落地风险会显著升高。
