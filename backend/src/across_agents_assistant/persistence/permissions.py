import uuid
from typing import List, Optional
from .database import Database

class ToolPermissionStore:
    """工具授权管理器"""

    def __init__(self, db_path: str):
        self.db = Database(db_path)
        self.db.init_schema()

    def grant_always_allow(self, tool_name: str, session_id: Optional[str] = None) -> bool:
        """授予始终允许权限"""
        perm_id = f"perm-{uuid.uuid4().hex[:12]}"

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            # 使用 REPLACE 确保持久化
            cursor.execute(
                '''INSERT OR REPLACE INTO tool_permissions (id, tool_name, permission_type, granted_by)
                   VALUES (?, ?, ?, ?)''',
                (perm_id, tool_name, 'always_allow', session_id or None)
            )
            return True

    def revoke_permission(self, tool_name: str) -> bool:
        """撤销权限"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM tool_permissions WHERE tool_name = ?', (tool_name,))
            return cursor.rowcount > 0

    def get_permission(self, tool_name: str) -> Optional[str]:
        """获取工具权限"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT permission_type FROM tool_permissions WHERE tool_name = ?', (tool_name,))
            row = cursor.fetchone()
            return row['permission_type'] if row else None

    def is_always_allowed(self, tool_name: str) -> bool:
        """检查是否始终允许"""
        return self.get_permission(tool_name) == 'always_allow'

    def list_always_allowed(self) -> List[str]:
        """列出所有始终允许的工具"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT tool_name FROM tool_permissions WHERE permission_type = 'always_allow'")
            rows = cursor.fetchall()
            return [row['tool_name'] for row in rows]