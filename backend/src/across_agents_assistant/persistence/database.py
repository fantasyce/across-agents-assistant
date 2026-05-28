import json
import sqlite3
import os
import uuid
import logging
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger("across_agents_assistant.persistence.database")


class Database:
    """SQLite 数据库连接管理器"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_dir()

    def _ensure_dir(self):
        dir_path = os.path.dirname(self.db_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=OFF")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self):
        """初始化数据库 schema。如果旧格式表存在，会被重命名并重建。"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 如果旧格式表存在 → 先尝试安全重建
            if self._needs_rebuild(cursor, "audit_logs", ["event_type"]):
                logger.info("Detected old-style audit_logs table, rebuilding schema")
                self._rebuild_tables(cursor)

            # 会话表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    project_id TEXT,
                    project_dir TEXT,
                    is_pinned INTEGER DEFAULT 0,
                    pinned_at TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    path TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL DEFAULT 'folder',
                    is_pinned INTEGER DEFAULT 0,
                    pinned_at TEXT,
                    archived_at TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 消息表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 审计日志表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    event_type TEXT,
                    session_id TEXT,
                    task_id TEXT,
                    tool_name TEXT,
                    risk_level TEXT,
                    decision TEXT,
                    details TEXT
                )
            ''')

            # 工具权限表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tool_permissions (
                    id TEXT PRIMARY KEY,
                    tool_name TEXT UNIQUE,
                    permission_type TEXT,
                    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    granted_by TEXT
                )
            ''')

            # 任务表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    task_type TEXT DEFAULT 'unknown',
                    status TEXT DEFAULT 'created',
                    project_dir TEXT,
                    error TEXT,
                    can_handle_directly INTEGER DEFAULT 0,
                    direct_response TEXT,
                    progress REAL DEFAULT 0.0,
                    completed_count INTEGER DEFAULT 0,
                    total_count INTEGER DEFAULT 0,
                    owner_agent TEXT,
                    allowed_subtask_agents TEXT,
                    owner_session_id TEXT,
                    owner_state_summary TEXT,
                    last_owner_decision TEXT,
                    task_types TEXT,
                    delivery_mode TEXT DEFAULT 'legacy',
                    is_paused INTEGER DEFAULT 0,
                    created_at REAL,
                    updated_at REAL
                )
            ''')

            # 子任务表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subtasks (
                    subtask_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    description TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    priority INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'pending',
                    progress REAL DEFAULT 0.0,
                    wave_number INTEGER DEFAULT 1,
                    dependencies TEXT,
                    error_message TEXT,
                    output_file TEXT,
                    duration REAL,
                    fix_plan TEXT,
                    is_fix_round INTEGER DEFAULT 0,
                    original_subtask_id TEXT,
                    created_at REAL,
                    updated_at REAL,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                )
            ''')

            # 作业表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    subtask_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    task_description TEXT,
                    status TEXT DEFAULT 'pending',
                    progress REAL DEFAULT 0.0,
                    result TEXT,
                    error TEXT,
                    logs TEXT,
                    created_at REAL,
                    started_at REAL,
                    completed_at REAL,
                    attempt INTEGER DEFAULT 0,
                    pinned_session_id TEXT,
                    failure_reason TEXT,
                    FOREIGN KEY (subtask_id) REFERENCES subtasks(subtask_id) ON DELETE CASCADE
                )
            ''')

            # Wave 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS waves (
                    wave_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    wave_number INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',
                    is_blocked INTEGER DEFAULT 0,
                    governance_status TEXT DEFAULT 'pending',
                    blocked_by_wave INTEGER,
                    is_revalidating INTEGER DEFAULT 0,
                    owner_decision TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                )
            ''')

            # 任务事件表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS task_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    subtask_id TEXT,
                    job_id TEXT,
                    data TEXT,
                    created_at REAL,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                )
            ''')

            # Fix rounds 表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fix_rounds (
                    fix_round_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    original_subtask_id TEXT NOT NULL,
                    fix_subtask_id TEXT NOT NULL,
                    round_number INTEGER NOT NULL,
                    status TEXT,
                    created_at REAL,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                )
            ''')

            # 产物表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    subtask_id TEXT,
                    file_name TEXT,
                    file_path TEXT,
                    file_size TEXT,
                    created_at REAL,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                )
            ''')

            # 任务契约表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS task_contracts (
                    contract_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    subtask_id TEXT,
                    wave_number INTEGER,
                    level TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    input_artifact_ids TEXT,
                    expected_deliverables TEXT,
                    acceptance_checks TEXT,
                    project_dir TEXT,
                    context_mode TEXT DEFAULT 'summary',
                    created_at REAL,
                    updated_at REAL,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                )
            ''')

            # 结构化产物记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS artifact_records (
                    artifact_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    subtask_id TEXT,
                    wave_number INTEGER,
                    name TEXT,
                    artifact_type TEXT NOT NULL,
                    version INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'accepted',
                    content_ref TEXT NOT NULL,
                    produced_by TEXT NOT NULL,
                    schema_version TEXT DEFAULT '1.0',
                    metadata TEXT,
                    source_artifact_ids TEXT,
                    supersedes_artifact_id TEXT,
                    superseded_by_artifact_id TEXT,
                    created_at REAL,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                )
            ''')

            # 验收记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS acceptance_records (
                    acceptance_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    subtask_id TEXT,
                    wave_number INTEGER,
                    level TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    deterministic_passed INTEGER DEFAULT 0,
                    judge_passed INTEGER DEFAULT 0,
                    failed_checks TEXT,
                    missing_artifacts TEXT,
                    feedback TEXT,
                    root_cause_scope TEXT DEFAULT 'unknown',
                    root_cause_wave INTEGER,
                    root_cause_artifact_ids TEXT,
                    recommended_action TEXT DEFAULT 'approve',
                    preferred_agent TEXT,
                    owner_session_id TEXT,
                    created_at REAL,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                )
            ''')

            # Requirement manifests for delivery-quality tracking (Phase 1)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS requirement_manifests (
                    manifest_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    project_dir TEXT,
                    deliverables TEXT NOT NULL,
                    quality_checks TEXT NOT NULL,
                    created_at REAL,
                    updated_at REAL,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                )
            ''')

            # Owner Delivery Contracts
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS delivery_contracts (
                    contract_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    contract_version TEXT DEFAULT '1.0',
                    task_types TEXT NOT NULL,
                    delivery_mode TEXT NOT NULL,
                    delivery_facets TEXT DEFAULT '[]',
                    technology_hypotheses TEXT DEFAULT '[]',
                    capabilities TEXT NOT NULL,
                    deliverables TEXT NOT NULL,
                    deliverable_groups TEXT DEFAULT '[]',
                    constraints_json TEXT NOT NULL,
                    acceptance_probes TEXT NOT NULL,
                    gate_plan TEXT DEFAULT '[]',
                    assumptions TEXT NOT NULL,
                    project_dir TEXT,
                    created_at REAL,
                    updated_at REAL,
                    FOREIGN KEY (task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
                )
            ''')

            # Additive migrations for existing databases so startup stays compatible
            self._ensure_column(cursor, "sessions", "project_id", "TEXT")
            self._ensure_column(cursor, "sessions", "project_dir", "TEXT")
            self._ensure_column(cursor, "sessions", "is_pinned", "INTEGER DEFAULT 0")
            self._ensure_column(cursor, "sessions", "pinned_at", "TEXT")
            self._ensure_column(cursor, "projects", "pinned_at", "TEXT")
            self._ensure_column(cursor, "tasks", "allowed_subtask_agents", "TEXT")
            self._ensure_column(cursor, "tasks", "owner_session_id", "TEXT")
            self._ensure_column(cursor, "tasks", "owner_state_summary", "TEXT")
            self._ensure_column(cursor, "tasks", "last_owner_decision", "TEXT")
            self._ensure_column(cursor, "tasks", "task_types", "TEXT")
            self._ensure_column(cursor, "tasks", "delivery_mode", "TEXT DEFAULT 'legacy'")
            self._ensure_column(cursor, "delivery_contracts", "contract_version", "TEXT DEFAULT '1.0'")
            self._ensure_column(cursor, "delivery_contracts", "delivery_facets", "TEXT DEFAULT '[]'")
            self._ensure_column(cursor, "delivery_contracts", "technology_hypotheses", "TEXT DEFAULT '[]'")
            self._ensure_column(cursor, "delivery_contracts", "deliverable_groups", "TEXT DEFAULT '[]'")
            self._ensure_column(cursor, "delivery_contracts", "gate_plan", "TEXT DEFAULT '[]'")
            self._ensure_column(cursor, "waves", "governance_status", "TEXT DEFAULT 'pending'")
            self._ensure_column(cursor, "waves", "blocked_by_wave", "INTEGER")
            self._ensure_column(cursor, "waves", "is_revalidating", "INTEGER DEFAULT 0")
            self._ensure_column(cursor, "waves", "owner_decision", "TEXT")
            self._ensure_column(cursor, "artifact_records", "source_artifact_ids", "TEXT")
            self._ensure_column(cursor, "artifact_records", "supersedes_artifact_id", "TEXT")
            self._ensure_column(cursor, "artifact_records", "superseded_by_artifact_id", "TEXT")
            self._ensure_column(cursor, "acceptance_records", "root_cause_scope", "TEXT DEFAULT 'unknown'")
            self._ensure_column(cursor, "acceptance_records", "root_cause_wave", "INTEGER")
            self._ensure_column(cursor, "acceptance_records", "root_cause_artifact_ids", "TEXT")
            self._ensure_column(cursor, "acceptance_records", "recommended_action", "TEXT DEFAULT 'approve'")
            self._ensure_column(cursor, "acceptance_records", "preferred_agent", "TEXT")
            self._ensure_column(cursor, "acceptance_records", "owner_session_id", "TEXT")

            # Indices
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_messages_session_created '
                'ON messages(session_id, created_at)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_sessions_project_updated '
                'ON sessions(project_id, is_pinned DESC, pinned_at DESC, updated_at DESC)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_sessions_project_pinned_updated '
                'ON sessions(project_id, is_pinned DESC, pinned_at DESC, updated_at DESC)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_projects_updated '
                'ON projects(is_pinned DESC, pinned_at DESC, last_opened_at DESC, updated_at DESC)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_projects_pinned_updated '
                'ON projects(is_pinned DESC, pinned_at DESC, last_opened_at DESC, updated_at DESC)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_audit_logs_event ON audit_logs(event_type)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_subtasks_task ON subtasks(task_id)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_subtasks_wave ON subtasks(task_id, wave_number)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_jobs_subtask ON jobs(subtask_id)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_waves_task ON waves(task_id)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_fix_rounds_task ON fix_rounds(task_id)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_artifacts_task ON artifacts(task_id)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_task_contracts_task ON task_contracts(task_id)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_task_contracts_subtask ON task_contracts(subtask_id)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_artifact_records_task ON artifact_records(task_id)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_artifact_records_subtask ON artifact_records(subtask_id)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_acceptance_records_task ON acceptance_records(task_id)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_acceptance_records_subtask ON acceptance_records(subtask_id)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_delivery_contracts_task ON delivery_contracts(task_id)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_tasks_updated_created '
                'ON tasks(updated_at DESC, created_at DESC)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_subtasks_task_created '
                'ON subtasks(task_id, created_at)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_jobs_subtask_created '
                'ON jobs(subtask_id, created_at)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_waves_task_number '
                'ON waves(task_id, wave_number)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_task_events_task_created '
                'ON task_events(task_id, created_at DESC)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_fix_rounds_task_round '
                'ON fix_rounds(task_id, round_number)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_artifacts_task_created '
                'ON artifacts(task_id, created_at)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_task_contracts_task_level_created '
                'ON task_contracts(task_id, level, created_at)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_artifact_records_task_created '
                'ON artifact_records(task_id, created_at)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_acceptance_records_task_created '
                'ON acceptance_records(task_id, created_at)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_requirement_manifests_task '
                'ON requirement_manifests(task_id)'
            )
            cursor.execute(
                'CREATE INDEX IF NOT EXISTS idx_delivery_contracts_task_updated '
                'ON delivery_contracts(task_id, updated_at DESC)'
            )

            # 凭证元数据表（仅记录元数据，不含 API key）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS credential_metadata (
                    provider_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    is_configured INTEGER NOT NULL DEFAULT 0,
                    last_loaded_at REAL,
                    last_updated_at REAL,
                    last_error TEXT
                )
            ''')

    # ── Schema detection & rebuild ──

    def _needs_rebuild(self, cursor, table: str, required_cols: list) -> bool:
        """检查表是否需要重建（缺少必要列）。"""
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        if not cursor.fetchone():
            return False
        cursor.execute(f"PRAGMA table_info({table})")
        existing = {row['name'] for row in cursor.fetchall()}
        return any(col not in existing for col in required_cols)

    def _ensure_column(self, cursor, table: str, column: str, definition: str) -> None:
        cursor.execute(f"PRAGMA table_info({table})")
        existing = {row['name'] for row in cursor.fetchall()}
        if column not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _rebuild_tables(self, cursor):
        """重建所有表以匹配新 schema。重命名旧表，创建新表。"""
        tables = {
            "sessions": '''
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, title TEXT, project_id TEXT, project_dir TEXT,
                    is_pinned INTEGER DEFAULT 0, pinned_at TEXT, metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
            ''',
            "projects": '''
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL DEFAULT 'folder', is_pinned INTEGER DEFAULT 0,
                    pinned_at TEXT, archived_at TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
            ''',
            "messages": '''
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY, session_id TEXT, role TEXT,
                    content TEXT, metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)
            ''',
            "audit_logs": '''
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    event_type TEXT, session_id TEXT, task_id TEXT,
                    tool_name TEXT, risk_level TEXT, decision TEXT, details TEXT)
            ''',
            "tool_permissions": '''
                CREATE TABLE IF NOT EXISTS tool_permissions (
                    id TEXT PRIMARY KEY, tool_name TEXT UNIQUE,
                    permission_type TEXT, granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    granted_by TEXT)
            ''',
        }
        for name, ddl in tables.items():
            cursor.execute(f"DROP TABLE IF EXISTS _{name}")
            # 检查表是否存在再重命名
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (name,)
            )
            if cursor.fetchone():
                cursor.execute(f"ALTER TABLE {name} RENAME TO _{name}")
            cursor.execute(ddl)

    # ── Old schema detection & migration ──

    def has_old_schema(self) -> bool:
        """检测旧 db/database.py 的表是否存在。"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tool_authorizations'"
            )
            return cursor.fetchone() is not None

    def _get_old_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _read_old_table(self, conn, table: str):
        try:
            return [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]
        except Exception:
            return []

    def migrate_from_old(self, old_db_path: str) -> int:
        """从旧 schema 迁移数据到新 schema。返回迁移记录数。"""
        if not os.path.exists(old_db_path):
            return 0

        old_conn = self._get_old_conn()
        total = 0

        try:
            cursor = old_conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing = {row["name"] for row in cursor.fetchall()}

            with self.get_connection() as conn:
                new_cursor = conn.cursor()

                # 迁移 sessions
                if "sessions" in existing:
                    for row in self._read_old_table(old_conn, "sessions"):
                        title = row.get("name") or ""
                        new_cursor.execute(
                            """INSERT OR IGNORE INTO sessions
                               (id, title, metadata, created_at, updated_at)
                               VALUES (?, ?, ?, ?, ?)""",
                            (row["id"], title, "{}", row["created_at"],
                             row["updated_at"]),
                        )
                        total += 1

                # 迁移 messages
                if "messages" in existing:
                    for row in self._read_old_table(old_conn, "messages"):
                        new_id = f"msg-{uuid.uuid4().hex[:12]}"
                        metadata = {}
                        if row.get("tool_call_id"):
                            metadata["tool_call_id"] = row["tool_call_id"]
                        if row.get("tool_calls"):
                            metadata["tool_calls"] = row["tool_calls"]
                        new_cursor.execute(
                            """INSERT OR IGNORE INTO messages
                               (id, session_id, role, content, metadata, created_at)
                               VALUES (?, ?, ?, ?, ?, ?)""",
                            (new_id, row["session_id"], row["role"],
                             row["content"], json.dumps(metadata),
                             row["created_at"]),
                        )
                        total += 1

                # 迁移 audit_logs
                if "audit_logs" in existing:
                    for row in self._read_old_table(old_conn, "audit_logs"):
                        new_id = f"log-{uuid.uuid4().hex[:12]}"
                        details = {}
                        if row.get("tool_args"):
                            try:
                                details = json.loads(row["tool_args"])
                            except (json.JSONDecodeError, TypeError):
                                details = {"raw_args": row["tool_args"]}
                        new_cursor.execute(
                            """INSERT OR IGNORE INTO audit_logs
                               (id, timestamp, event_type, session_id,
                                tool_name, risk_level, decision, details)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                            (new_id, row["created_at"], "tool_call",
                             row["session_id"], row["tool_name"],
                             row["risk_level"], row["decision"],
                             json.dumps(details)),
                        )
                        total += 1

                # 迁移 tool_authorizations
                if "tool_authorizations" in existing:
                    for row in self._read_old_table(old_conn, "tool_authorizations"):
                        new_id = f"perm-{uuid.uuid4().hex[:12]}"
                        perm_type = "always_allow" if row.get(
                            "is_always_allowed"
                        ) else None
                        if perm_type:
                            new_cursor.execute(
                                """INSERT OR IGNORE INTO tool_permissions
                                   (id, tool_name, permission_type, granted_at)
                                   VALUES (?, ?, ?, ?)""",
                                (new_id, row["tool_name"], perm_type,
                                 row.get("created_at")),
                            )
                            total += 1

        finally:
            old_conn.close()

        return total
