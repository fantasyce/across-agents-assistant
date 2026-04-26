import pytest
import os
import tempfile
from datetime import datetime
from across_agents_assistant.persistence.audit_logger import AuditLogger

@pytest.fixture
def logger():
    fd, path = tempfile.mkstemp('.db')
    os.close(fd)
    os.unlink(path)
    yield AuditLogger(path)
    os.unlink(path)

def test_log_tool_call(logger):
    logger.log_tool_call('task-1', 'list_directory', 'low', {'path': '~'})
    logs = logger.query_logs(event_type='tool_call')
    assert len(logs) == 1
    assert logs[0].tool_name == 'list_directory'

def test_log_approval_request(logger):
    logger.log_approval_request('req-1', 'task-1', 'create_email_draft', 'medium')
    logs = logger.query_logs(event_type='approval_request')
    assert len(logs) == 1
    assert logs[0].tool_name == 'create_email_draft'

def test_log_approval_decision(logger):
    logger.log_approval_decision('req-1', 'approved')
    logs = logger.query_logs(event_type='approval_decision')
    assert len(logs) == 1
    assert logs[0].decision == 'approved'

def test_query_by_tool_name(logger):
    logger.log_tool_call('task-1', 'list_directory', 'low')
    logger.log_tool_call('task-2', 'create_email_draft', 'medium')
    logs = logger.query_logs(tool_name='create_email_draft')
    assert len(logs) == 1
    assert logs[0].tool_name == 'create_email_draft'