import pytest
import os
import tempfile
from across_agents_assistant.persistence.permissions import ToolPermissionStore

@pytest.fixture
def store():
    fd, path = tempfile.mkstemp('.db')
    os.close(fd)
    os.unlink(path)
    yield ToolPermissionStore(path)
    os.unlink(path)

def test_grant_always_allow(store):
    result = store.grant_always_allow('list_directory')
    assert result == True
    assert store.is_always_allowed('list_directory') == True

def test_revoke_permission(store):
    store.grant_always_allow('list_directory')
    result = store.revoke_permission('list_directory')
    assert result == True
    assert store.is_always_allowed('list_directory') == False

def test_get_permission(store):
    store.grant_always_allow('create_email_draft')
    perm = store.get_permission('create_email_draft')
    assert perm == 'always_allow'

def test_is_always_allowed(store):
    store.grant_always_allow('list_directory')
    assert store.is_always_allowed('list_directory') == True
    assert store.is_always_allowed('unknown_tool') == False

def test_list_always_allowed(store):
    store.grant_always_allow('list_directory')
    store.grant_always_allow('get_finder_context')
    tools = store.list_always_allowed()
    assert 'list_directory' in tools
    assert 'get_finder_context' in tools