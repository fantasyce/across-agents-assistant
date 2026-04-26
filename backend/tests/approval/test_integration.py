import pytest
from across_agents_assistant.approval.service import ApprovalService
from across_agents_assistant.approval.executor import ToolExecutor
from across_agents_assistant.approval.models import RiskLevel, ApprovalStatus
from across_agents_assistant.tools.tool_registry import registry

# Import builtin_tools to ensure tools are registered
from across_agents_assistant.tools import builtin_tools  # noqa: F401

def test_full_approval_flow():
    """完整审批流程：创建请求 -> 批准 -> 执行"""
    service = ApprovalService()
    executor = ToolExecutor(registry, service)

    # 1. 创建审批请求
    request = service.create_approval_request(
        task_id="task-1",
        subtask_id="st-1",
        agent_id="claude",
        tool_name="create_email_draft",
        tool_params={"recipient": "test@example.com", "subject": "Hi", "body": "Hello"},
        risk_level=RiskLevel.MEDIUM,
        description="帮我写邮件给老板"
    )
    assert request.status == ApprovalStatus.PENDING
    pending = service.get_pending_requests()
    assert len(pending) == 1

    # 2. 批准请求
    approved = service.approve(request.request_id)
    assert approved == True
    assert request.status == ApprovalStatus.APPROVED
    assert len(service.get_pending_requests()) == 0

    # 3. 执行已批准的请求
    result = executor.execute_approved_request(request)
    assert result.success == True
    assert "draft" in result.output.lower() or "成功" in result.output

def test_rejection_flow():
    """拒绝流程"""
    service = ApprovalService()
    executor = ToolExecutor(registry, service)

    request = service.create_approval_request(
        task_id="task-1",
        subtask_id="st-1",
        agent_id="claude",
        tool_name="create_email_draft",
        tool_params={"recipient": "test@example.com"},
        risk_level=RiskLevel.MEDIUM,
        description="帮我写邮件"
    )

    rejected = service.reject(request.request_id)
    assert rejected == True
    assert request.status == ApprovalStatus.REJECTED

    # 执行已拒绝的请求应该失败
    result = executor.execute_approved_request(request)
    assert result.success == False

def test_always_allow_flow():
    """始终允许流程"""
    service = ApprovalService()
    executor = ToolExecutor(registry, service)

    # 创建并始终允许
    request = service.always_allow(
        service.create_approval_request(
            task_id="task-1",
            subtask_id="st-1",
            agent_id="claude",
            tool_name="list_directory",
            tool_params={"path": "~"},
            risk_level=RiskLevel.LOW,
            description="查看目录"
        ).request_id
    )
    assert request == True
    assert service.is_auto_approved("list_directory") == True

    # 再次执行同一工具应该自动批准
    request2 = service.create_approval_request(
        task_id="task-2",
        subtask_id="st-2",
        agent_id="claude",
        tool_name="list_directory",
        tool_params={"path": "~"},
        risk_level=RiskLevel.LOW,
        description="再次查看目录"
    )
    assert request2.status == ApprovalStatus.ALWAYS_ALLOW

def test_low_risk_auto_executes():
    """低风险工具自动执行"""
    service = ApprovalService()
    executor = ToolExecutor(registry, service)

    result = executor.execute_tool(
        tool_name="list_directory",
        params={"path": "~"},
        task_id="task-1",
        subtask_id="st-1",
        agent_id="claude",
        user_description="查看目录"
    )

    # LOW 风险直接执行，不需要审批
    assert result.success == True
    assert result.tool_name == "list_directory"