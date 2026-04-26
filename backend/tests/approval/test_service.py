import pytest
from across_agents_assistant.approval.service import ApprovalService
from across_agents_assistant.approval.models import RiskLevel, ApprovalStatus, ApprovalRequest

@pytest.fixture
def service():
    return ApprovalService()

def test_service_initial_state(service):
    assert service.get_pending_requests() == []
    assert service.is_auto_approved("any_tool") == False

def test_create_approval_request(service):
    req = service.create_approval_request(
        task_id="task-1",
        subtask_id="st-1",
        agent_id="claude",
        tool_name="create_email_draft",
        tool_params={"recipient": "test@example.com"},
        risk_level=RiskLevel.MEDIUM,
        description="帮我写邮件"
    )
    assert req.request_id is not None
    assert req.status == ApprovalStatus.PENDING
    assert len(service.get_pending_requests()) == 1

def test_approve_request(service):
    req = service.create_approval_request(
        task_id="task-1",
        subtask_id="st-1",
        agent_id="claude",
        tool_name="create_email_draft",
        tool_params={},
        risk_level=RiskLevel.MEDIUM,
        description="帮我写邮件"
    )
    result = service.approve(req.request_id)
    assert result == True
    assert req.status == ApprovalStatus.APPROVED

def test_reject_request(service):
    req = service.create_approval_request(
        task_id="task-1",
        subtask_id="st-1",
        agent_id="claude",
        tool_name="create_email_draft",
        tool_params={},
        risk_level=RiskLevel.MEDIUM,
        description="帮我写邮件"
    )
    result = service.reject(req.request_id)
    assert result == True
    assert req.status == ApprovalStatus.REJECTED

def test_always_allow(service):
    req = service.create_approval_request(
        task_id="task-1",
        subtask_id="st-1",
        agent_id="claude",
        tool_name="list_directory",
        tool_params={},
        risk_level=RiskLevel.LOW,
        description="查看目录"
    )
    result = service.always_allow(req.request_id)
    assert result == True
    assert service.is_auto_approved("list_directory") == True

def test_unknown_request_approve(service):
    result = service.approve("unknown-id")
    assert result == False

def test_remove_always_allow(service):
    service._always_allowed_tools.add("list_directory")
    result = service.remove_always_allow("list_directory")
    assert result == True
    assert service.is_auto_approved("list_directory") == False

def test_remove_always_allow_not_in_list(service):
    result = service.remove_always_allow("nonexistent_tool")
    assert result == False

def test_get_always_allowed_tools(service):
    service._always_allowed_tools.add("tool_a")
    service._always_allowed_tools.add("tool_b")
    tools = service.get_always_allowed_tools()
    assert "tool_a" in tools
    assert "tool_b" in tools

def test_reject_unknown_request(service):
    result = service.reject("unknown-id")
    assert result == False

def test_always_allow_non_pending_request(service):
    req = service.create_approval_request(
        task_id="task-1",
        subtask_id="st-1",
        agent_id="claude",
        tool_name="list_directory",
        tool_params={},
        risk_level=RiskLevel.LOW,
        description="查看目录"
    )
    # First approve it
    service.approve(req.request_id)
    # Now try to always_allow the same request (should fail since it's no longer pending)
    result = service.always_allow(req.request_id)
    assert result == False
    # Verify tool was NOT added to always allowed list
    assert service.is_auto_approved("list_directory") == False