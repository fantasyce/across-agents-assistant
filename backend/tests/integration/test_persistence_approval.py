"""
Integration tests for ApprovalService + ToolPermissionStore persistence.

Run with: PYTHONPATH=backend/src:src pytest tests/integration/test_persistence_approval.py -v
"""
import pytest
import os
import tempfile

from src.across_agents_assistant.approval.service import ApprovalService
from src.across_agents_assistant.approval.models import RiskLevel, ApprovalRequest
from across_agents_assistant.persistence.permissions import ToolPermissionStore


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    fd, path = tempfile.mkstemp('.db')
    os.close(fd)
    os.unlink(path)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def permission_store(temp_db):
    """Create a ToolPermissionStore with temporary database."""
    return ToolPermissionStore(temp_db)


@pytest.fixture
def approval_service(permission_store):
    """Create an ApprovalService with persistent storage."""
    return ApprovalService(permission_store=permission_store)


def test_approval_service_with_persistence(approval_service, permission_store):
    """Test that ApprovalService uses ToolPermissionStore for persistence."""
    # Create a pending request
    request = approval_service.create_approval_request(
        task_id='task-1',
        subtask_id='sub-1',
        agent_id='agent-1',
        tool_name='test_tool',
        tool_params={'path': '/tmp'},
        risk_level=RiskLevel.HIGH,
        description='Test tool'
    )
    assert request.status.value == 'pending'

    # Approve it
    approval_service.approve(request.request_id)
    assert approval_service.is_auto_approved('test_tool') == False  # Not in always allow


def test_always_allow_persistence(approval_service, permission_store):
    """Test that always_allow persists to ToolPermissionStore."""
    # Create a pending request
    request = ApprovalRequest(
        request_id='req-test',
        task_id='task-1',
        subtask_id='sub-1',
        agent_id='agent-1',
        tool_name='persistent_tool',
        tool_params={},
        risk_level=RiskLevel.HIGH,
        description='Test'
    )
    approval_service._pending_requests[request.request_id] = request

    # Use always_allow
    result = approval_service.always_allow('req-test')
    assert result == True

    # Check it's persisted
    assert permission_store.is_always_allowed('persistent_tool') == True
    assert approval_service.is_auto_approved('persistent_tool') == True


def test_remove_always_allow_persistence(approval_service, permission_store):
    """Test that remove_always_allow removes from persistence."""
    # First add to always allow
    approval_service._always_allowed_tools.add('removable_tool')
    if approval_service._permission_store:
        approval_service._permission_store.grant_always_allow('removable_tool')

    # Verify it's in persistence
    assert permission_store.is_always_allowed('removable_tool') == True

    # Remove it
    result = approval_service.remove_always_allow('removable_tool')
    assert result == True

    # Verify it's removed from persistence
    assert permission_store.is_always_allowed('removable_tool') == False
    assert approval_service.is_auto_approved('removable_tool') == False


def test_persistence_loads_existing_tools(permission_store):
    """Test that ApprovalService loads existing always-allowed tools from persistence."""
    # Grant some permissions directly
    permission_store.grant_always_allow('pre_existing_tool')
    permission_store.grant_always_allow('another_tool')

    # Create new ApprovalService with same store
    service = ApprovalService(permission_store=permission_store)

    # Verify existing tools are loaded
    assert service.is_auto_approved('pre_existing_tool') == True
    assert service.is_auto_approved('another_tool') == True
    assert service.is_auto_approved('unknown_tool') == False


def test_backward_compatibility():
    """Test that ApprovalService works without permission_store (backward compatibility)."""
    service = ApprovalService()  # No permission_store
    assert service._permission_store is None

    # Add to always allow manually
    service._always_allowed_tools.add('manual_tool')
    assert service.is_auto_approved('manual_tool') == True
