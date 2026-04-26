import time
import pytest
from across_agents_assistant.approval.models import RiskLevel, ApprovalStatus, ApprovalRequest, ToolExecutionResult

def test_risk_level_enum():
    assert RiskLevel.LOW.value == "low"
    assert RiskLevel.MEDIUM.value == "medium"
    assert RiskLevel.HIGH.value == "high"

def test_approval_status_enum():
    assert ApprovalStatus.PENDING.value == "pending"
    assert ApprovalStatus.APPROVED.value == "approved"
    assert ApprovalStatus.REJECTED.value == "rejected"
    assert ApprovalStatus.ALWAYS_ALLOW.value == "always_allow"
    assert ApprovalStatus.EXPIRED.value == "expired"

def test_approval_request_creation():
    req = ApprovalRequest(
        request_id="req-1",
        task_id="task-1",
        subtask_id="st-1",
        agent_id="claude",
        tool_name="create_email_draft",
        tool_params={"recipient": "boss@example.com", "subject": "Hi", "body": "Hello"},
        risk_level=RiskLevel.MEDIUM,
        description="帮我写邮件给老板",
        plan_summary="将创建邮件草稿",
        context_sources=["clipboard"]
    )
    assert req.request_id == "req-1"
    assert req.tool_name == "create_email_draft"
    assert req.risk_level == RiskLevel.MEDIUM
    assert req.status == ApprovalStatus.PENDING

def test_tool_execution_result():
    result = ToolExecutionResult(
        success=True,
        output="邮件草稿已创建",
        tool_name="create_email_draft"
    )
    assert result.success == True
    assert result.output == "邮件草稿已创建"

def test_approval_request_is_pending():
    req = ApprovalRequest(
        request_id="req-1",
        task_id="task-1",
        subtask_id="st-1",
        agent_id="claude",
        tool_name="create_email_draft",
        tool_params={},
        risk_level=RiskLevel.MEDIUM,
        description="帮我写邮件"
    )
    assert req.is_pending() == True
    req.status = ApprovalStatus.APPROVED
    assert req.is_pending() == False

def test_approval_request_is_expired():
    req = ApprovalRequest(
        request_id="req-1",
        task_id="task-1",
        subtask_id="st-1",
        agent_id="claude",
        tool_name="create_email_draft",
        tool_params={},
        risk_level=RiskLevel.MEDIUM,
        description="帮我写邮件"
    )
    # Not expired when just created
    assert req.is_expired() == False

    # Simulate time passing by directly modifying created_at
    req.created_at = time.time() - 600  # 10 minutes ago
    assert req.is_expired() == True

    # If not pending, is_expired returns False regardless of time
    req.status = ApprovalStatus.APPROVED
    assert req.is_expired() == False