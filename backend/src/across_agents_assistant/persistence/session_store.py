import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from .database import Database

@dataclass
class Session:
    id: str
    title: Optional[str]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

@dataclass
class Message:
    id: str
    session_id: str
    role: str
    content: str
    metadata: Dict[str, Any]
    created_at: datetime

class SessionStore:
    """会话存储管理器"""

    def __init__(self, db_path: str):
        self.db = Database(db_path)
        self.db.init_schema()

    def create_session(self, title: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Session:
        """创建新会话"""
        session_id = f"sess-{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO sessions (id, title, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?)',
                (session_id, title or "", json.dumps(metadata or {}), now, now)
            )

        return Session(
            id=session_id,
            title=title,
            metadata=metadata or {},
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

    def get_or_create_session(self, session_id: str, title: Optional[str] = None) -> Session:
        """获取或创建会话"""
        existing = self.get_session(session_id)
        if existing:
            return existing
        now = datetime.now().isoformat()
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT OR IGNORE INTO sessions (id, title, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?)',
                (session_id, title or "", '{}', now, now)
            )
        return Session(
            id=session_id, title=title, metadata={},
            created_at=datetime.now(), updated_at=datetime.now()
        )

    def update_session(self, session_id: str, title: Optional[str] = None) -> bool:
        """更新会话属性（如重命名）"""
        now = datetime.now().isoformat()
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            if title is not None:
                cursor.execute(
                    'UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?',
                    (title, now, session_id)
                )
            else:
                cursor.execute(
                    'UPDATE sessions SET updated_at = ? WHERE id = ?',
                    (now, session_id)
                )
            return cursor.rowcount > 0

    def update_system_message(self, session_id: str, new_content: str) -> bool:
        """更新会话的第一条系统消息内容"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id FROM messages WHERE session_id = ? AND role = "system" ORDER BY created_at ASC LIMIT 1',
                (session_id,)
            )
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    'UPDATE messages SET content = ? WHERE id = ?',
                    (new_content, row['id'])
                )
                return True
            return False

    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
            row = cursor.fetchone()

        if not row:
            return None

        return Session(
            id=row['id'],
            title=row['title'],
            metadata=json.loads(row['metadata'] or '{}'),
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at'])
        )

    def list_sessions(self, limit: int = 50) -> List[Session]:
        """列出最近会话"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?', (limit,))
            rows = cursor.fetchall()

        return [
            Session(
                id=row['id'],
                title=row['title'],
                metadata=json.loads(row['metadata'] or '{}'),
                created_at=datetime.fromisoformat(row['created_at']),
                updated_at=datetime.fromisoformat(row['updated_at'])
            )
            for row in rows
        ]

    def add_message(self, session_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Message:
        """添加消息"""
        message_id = f"msg-{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO messages (id, session_id, role, content, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                (message_id, session_id, role, content, json.dumps(metadata or {}), now)
            )
            cursor.execute('UPDATE sessions SET updated_at = ? WHERE id = ?', (now, session_id))

        return Message(
            id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            metadata=metadata or {},
            created_at=datetime.now()
        )

    def count_messages(self, session_id: str) -> int:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT COUNT(*) FROM messages WHERE session_id = ?',
                (session_id,)
            )
            return cursor.fetchone()[0]

    def get_messages(self, session_id: str, limit: int = 30, offset: int = 0) -> List[Message]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?',
                (session_id, limit, offset)
            )
            rows = cursor.fetchall()

        msgs = [
            Message(
                id=row['id'],
                session_id=row['session_id'],
                role=row['role'],
                content=row['content'],
                metadata=json.loads(row['metadata'] or '{}'),
                created_at=datetime.fromisoformat(row['created_at'])
            )
            for row in rows
        ]
        msgs.reverse()
        return msgs

    def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
            cursor.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
            return cursor.rowcount > 0