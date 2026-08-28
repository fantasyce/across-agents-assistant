import json
import os
import logging
import re
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional

from .database import Database
from .session_store import SessionStore
from .audit_logger import AuditLogger
from .permissions import ToolPermissionStore
from .task_persistence import TaskPersistenceService
from .promotion_package_store import PromotionPackageStore
from .goal_contract_store import GoalContractStore
from ..paths import app_subdir, data_file
from ..runtime_boundary import safe_runtime_override
from ..approval.receipts import ApprovalReceiptStore, ApprovalReceiptSubject

logger = logging.getLogger("across_agents_assistant.persistence")

# Default DB path inside the app-owned local data root.
DEFAULT_DB_PATH = safe_runtime_override("ACROSS_AGENTS_DB_PATH") or str(data_file("assistant.db"))


def _normalize_local_path(path: str) -> str:
    value = str(path or "").strip()
    if not value or "\x00" in value or "\r" in value or "\n" in value:
        raise ValueError("Invalid local path")
    return os.path.realpath(os.path.abspath(os.path.expanduser(value)))


class PersistenceService:
    """统一持久化服务入口。

    组合 SessionStore + AuditLogger + ToolPermissionStore + TaskPersistenceService，
    对外暴露与旧 db.DatabaseManager 兼容的方法签名，
    方便 api_server.py 逐步迁移到新模块。
    """

    def __init__(self, db_path: str = None):
        db_path = db_path or DEFAULT_DB_PATH
        self.db_path = db_path
        self.db = Database(db_path)
        self.sessions = SessionStore(db_path)
        self.audit = AuditLogger(db_path)
        self.permissions = ToolPermissionStore(db_path)
        self.approval_receipts = ApprovalReceiptStore(db_path)
        self.promotion_packages = PromotionPackageStore(db_path)
        self.tasks = TaskPersistenceService(self.db)
        # 确保 schema 已初始化
        self.db.init_schema()
        self.goal_contracts = GoalContractStore(self.db)
        # 启动时自动迁移旧数据
        self._auto_migrate()
        logger.info(f"PersistenceService initialized at {db_path}")

    # ──────────────────────────────────────────
    # 会话 / 消息（兼容旧 db 签名）
    # ──────────────────────────────────────────

    def get_or_create_session(self, session_id: str) -> None:
        """确保会话存在（兼容旧 db.get_or_create_session）。"""
        self.sessions.get_or_create_session(session_id)

    def ensure_default_project(self) -> Dict[str, Any]:
        workspace = app_subdir("workspace")
        return self.create_project(
            name=workspace.name,
            path=str(workspace),
            kind="blank",
            project_id="default-workspace",
            assign_unscoped_sessions=True,
        )

    def create_project(
        self,
        name: str,
        path: str,
        kind: str = "folder",
        project_id: Optional[str] = None,
        assign_unscoped_sessions: bool = False,
    ) -> Dict[str, Any]:
        normalized = _normalize_local_path(path)
        # codeql[py/path-injection]: Projects are explicit user-selected local
        # folders; the app creates/opens exactly that resolved local folder.
        os.makedirs(normalized, exist_ok=True)
        safe_name = (name or os.path.basename(normalized) or "Project").strip()
        safe_kind = kind if kind in {"blank", "folder"} else "folder"
        now = datetime.now().isoformat()
        pid = project_id or f"proj-{uuid.uuid4().hex[:12]}"
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM projects WHERE path = ?", (normalized,))
            row = cursor.fetchone()
            if not row and project_id:
                cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
                row = cursor.fetchone()
            if row:
                cursor.execute(
                    "UPDATE projects SET name = ?, path = ?, kind = ?, archived_at = NULL, updated_at = ?, last_opened_at = ? WHERE id = ?",
                    (safe_name, normalized, safe_kind, now, now, row["id"]),
                )
                pid = row["id"]
            else:
                cursor.execute(
                    """INSERT INTO projects
                       (id, name, path, kind, created_at, updated_at, last_opened_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (pid, safe_name, normalized, safe_kind, now, now, now),
                )
            if assign_unscoped_sessions:
                cursor.execute(
                    "UPDATE sessions SET project_id = ?, project_dir = ? WHERE project_id IS NULL",
                    (pid, normalized),
                )
        project = self.get_project(pid)
        if not project:
            raise RuntimeError(f"Failed to create project: {safe_name}")
        return project

    def create_blank_project(self, name: str) -> Dict[str, Any]:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "-", (name or "").strip()).strip(".-").lower()
        if not slug:
            slug = f"project-{uuid.uuid4().hex[:6]}"
        path = app_subdir("workspace") / slug
        return self.create_project(name=name or slug, path=str(path), kind="blank")

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM projects WHERE id = ? AND archived_at IS NULL", (project_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_projects(self, session_limit: int = 5) -> List[Dict[str, Any]]:
        self.ensure_default_project()
        safe_limit = max(0, min(int(session_limit or 5), 50))
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM projects
                   WHERE archived_at IS NULL
                   ORDER BY is_pinned DESC, pinned_at DESC, last_opened_at DESC, updated_at DESC, name COLLATE NOCASE ASC"""
            )
            projects = [dict(row) for row in cursor.fetchall()]
            for project in projects:
                if safe_limit == 0:
                    project["sessions"] = []
                    continue
                cursor.execute(
                    """SELECT s.id as session_id, s.created_at, s.updated_at, s.title as name,
                              s.project_id, s.project_dir, s.is_pinned, s.pinned_at,
                              (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id AND m.role != 'system') as message_count,
                              (SELECT m2.content FROM messages m2
                               WHERE m2.session_id = s.id AND m2.role = 'user'
                               ORDER BY m2.created_at ASC LIMIT 1) as first_user_message
                       FROM sessions s
                       WHERE s.project_id = ?
                         AND EXISTS (SELECT 1 FROM messages m3 WHERE m3.session_id = s.id AND m3.role != 'system')
                       ORDER BY s.is_pinned DESC, s.pinned_at DESC, s.updated_at DESC
                       LIMIT ?""",
                    (project["id"], safe_limit),
                )
                project["sessions"] = [dict(row) for row in cursor.fetchall()]
        return projects

    def set_project_pinned(self, project_id: str, is_pinned: bool) -> Optional[Dict[str, Any]]:
        now = datetime.now().isoformat()
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE projects
                   SET is_pinned = ?, pinned_at = ?, updated_at = ?
                   WHERE id = ? AND archived_at IS NULL""",
                (1 if is_pinned else 0, now if is_pinned else None, now, project_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get_project(project_id)

    def set_session_pinned(self, session_id: str, is_pinned: bool) -> bool:
        now = datetime.now().isoformat()
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """UPDATE sessions
                   SET is_pinned = ?, pinned_at = ?, updated_at = ?
                   WHERE id = ?""",
                (1 if is_pinned else 0, now if is_pinned else None, now, session_id),
            )
            return cursor.rowcount > 0

    def assign_session_project(
        self,
        session_id: str,
        project_id: Optional[str] = None,
        project_dir: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if not session_id:
            return None
        project = None
        if project_id:
            project = self.get_project(project_id)
        if not project and project_dir:
            normalized = os.path.realpath(os.path.expanduser(project_dir))
            project = self.create_project(
                name=os.path.basename(normalized) or "Project",
                path=normalized,
                kind="folder",
            )
        if not project:
            project = self.ensure_default_project()
        self.get_or_create_session(session_id)
        now = datetime.now().isoformat()
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE sessions SET project_id = ?, project_dir = ?, updated_at = ? WHERE id = ?",
                (project["id"], project["path"], now, session_id),
            )
            cursor.execute(
                "UPDATE projects SET last_opened_at = ?, updated_at = ? WHERE id = ?",
                (now, now, project["id"]),
            )
        return project

    def get_session_project(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT p.* FROM sessions s
                   JOIN projects p ON p.id = s.project_id
                   WHERE s.id = ? AND p.archived_at IS NULL""",
                (session_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_call_id: str = None,
        tool_calls: str = None,
    ) -> None:
        """添加消息（兼容旧 db.add_message 签名）。"""
        # 自动创建会话
        self.get_or_create_session(session_id)
        metadata = {}
        if tool_call_id:
            metadata["tool_call_id"] = tool_call_id
        if tool_calls:
            metadata["tool_calls"] = tool_calls
        self.sessions.add_message(session_id, role, content, metadata=metadata or None)

    def get_messages(self, session_id: str, limit: int = 30, offset: int = 0) -> List[Dict[str, Any]]:
        """获取消息列表（按时间正序），返回 dict 格式（兼容旧 db.get_messages）。"""
        msgs = self.sessions.get_messages(session_id, limit=limit, offset=offset)
        result = []
        for m in msgs:
            metadata = m.metadata or {}
            result.append({
                "role": m.role,
                "content": m.content or "",
                "tool_call_id": metadata.get("tool_call_id"),
                "tool_calls": metadata.get("tool_calls"),
                "created_at": str(m.created_at),
            })
        return result

    def get_visible_messages(self, session_id: str, limit: int = 30, offset: int = 0) -> List[Dict[str, Any]]:
        """获取用户可见消息，过滤内部 system prompt。"""
        safe_limit = max(1, min(int(limit or 30), 500))
        safe_offset = max(0, int(offset or 0))
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM messages
                   WHERE session_id = ? AND role != 'system'
                   ORDER BY created_at DESC
                   LIMIT ? OFFSET ?""",
                (session_id, safe_limit, safe_offset),
            )
            rows = list(cursor.fetchall())
        rows.reverse()
        result = []
        for row in rows:
            metadata = json.loads(row["metadata"] or "{}")
            result.append({
                "role": row["role"],
                "content": row["content"] or "",
                "tool_call_id": metadata.get("tool_call_id"),
                "tool_calls": metadata.get("tool_calls"),
                "created_at": str(row["created_at"]),
            })
        return result

    def count_messages(self, session_id: str) -> int:
        """获取会话消息总数。"""
        return self.sessions.count_messages(session_id)

    def count_visible_messages(self, session_id: str) -> int:
        """获取用户可见消息总数，过滤内部 system prompt。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role != 'system'",
                (session_id,),
            )
            return int(cursor.fetchone()[0] or 0)

    def list_sessions(self, limit: int = 50, offset: int = 0, project_id: Optional[str] = None) -> tuple[List[Dict[str, Any]], int]:
        """列出有消息的会话摘要，支持分页。

        只返回列表页需要的轻量字段，避免历史会话增长后一次性扫描并
        hydrate 全量数据。
        """
        safe_limit = max(1, min(int(limit or 50), 200))
        safe_offset = max(0, int(offset or 0))
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            filters = ["EXISTS (SELECT 1 FROM messages m WHERE m.session_id = s.id AND m.role != 'system')"]
            params: list[Any] = []
            if project_id:
                filters.append("s.project_id = ?")
                params.append(project_id)
            where_clause = " AND ".join(filters)
            cursor.execute(f'''
                SELECT COUNT(*) as total
                FROM sessions s
                WHERE {where_clause}
            ''', params)
            total = int(cursor.fetchone()["total"] or 0)
            cursor.execute(f'''
                SELECT s.id as session_id, s.created_at, s.updated_at,
                       s.title as name, s.project_id, s.project_dir, s.is_pinned, s.pinned_at,
                       (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id AND m.role != 'system') as message_count,
                       (SELECT m2.content FROM messages m2
                        WHERE m2.session_id = s.id AND m2.role = 'user'
                        ORDER BY m2.created_at ASC LIMIT 1) as first_user_message
                FROM sessions s
                WHERE {where_clause}
                ORDER BY s.is_pinned DESC, s.pinned_at DESC, s.updated_at DESC
                LIMIT ? OFFSET ?
            ''', [*params, safe_limit, safe_offset])
            return [dict(r) for r in cursor.fetchall()], total

    def clear_session(self, session_id: str) -> None:
        """删除会话及所有消息。"""
        self.sessions.delete_session(session_id)

    def rename_session(self, session_id: str, name: str) -> None:
        """重命名会话。"""
        self.sessions.update_session(session_id, title=name)

    def update_system_message(self, session_id: str, new_content: str) -> bool:
        """更新会话的第一条系统消息。"""
        return self.sessions.update_system_message(session_id, new_content)

    # ──────────────────────────────────────────
    # 审计日志（兼容旧 db 签名）
    # ──────────────────────────────────────────

    def add_audit_log(
        self,
        session_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        risk_level: str,
        decision: str,
    ) -> None:
        """记录审计日志（兼容旧 db.add_audit_log 签名）。"""
        self.audit.log_tool_call(
            task_id=f"session-{session_id[:8]}",
            tool_name=tool_name,
            risk_level=risk_level,
            params=tool_args or {},
        )
        self.audit.log_approval_decision(
            request_id=f"auto-{session_id[:8]}",
            decision=decision,
            details={"tool_args": tool_args, "session_id": session_id},
        )

    def record_approval_receipt(
        self,
        *,
        subject_type: str,
        subject_id: str,
        subject_payload: Dict[str, Any],
        scope: str,
        decision: str,
        proposer_id: str,
        approver_id: str,
        risk_level: str = "unknown",
        request_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        subject_sha256: Optional[str] = None,
    ) -> Dict[str, Any]:
        receipt = self.approval_receipts.record(
            subject=ApprovalReceiptSubject(
                subject_type=subject_type,
                subject_id=subject_id,
                payload=subject_payload,
                subject_sha256=subject_sha256,
            ),
            scope=scope,
            decision=decision,
            proposer_id=proposer_id,
            approver_id=approver_id,
            risk_level=risk_level,
            request_id=request_id,
            idempotency_key=idempotency_key,
        )
        chain_status = self.approval_receipts.verify_chain()["integrity_status"]
        receipt_status = receipt.get("integrity_status")
        return {
            **receipt,
            "receipt_integrity_status": receipt_status,
            "chain_integrity_status": chain_status,
            "integrity_status": (
                "verified"
                if receipt_status == "verified" and chain_status == "verified"
                else "tampered"
            ),
        }

    # ──────────────────────────────────────────
    # 工具授权（兼容旧 db 签名）
    # ──────────────────────────────────────────

    def get_tool_authorization(self, tool_name: str) -> bool:
        """检查工具是否始终允许。"""
        return self.permissions.is_always_allowed(tool_name)

    def set_tool_authorization(self, tool_name: str, is_always_allowed: bool) -> None:
        """设置/取消工具的始终允许状态。"""
        if is_always_allowed:
            self.permissions.grant_always_allow(tool_name)
        else:
            self.permissions.revoke_permission(tool_name)

    def get_all_authorizations(self) -> List[Dict[str, Any]]:
        """获取所有授权记录（兼容旧 db.get_all_authorizations）。"""
        allowed = self.permissions.list_always_allowed()
        return [
            {"tool_name": name, "is_always_allowed": True, "updated_at": ""}
            for name in allowed
        ]

    def list_permissions(self) -> List[Dict[str, Any]]:
        """获取所有权限记录的详细信息（含 granted_at）。"""
        return self.permissions.list_permissions()

    # ──────────────────────────────────────────
    # 数据迁移
    # ──────────────────────────────────────────

    def _auto_migrate(self) -> None:
        """启动时自动检测并迁移旧数据。"""
        try:
            if self.db.has_old_schema():
                count = self.db.migrate_from_old(self.db_path)
                if count > 0:
                    logger.info(f"Migrated {count} old records to new schema")
        except Exception as e:
            logger.warning(f"Migration skipped: {e}")

# 全局单例（替换 db/database.py 的 db 单例）
persistence = PersistenceService()
