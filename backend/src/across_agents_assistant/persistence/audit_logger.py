import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from .database import Database

@dataclass
class AuditLog:
    id: str
    timestamp: datetime
    event_type: str
    session_id: Optional[str]
    task_id: Optional[str]
    tool_name: Optional[str]
    risk_level: Optional[str]
    decision: Optional[str]
    details: Dict[str, Any]

class AuditLogger:
    """审计日志管理器"""

    def __init__(self, db_path: str):
        self.db = Database(db_path)
        self.db.init_schema()

    def log_tool_call(self, task_id: str, tool_name: str, risk_level: str, params: Dict[str, Any] = None):
        """记录工具调用"""
        log_id = f"log-{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO audit_logs (id, timestamp, event_type, task_id, tool_name, risk_level, details)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (log_id, now, 'tool_call', task_id, tool_name, risk_level, json.dumps(params or {}))
            )

    def log_approval_request(self, request_id: str, task_id: str, tool_name: str, risk_level: str):
        """记录审批请求"""
        log_id = f"log-{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO audit_logs (id, timestamp, event_type, session_id, task_id, tool_name, risk_level)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (log_id, now, 'approval_request', None, task_id, tool_name, risk_level)
            )

    def log_approval_decision(self, request_id: str, decision: str, details: Dict[str, Any] = None):
        """记录审批决定"""
        log_id = f"log-{uuid.uuid4().hex[:12]}"
        now = datetime.now().isoformat()

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''INSERT INTO audit_logs (id, timestamp, event_type, session_id, decision, details)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (log_id, now, 'approval_decision', None, decision, json.dumps(details or {}))
            )

    def query_logs(
        self,
        event_type: Optional[str] = None,
        tool_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditLog]:
        """查询审计日志"""
        query = 'SELECT * FROM audit_logs WHERE 1=1'
        params = []

        if event_type:
            query += ' AND event_type = ?'
            params.append(event_type)

        if tool_name:
            query += ' AND tool_name = ?'
            params.append(tool_name)

        if start_time:
            query += ' AND timestamp >= ?'
            params.append(start_time.isoformat())

        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

        return [
            AuditLog(
                id=row['id'],
                timestamp=datetime.fromisoformat(row['timestamp']),
                event_type=row['event_type'],
                session_id=row['session_id'],
                task_id=row['task_id'],
                tool_name=row['tool_name'],
                risk_level=row['risk_level'],
                decision=row['decision'],
                details=json.loads(row['details'] or '{}')
            )
            for row in rows
        ]