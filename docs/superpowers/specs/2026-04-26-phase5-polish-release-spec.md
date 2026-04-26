# Phase 5: 打磨、内测与发布准备 - 设计规格

## 1. 概述

**目标：** 提升产品的商业级可用性，解决持久化和全自动推理闭环问题，并做好发布准备。

**架构位置：** Phase 5 在现有模块基础上，新增持久化和 Agent Loop 能力。

## 2. 新增能力

### 2.1 SQLite 持久化

**目标：** 实现会话历史存储、加载和高危工具调用审计。

**实现状态：** 已实现 (database.py)

#### 2.1.1 数据库 Schema

```sql
-- 会话历史表
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 消息历史表
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,  -- 'user', 'assistant', 'tool'
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- 审计日志表
CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    tool_args TEXT NOT NULL,  -- JSON string
    risk_level TEXT NOT NULL,
    decision TEXT NOT NULL,  -- 'approve', 'reject', or 'auto_approve'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- 工具授权表
CREATE TABLE tool_authorizations (
    tool_name TEXT PRIMARY KEY,
    is_always_allowed BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 2.1.2 DatabaseManager 类

```python
class DatabaseManager:
    """数据库管理器 - SQLite 连接管理"""

    def __init__(self, db_path: str = None):
        # 默认使用 ~/.across_agents/assistant.db
        self.db_path = db_path or os.path.join("~/.across_agents", "assistant.db")

    def _get_connection(self) -> sqlite3.Connection:
        """获取新连接（线程安全）"""

    def _init_db(self):
        """初始化数据库表"""

    # --- Session Management ---

    def get_or_create_session(self, session_id: str):
        """获取或创建会话"""

    def update_session_timestamp(self, session_id: str):
        """更新会话时间戳"""

    # --- Message Management ---

    def add_message(self, session_id: str, role: str, content: str):
        """添加消息"""

    def get_messages(self, session_id: str, limit: int = 50) -> List[Dict]:
        """获取会话消息"""

    # --- Audit Logs ---

    def add_audit_log(self, session_id: str, tool_name: str, tool_args: Dict,
                      risk_level: str, decision: str):
        """添加审计日志"""

    # --- Tool Authorizations ---

    def get_tool_authorization(self, tool_name: str) -> bool:
        """获取工具授权状态"""

    def set_tool_authorization(self, tool_name: str, is_always_allowed: bool):
        """设置工具授权"""

    def get_all_authorizations(self) -> List[Dict]:
        """获取所有授权"""
```

**文件位置：** `src/across_agents_assistant/db/database.py`

### 2.2 ToolPermissionStore

**目标：** 持久化存储工具授权（Always Allow）。

**实现状态：** 已实现 (集成在 DatabaseManager 中)

```python
# ToolPermissionStore 功能通过 DatabaseManager 实现

class DatabaseManager:
    # ...

    def get_tool_authorization(self, tool_name: str) -> bool:
        """检查工具是否始终允许"""

    def set_tool_authorization(self, tool_name: str, is_always_allowed: bool):
        """设置工具始终允许状态"""

    def get_all_authorizations(self) -> List[Dict[str, Any]]:
        """获取所有工具授权列表"""
```

### 2.3 Agent Loop (全自动推理循环)

**目标：** 后端实现 `while` 循环推理机制，大模型调用工具后自动回收结果并进行第二次总结。

**实现状态：** 已实现 (AgentBridge)

#### 2.3.1 架构

```
用户请求 "帮我分析代码"
         │
         ▼
┌─────────────────────────┐
│   AgentBridge.invoke()   │
│   发起 LLM 调用          │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│   LLM 返回工具调用       │
│   tools=[code_analysis]  │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│   执行工具               │
│   code_analysis()       │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│   回收结果，回传给 LLM    │
│   发起第二次总结         │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│   LLM 返回最终回答       │
└─────────────────────────┘
```

#### 2.3.2 AgentBridge 类

```python
class AgentBridge:
    """Agent Bridge 主接口"""

    def __init__(self, openclaw_client: Any):
        self._client = openclaw_client
        self._sessions: Dict[str, AgentSession] = {}

    def invoke(self, agent_id: str, message: str,
               context: Optional[Dict] = None,
               timeout: float = 120.0) -> AgentResponse:
        """调用单个 Agent"""

    def batch_invoke(self, requests: List[InvokeRequest]) -> List[AgentResponse]:
        """批量并行调用多个 Agent"""

    def is_agent_available(self, agent_id: str) -> bool:
        """检查 Agent 是否可用"""

    def shutdown(self) -> None:
        """关闭所有 Agent 会话"""
```

**文件位置：** `src/across_agents_assistant/agent_bridge/bridge.py`

### 2.4 TCC 权限引导

**目标：** 原生前置探测 macOS 辅助功能权限，提供优雅的 UI 警告和一键跳转"系统设置"。

**实现状态：** 已实现 (集成在 ApprovalService 中)

#### 2.4.1 ApprovalService 权限检查

```python
class ApprovalService:
    """审批服务，管理待审批队列和审批操作"""

    def __init__(self):
        self._pending_requests: Dict[str, ApprovalRequest] = {}
        self._always_allowed_tools: Set[str] = set()
        self._approval_callbacks: List[Callable] = []

    def is_auto_approved(self, tool_name: str) -> bool:
        """检查工具是否自动批准"""
        return tool_name in self._always_allowed_tools

    def always_allow(self, request_id: str) -> bool:
        """始终允许该工具"""
        # 添加到 _always_allowed_tools 集合

    def get_always_allowed_tools(self) -> Set[str]:
        """获取始终允许的工具列表"""

    def remove_always_allow(self, tool_name: str) -> bool:
        """从始终允许列表移除"""
```

#### 2.4.2 PermissionGuider UI

权限引导 UI 需要在应用层实现，提供：
- 权限状态仪表盘
- 缺失权限的警告
- 一键跳转设置链接

**文件位置：** `src/across_agents_assistant/approval/service.py`

## 3. 文件结构

```
backend/src/across_agents_assistant/
├── db/
│   ├── __init__.py
│   └── database.py       # DatabaseManager (SQLite 连接管理)
├── approval/
│   ├── __init__.py
│   ├── models.py         # 数据模型 (RiskLevel, ApprovalStatus, ApprovalRequest)
│   ├── service.py        # ApprovalService (审批服务和权限管理)
│   └── executor.py       # 审批执行器
├── agent_bridge/
│   ├── __init__.py
│   ├── protocol.py      # 通信协议 (AgentResponse, InvokeRequest, MessageType)
│   ├── agent.py         # AgentSession (Agent 会话管理)
│   ├── bridge.py        # AgentBridge (主接口)
│   ├── result.py        # TaskResult, SubtaskResult, ResultStatus
│   └── errors.py        # AgentException, AgentError
├── llm_gateway/
│   ├── __init__.py
│   ├── gateway.py       # LLMGateway (统一网关)
│   ├── config.py        # 配置
│   ├── base_adapter.py  # 基础适配器
│   ├── bailian_adapter.py
│   ├── deepseek_adapter.py
│   └── minimax_adapter.py
└── ... (其他现有模块)
```

## 4. API 设计

### 4.1 会话 API

```python
# 创建会话
POST /api/v1/sessions
Body: {"title": "分析代码", "metadata": {}}
Response: {"session_id": "..."}

# 获取会话
GET /api/v1/sessions/{session_id}
Response: {"id": "...", "title": "...", "created_at": "...", "messages": [...]}

# 列出会话
GET /api/v1/sessions?limit=50
Response: {"sessions": [...]}

# 添加消息
POST /api/v1/sessions/{session_id}/messages
Body: {"role": "user", "content": "..."}
Response: {"message_id": "..."}

# 删除会话
DELETE /api/v1/sessions/{session_id}
```

### 4.2 审计 API

```python
# 查询审计日志
GET /api/v1/audit/logs?event_type=tool_call&start_time=2026-04-01
Response: {"logs": [...]}

# 获取工具权限状态
GET /api/v1/permissions/tools
Response: {"tools": [{"name": "...", "permission": "always_allow/ask"}]}

# 设置工具权限
PUT /api/v1/permissions/tools/{tool_name}
Body: {"permission": "always_allow"}
```

### 4.3 Agent Loop API

```python
# 执行 Agent Loop
POST /api/v1/agent/loop
Body: {"message": "帮我分析代码", "context": {}, "max_iterations": 5}
Response: {"final_answer": "...", "iterations": 2, "tool_calls": [...]}
```

### 4.4 权限检查 API

```python
# 检查权限状态
GET /api/v1/permissions/status
Response: {
    "accessibility": True/False,
    "screen_recording": True/False
}

# 跳转到设置
POST /api/v1/permissions/open/{permission_type}
```

## 5. 与现有模块集成

### 5.1 ApprovalService 集成

ApprovalService 已经与工具授权系统集成：

```python
class ApprovalService:
    def __init__(self):
        self._pending_requests: Dict[str, ApprovalRequest] = {}
        self._always_allowed_tools: Set[str] = set()
        self._approval_callbacks: List[Callable] = []

    def is_auto_approved(self, tool_name: str) -> bool:
        """检查工具是否自动批准"""
        return tool_name in self._always_allowed_tools

    def always_allow(self, request_id: str) -> bool:
        """始终允许该工具 - 添加到 _always_allowed_tools"""
        self._always_allowed_tools.add(request.tool_name)

    def get_always_allowed_tools(self) -> Set[str]:
        """获取始终允许的工具列表"""
        return self._always_allowed_tools.copy()

    def remove_always_allow(self, tool_name: str) -> bool:
        """从始终允许列表移除"""
        if tool_name in self._always_allowed_tools:
            self._always_allowed_tools.remove(tool_name)
            return True
        return False
```

### 5.2 AgentBridge 与 LLMGateway 集成

AgentBridge 通过 openclaw_client 调用 LLM，支持多 Agent 并行调用：

```python
class AgentBridge:
    def __init__(self, openclaw_client: Any):
        self._client = openclaw_client
        self._sessions: Dict[str, AgentSession] = {}

    def invoke(self, agent_id: str, message: str,
               context: Optional[Dict] = None,
               timeout: float = 120.0) -> AgentResponse:
        """调用单个 Agent"""

    def batch_invoke(self, requests: List[InvokeRequest]) -> List[AgentResponse]:
        """批量并行调用多个 Agent"""
```

### 5.3 DatabaseManager 集成

DatabaseManager 通过全局单例 `db` 提供持久化服务：

```python
# 全局数据库实例
db = DatabaseManager()

# 使用示例
db.add_message(session_id, "user", "Hello")
db.add_audit_log(session_id, "code_analysis", {}, "medium", "auto_approve")
db.set_tool_authorization("read_file", True)
```

## 6. 验收标准

| ID | 标准 | 状态 | 验证方式 |
|----|------|------|----------|
| P5-1 | 会话创建和消息存储正常 | 已实现 |单元测试 |
| P5-2 | 审计日志记录工具调用 | 已实现 |单元测试 |
| P5-3 | 工具权限持久化 | 已实现 |单元测试 |
| P5-4 | Agent Bridge 执行工具调用循环 | 已实现 |集成测试 |
| P5-5 | 审批服务管理待审批请求 | 已实现 |单元测试 |
| P5-6 | 权限引导 UI 跳转正常 | 待实现 |手动测试 |

## 7. 技术限制

- SQLite 不支持高并发写入
- Agent Bridge 最大并发数取决于配置
- TCC 权限检查依赖系统命令，可能有延迟
- 部分权限检测在沙盒环境下可能不准确

## 8. 实现状态汇总

### 已实现模块

| 模块 | 文件位置 | 状态 |
|------|----------|------|
| DatabaseManager | `src/across_agents_assistant/db/database.py` | 已实现 |
| ApprovalService | `src/across_agents_assistant/approval/service.py` | 已实现 |
| ApprovalModels | `src/across_agents_assistant/approval/models.py` | 已实现 |
| ApprovalExecutor | `src/across_agents_assistant/approval/executor.py` | 已实现 |
| AgentBridge | `src/across_agents_assistant/agent_bridge/bridge.py` | 已实现 |
| AgentSession | `src/across_agents_assistant/agent_bridge/agent.py` | 已实现 |
| AgentProtocol | `src/across_agents_assistant/agent_bridge/protocol.py` | 已实现 |
| AgentResult | `src/across_agents_assistant/agent_bridge/result.py` | 已实现 |
| AgentErrors | `src/across_agents_assistant/agent_bridge/errors.py` | 已实现 |

### 待实现功能

| 功能 | 说明 |
|------|------|
| PermissionGuider UI | 前端权限引导界面 |
| API Endpoints | FastAPI 路由尚未完全实现 |
| 独立 persistence 模块 | 当前功能集成在 db/database.py 中 |