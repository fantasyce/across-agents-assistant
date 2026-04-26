import pytest
from unittest.mock import MagicMock, patch
from across_agents_assistant.approval.executor import ToolExecutor
from across_agents_assistant.approval.service import ApprovalService
from across_agents_assistant.approval.models import RiskLevel, ApprovalStatus, ToolExecutionResult
from across_agents_assistant.tools.tool_registry import registry

# Import builtin_tools to ensure tools are registered
from across_agents_assistant.tools import builtin_tools  # noqa: F401

@pytest.fixture
def executor():
    return ToolExecutor(registry)

def test_executor_check_risk_level(executor):
    assert executor.check_risk_level("list_directory") == RiskLevel.LOW
    assert executor.check_risk_level("create_email_draft") == RiskLevel.MEDIUM

def test_executor_check_unknown_tool(executor):
    assert executor.check_risk_level("unknown_tool") == RiskLevel.HIGH

def test_executor_low_risk_auto_executes(executor):
    """LOW 风险工具应自动执行，不需要审批"""
    service = ApprovalService()
    executor_with_service = ToolExecutor(registry, service)

    result = executor_with_service.execute_tool(
        tool_name="list_directory",
        params={"path": "~"},
        task_id="task-1",
        subtask_id="st-1",
        agent_id="claude",
        user_description="查看主目录"
    )
    assert result.success == True
    assert result.tool_name == "list_directory"

def test_executor_medium_risk_creates_pending_request(executor):
    """MEDIUM 风险工具应创建待审批请求"""
    service = ApprovalService()
    executor_with_service = ToolExecutor(registry, service)

    result = executor_with_service.execute_tool(
        tool_name="create_email_draft",
        params={"recipient": "test@example.com", "subject": "Hi", "body": "Hello"},
        task_id="task-1",
        subtask_id="st-1",
        agent_id="claude",
        user_description="帮我写邮件"
    )
    # 应该返回 pending 状态，不直接执行
    assert result.success == False
    assert result.output is None  # 未执行，等待审批

    # 检查是否有待审批请求
    pending = service.get_pending_requests()
    assert len(pending) == 1
    assert pending[0].tool_name == "create_email_draft"