import uuid
from typing import List, Optional
from .database import Database

class ToolPermissionStore:
    """工具授权管理器"""
    PERSISTED_PERMISSION_TYPES = {"always_allow", "unavailable"}
    ASK_PERMISSION_TYPES = {"ask", "ask_every_time", "ask_each_time"}

    def __init__(self, db_path: str):
        self.db = Database(db_path)
        self.db.init_schema()

    def grant_always_allow(self, tool_name: str, session_id: Optional[str] = None) -> bool:
        """授予始终允许权限"""
        return self.set_permission(tool_name, "always_allow", session_id=session_id)

    def set_permission(self, tool_name: str, permission_type: str, session_id: Optional[str] = None) -> bool:
        """设置工具权限。ask 类权限不持久化，表示每次询问。"""
        normalized = permission_type.strip().lower()
        if normalized in self.ASK_PERMISSION_TYPES:
            self.revoke_permission(tool_name)
            return True
        if normalized not in self.PERSISTED_PERMISSION_TYPES:
            raise ValueError(f"Unsupported permission type: {permission_type}")

        perm_id = f"perm-{uuid.uuid4().hex[:12]}"
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            # 使用 REPLACE 确保持久化
            cursor.execute(
                '''INSERT OR REPLACE INTO tool_permissions (id, tool_name, permission_type, granted_by)
                   VALUES (?, ?, ?, ?)''',
                (perm_id, tool_name, normalized, session_id or None)
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

    def is_unavailable(self, tool_name: str) -> bool:
        """检查工具是否被用户设置为不可用"""
        return self.get_permission(tool_name) == 'unavailable'

    def list_always_allowed(self) -> List[str]:
        """列出所有始终允许的工具名称"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT tool_name FROM tool_permissions WHERE permission_type = 'always_allow'")
            rows = cursor.fetchall()
            return [row['tool_name'] for row in rows]

    def list_permissions(self) -> List[dict]:
        """列出所有权限记录（含详细信息）"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT tool_name, permission_type, granted_at, granted_by "
                "FROM tool_permissions ORDER BY granted_at DESC"
            )
            return [dict(r) for r in cursor.fetchall()]
