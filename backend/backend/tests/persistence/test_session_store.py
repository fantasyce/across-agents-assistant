import pytest
import os
import tempfile
from across_agents_assistant.persistence.session_store import SessionStore, Session, Message

@pytest.fixture
def store():
    fd, path = tempfile.mkstemp('.db')
    os.close(fd)
    os.unlink(path)
    yield SessionStore(path)
    os.unlink(path)

def test_create_session(store):
    session = store.create_session(title="Test Session")
    assert session.id.startswith("sess-")
    assert session.title == "Test Session"

def test_get_session(store):
    session = store.create_session(title="Test")
    found = store.get_session(session.id)
    assert found is not None
    assert found.title == "Test"

def test_list_sessions(store):
    store.create_session(title="Session 1")
    store.create_session(title="Session 2")
    sessions = store.list_sessions()
    assert len(sessions) == 2

def test_add_message(store):
    session = store.create_session()
    msg = store.add_message(session.id, "user", "Hello")
    assert msg.role == "user"
    assert msg.content == "Hello"

def test_get_messages(store):
    session = store.create_session()
    store.add_message(session.id, "user", "Hello")
    store.add_message(session.id, "assistant", "Hi")
    msgs = store.get_messages(session.id)
    assert len(msgs) == 2

def test_delete_session(store):
    session = store.create_session()
    result = store.delete_session(session.id)
    assert result == True
    assert store.get_session(session.id) is None