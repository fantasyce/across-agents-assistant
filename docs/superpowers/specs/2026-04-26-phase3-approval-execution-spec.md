# Phase 3: 审批与受控执行 - 设计规格

## 1. 概述

**目标：** 实现完整的"规划 → 审批 → 执行 → 反馈"链路，确保高风险工具调用被用户确认后才执行。

**架构位置：** Phase 3 在 TaskManager 和 AgentBridge 之上，新增审批层。

```
┌─────────────────────────────────────────────────────────────────┐
│                         UI Layer                                 │
│  ┌─────────────────┐  ┌──────────────────────────────────────┐  │
│  │   会话窗口       │  │        审批浮窗                       │  │
│  │  (结果显示)     │  │  (待审批请求列表)                     │  │
│  └────────┬────────┘  └───────────────┬──────────────────────┘  │
│           │                          │                           │
│           └──────────────┬───────────┘                           │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    ApprovalService                           │ │
│  │  - 管理待审批队列                                           │ │
│  │  - 处理 approve/reject/always_allow                        │ │
│  │  - 风险等级判断                                             │ │
│  └────────────────────────────┬────────────────────────────────┘ │
│                               │                                  │
│           ┌───────────────────┼───────────────────┐               │
│           ▼                   ▼                   ▼               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  TaskManager    │  │   ToolRegistry  │  │  AgentBridge    │  │
│  │  (任务管理)      │  │  (工具注册)     │  │  (Agent通信)    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## 2. 核心组件

### 2.1 ApprovalRequest（审批请求）

```python
@dataclass
class ApprovalRequest:
    request_id: str          # 唯一标识
    task_id: str             # 关联的任务 ID
    subtask_id: str          # 关联的子任务 ID
    agent_id: str            # 将要执行工具的 Agent
    tool_name: str           # 工具名称
    tool_params: Dict[str, Any]  # 工具参数
    risk_level: RiskLevel   # low/medium/high
    description: str         # 用户原始目标
    plan_summary: str        # Agent 计划摘要
    context_sources: List[str]  # 将读取的上下文来源
    created_at: float        # 创建时间
    status: ApprovalStatus   # pending/approved/rejected/always_allow
```

### 2.2 RiskLevel（风险等级）

```python
class RiskLevel(str, Enum):
    LOW = "low"      # 默认不审批
    MEDIUM = "medium"  # 需要审批
    HIGH = "high"    # 默认拒绝，需要强审批
```

### 2.3 ApprovalStatus（审批状态）

```python
class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ALWAYS_ALLOW = "always_allow"  # 始终允许，下次自动执行
    EXPIRED = "expired"  # 超时未处理
```

### 2.4 ApprovalService（审批服务）

```python
class ApprovalService:
    def __init__(self):
        self._pending_requests: Dict[str, ApprovalRequest] = {}
        self._always_allowed_tools: Set[str] = set()
        self._approval_callbacks: List[Callable] = []
    
    def create_approval_request(
        self,
        task_id: str,
        subtask_id: str,
        agent_id: str,
        tool_name: str,
        tool_params: Dict[str, Any],
        risk_level: RiskLevel,
        description: str,
        plan_summary: str = "",
        context_sources: List[str] = None
    ) -> ApprovalRequest:
        """创建审批请求"""
    
    def approve(self, request_id: str) -> bool:
        """用户批准"""
    
    def reject(self, request_id: str) -> bool:
        """用户拒绝"""
    
    def always_allow(self, request_id: str) -> bool:
        """用户选择始终允许"""
    
    def get_pending_requests(self) -> List[ApprovalRequest]:
        """获取所有待审批请求"""
    
    def is_auto_approved(self, tool_name: str) -> bool:
        """检查工具是否在始终允许列表"""
```

### 2.5 ToolExecutor（工具执行器）

```python
class ToolExecutor:
    def __init__(self, registry: ToolRegistry, approval_service: ApprovalService):
        self._registry = registry
        self._approval_service = approval_service
    
    async def execute_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        task_id: str,
        subtask_id: str,
        agent_id: str,
        user_description: str
    ) -> ToolExecutionResult:
        """执行工具，可能触发审批流程"""
```

## 3. 执行流程

### 3.1 工具执行流程

```
用户请求 "帮我写邮件给老板"
         │
         ▼
┌─────────────────────────┐
│   TaskManager 分解任务  │
│   subtask: create_email_draft │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│   ToolExecutor 检查风险   │
│   risk_level = medium   │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│   检查是否始终允许       │
│   不在白名单            │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│   ApprovalService       │
│   创建 ApprovalRequest   │
│   状态: PENDING         │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│   审批浮窗显示           │
│   - 用户目标            │
│   - 工具信息            │
│   - 批准/拒绝/始终允许  │
└───────────┬─────────────┘
            │
     ┌──────┴──────┐
     │             │
     ▼             ▼
┌─────────┐  ┌─────────┐
│  批准    │  │  拒绝    │
└────┬────┘  └────┬────┘
     │             │
     ▼             ▼
┌─────────┐  ┌─────────┐
│ 执行工具 │  │ 返回草稿 │
│ 返回结果 │  │ 提示拒绝 │
└─────────┘  └─────────┘
```

### 3.2 低风险工具自动执行

```
用户请求 "查看当前目录"
         │
         ▼
┌─────────────────────────┐
│   risk_level = low      │
│   不需要审批             │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│   直接执行工具           │
│   返回结果到会话        │
└─────────────────────────┘
```

## 4. 审批浮窗 UI

### 4.1 浮窗布局

```
┌──────────────────────────────────────────────────────┐
│  🔔 待审批请求 (2)                              [X]  │
├──────────────────────────────────────────────────────┤
│                                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │ 📧 邮件草稿 - medium risk                       │ │
│  │                                                 │ │
│  │ 用户目标: 帮我写邮件给老板                       │ │
│  │                                                 │ │
│  │ 计划摘要: 将创建一封邮件草稿，包含主题和正文     │ │
│  │                                                 │ │
│  │ 工具: create_email_draft                        │ │
│  │ 参数: recipient=老板邮箱                        │ │
│  │       subject=项目进度汇报                      │ │
│  │       body=...                                  │ │
│  │                                                 │ │
│  │ 风险: 将创建邮件草稿（非直接发送）              │ │
│  │                                                 │ │
│  │  [批准]  [拒绝]  [始终允许]                     │ │
│  └─────────────────────────────────────────────────┘ │
│                                                       │
│  ┌─────────────────────────────────────────────────┐ │
│  │ 📁 查看目录 - low risk                          │ │
│  │                                                 │ │
│  │ ...                                             │ │
│  └─────────────────────────────────────────────────┘ │
│                                                       │
└──────────────────────────────────────────────────────┘
```

### 4.2 审批操作

| 操作 | 描述 | 后续行为 |
|------|------|----------|
| 批准 | 同意本次执行 | 执行工具，返回结果 |
| 拒绝 | 拒绝执行 | 返回拒绝提示，不执行 |
| 始终允许 | 记住选择 | 将工具加入白名单，后续自动执行 |

## 5. 数据模型

### 5.1 持久化审批规则

审批规则（用户选择"始终允许"的工具）存储在本地配置：

```json
// ~/.across-agents/approval_rules.json
{
  "always_allowed_tools": ["list_directory", "get_finder_context", "toggle_system_dark_mode"],
  "always_allowed_agents": [],
  "created_at": "2026-04-26T12:00:00Z"
}
```

## 6. API 设计

### 6.1 内部 API

```python
# ApprovalService
approval_service.create_approval_request(...)
approval_service.approve(request_id) -> bool
approval_service.reject(request_id) -> bool
approval_service.always_allow(request_id) -> bool
approval_service.get_pending_requests() -> List[ApprovalRequest]

# ToolExecutor  
tool_executor.execute_tool(...) -> ToolExecutionResult
tool_executor.check_risk_level(tool_name) -> RiskLevel
```

### 6.2 事件回调

```python
# 审批状态变化时触发
def on_approval_state_changed(request: ApprovalRequest):
    """更新 UI，显示审批结果"""
```

## 7. 现有模块集成

### 7.1 与 TaskManager 集成

TaskManager 的 `_execute_agent_job` 执行工具前，先经过 ToolExecutor：

```python
def _execute_agent_job(self, job: Job, subtask: SubTask, target_agent: str) -> JobResult:
    # 检查是否需要审批
    tool_name = subtask.tool_name
    risk_level = tool_executor.check_risk_level(tool_name)
    
    if risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH):
        # 创建审批请求
        request = approval_service.create_approval_request(...)
        # 等待审批结果
        # ...
    else:
        # 直接执行
        result = tool_executor.execute_tool(...)
```

### 7.2 与 UI 集成

审批浮窗订阅 ApprovalService 的状态变化：

```python
approval_service.add_callback(on_approval_state_changed)
```

## 8. 验收标准

| ID | 标准 | 验证方式 |
|----|------|----------|
| P3-1 | 只读工具（list_directory, get_finder_context）执行不需要审批 | 手动测试 |
| P3-2 | 草稿工具（create_email_draft, create_note_draft）触发审批浮窗 | 手动测试 |
| P3-3 | 审批通过后工具执行并返回结果 | 手动测试 |
| P3-4 | 审批拒绝后返回拒绝提示 | 手动测试 |
| P3-5 | "始终允许"功能正确添加到白名单 | 手动测试 |
| P3-6 | 审批超时处理（5分钟） | 手动测试 |
| P3-7 | 多任务并发审批支持 | 手动测试 |

## 9. 技术限制

- Phase 3 暂不实现持久化审批规则存储（下次启动丢失）
- 高风险（high）工具暂不开放，默认直接拒绝
- 审批超时暂定为 5 分钟

## 10. 文件结构

```
backend/src/across_agents_assistant/
├── approval/
│   ├── __init__.py
│   ├── models.py          # ApprovalRequest, RiskLevel, ApprovalStatus, ToolExecutionResult
│   ├── service.py         # ApprovalService
│   ├── executor.py        # ToolExecutor
│   └── tests/
│       ├── __init__.py
│       ├── test_models.py
│       ├── test_service.py
│       ├── test_executor.py
│       └── test_integration.py
```

## 11. 验收测试结果

| ID | 标准 | 测试方式 | 状态 |
|----|------|----------|------|
| P3-1 | 只读工具执行不需要审批 | test_low_risk_auto_executes | ✅ |
| P3-2 | 草稿工具触发审批流程 | test_executor_medium_risk_creates_pending_request | ✅ |
| P3-3 | 审批通过后工具执行 | test_full_approval_flow | ✅ |
| P3-4 | 审批拒绝后返回失败 | test_rejection_flow | ✅ |
| P3-5 | "始终允许"功能正常 | test_always_allow_flow | ✅ |

## 12. 依赖关系

- ApprovalService 依赖 ToolRegistry（已有）
- ToolExecutor 依赖 ToolRegistry 和 ApprovalService
- UI 层依赖 ApprovalService 的回调

## 12. 风险与注意事项

1. **并发审批**：多个任务同时需要审批时，需要队列管理
2. **审批状态同步**：审批浮窗和 TaskManager 之间的状态同步
3. **超时处理**：用户长时间不审批需要超时处理
4. **安全边界**：始终允许功能可能被滥用，需要明确的工具范围限制