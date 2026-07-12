import json
import logging
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

from .database import Database

logger = logging.getLogger("across_agents_assistant.persistence.task")


class TaskPersistenceService:
    """任务持久化服务。

    封装所有任务相关的数据库操作，包括任务、子任务、作业、wave、事件等。
    """

    def __init__(self, db: Database):
        self.db = db

    # ── Task CRUD ──

    def save_task(self, task: Dict[str, Any]) -> None:
        """保存或更新任务。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO tasks (
                    task_id, description, task_type, status, project_dir, error,
                    can_handle_directly, direct_response, progress,
                    completed_count, total_count, owner_agent, owner_session_id,
                    allowed_subtask_agents, owner_state_summary, last_owner_decision,
                    task_types, delivery_mode,
                    is_paused, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                task['task_id'],
                task['description'],
                task.get('task_type', 'unknown'),
                task.get('status', 'created'),
                task.get('project_dir'),
                task.get('error'),
                1 if task.get('can_handle_directly') else 0,
                task.get('direct_response'),
                task.get('progress', 0.0),
                task.get('completed_count', 0),
                task.get('total_count', 0),
                task.get('owner_agent'),
                task.get('owner_session_id'),
                json.dumps(task.get('allowed_subtask_agents', [])),
                json.dumps(task.get('owner_state_summary', {})),
                json.dumps(task.get('last_owner_decision', {})),
                json.dumps(task.get('task_types', [])),
                task.get('delivery_mode', 'external'),
                1 if task.get('is_paused') else 0,
                task.get('created_at'),
                task.get('updated_at')
            ))

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务详情。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tasks WHERE task_id = ?', (task_id,))
            row = cursor.fetchone()
            if not row:
                return None
            item = dict(row)
            for key in ('owner_state_summary', 'last_owner_decision'):
                try:
                    item[key] = json.loads(item[key]) if item.get(key) else {}
                except json.JSONDecodeError:
                    item[key] = {}
            for key in ('allowed_subtask_agents', 'task_types'):
                try:
                    item[key] = json.loads(item[key]) if item.get(key) else []
                except json.JSONDecodeError:
                    item[key] = []
            item['delivery_mode'] = item.get('delivery_mode') or 'external'
            return item

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """获取所有任务。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tasks ORDER BY created_at DESC')
            result = []
            for row in cursor.fetchall():
                item = dict(row)
                for key in ('owner_state_summary', 'last_owner_decision'):
                    try:
                        item[key] = json.loads(item[key]) if item.get(key) else {}
                    except json.JSONDecodeError:
                        item[key] = {}
                for key in ('allowed_subtask_agents', 'task_types'):
                    try:
                        item[key] = json.loads(item[key]) if item.get(key) else []
                    except json.JSONDecodeError:
                        item[key] = []
                item['delivery_mode'] = item.get('delivery_mode') or 'external'
                result.append(item)
            return result

    def get_task_summaries(self, *, limit: int = 50, offset: int = 0) -> tuple[List[Dict[str, Any]], int]:
        """Return lightweight task rows for list views."""
        limit = max(1, min(int(limit or 50), 200))
        offset = max(0, int(offset or 0))
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            total = cursor.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
            cursor.execute(
                '''
                SELECT task_id, description, status, progress, completed_count, total_count,
                       created_at, updated_at, project_dir, owner_agent, allowed_subtask_agents,
                       task_types, delivery_mode, last_owner_decision
                FROM tasks
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ? OFFSET ?
                ''',
                (limit, offset),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            task_ids = [row["task_id"] for row in rows if row.get("task_id")]
            counts = self._get_business_subtask_counts(cursor, task_ids)
            for row in rows:
                completed_count, total_count = counts.get(
                    row.get("task_id"),
                    (int(row.get("completed_count") or 0), int(row.get("total_count") or 0)),
                )
                row["completed_count"] = completed_count
                row["total_count"] = total_count
                row["progress"] = (
                    completed_count / total_count
                    if total_count > 0
                    else float(row.get("progress") or 0)
                )
                try:
                    row["last_owner_decision"] = (
                        json.loads(row["last_owner_decision"])
                        if row.get("last_owner_decision")
                        else {}
                    )
                except json.JSONDecodeError:
                    row["last_owner_decision"] = {}
                for key in ("allowed_subtask_agents", "task_types"):
                    try:
                        row[key] = json.loads(row[key]) if row.get(key) else []
                    except json.JSONDecodeError:
                        row[key] = []
            return rows, int(total or 0)

    def update_task_status(self, task_id: str, status: str, error: str = None) -> None:
        """更新任务状态。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE tasks SET status = ?, error = ?, updated_at = ?
                WHERE task_id = ?
            ''', (status, error, datetime.now().timestamp(), task_id))

    def update_task_progress(self, task_id: str, progress: float,
                            completed_count: int, total_count: int) -> None:
        """更新任务进度。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE tasks SET progress = ?, completed_count = ?,
                    total_count = ?, updated_at = ?
                WHERE task_id = ?
            ''', (progress, completed_count, total_count,
                  datetime.now().timestamp(), task_id))

    def delete_task(self, task_id: str) -> None:
        """删除任务（级联删除子任务、作业等）。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM tasks WHERE task_id = ?', (task_id,))

    # ── Subtask CRUD ──

    def save_subtask(self, subtask: Dict[str, Any]) -> None:
        """保存或更新子任务。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO subtasks (
                    subtask_id, task_id, description, agent_id, priority,
                    status, progress, wave_number, dependencies,
                    error_message, output_file, duration, fix_plan,
                    is_fix_round, original_subtask_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                subtask['subtask_id'],
                subtask['task_id'],
                subtask['description'],
                subtask['agent_id'],
                subtask.get('priority', 1),
                subtask.get('status', 'pending'),
                subtask.get('progress', 0.0),
                subtask.get('wave_number', 1),
                json.dumps(subtask.get('dependencies', [])),
                subtask.get('error_message'),
                subtask.get('output_file'),
                subtask.get('duration'),
                subtask.get('fix_plan'),
                1 if subtask.get('is_fix_round') else 0,
                subtask.get('original_subtask_id'),
                subtask.get('created_at'),
                datetime.now().timestamp()
            ))

    def delete_subtask(self, subtask_id: str) -> None:
        """删除子任务。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM subtasks WHERE subtask_id = ?', (subtask_id,))

    def get_subtasks(self, task_id: str) -> List[Dict[str, Any]]:
        """获取任务的所有子任务。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM subtasks WHERE task_id = ? ORDER BY created_at
            ''', (task_id,))
            rows = cursor.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                if d.get('dependencies'):
                    try:
                        d['dependencies'] = json.loads(d['dependencies'])
                    except json.JSONDecodeError:
                        d['dependencies'] = []
                else:
                    d['dependencies'] = []
                result.append(d)
            return result

    def update_subtask_status(self, subtask_id: str, status: str,
                              progress: float = None, error_message: str = None) -> None:
        """更新子任务状态。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            updates = ['status = ?']
            params = [status]
            if progress is not None:
                updates.append('progress = ?')
                params.append(progress)
            if error_message is not None:
                updates.append('error_message = ?')
                params.append(error_message)
            updates.append('updated_at = ?')
            params.append(datetime.now().timestamp())
            params.append(subtask_id)

            sql = f"UPDATE subtasks SET {', '.join(updates)} WHERE subtask_id = ?"
            cursor.execute(sql, params)

    def update_subtask_output(self, subtask_id: str, output_file: str = None,
                              duration: float = None) -> None:
        """更新子任务输出。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            updates = []
            params = []
            if output_file is not None:
                updates.append('output_file = ?')
                params.append(output_file)
            if duration is not None:
                updates.append('duration = ?')
                params.append(duration)
            if updates:
                updates.append('updated_at = ?')
                params.append(datetime.now().timestamp())
                params.append(subtask_id)
                sql = f"UPDATE subtasks SET {', '.join(updates)} WHERE subtask_id = ?"
                cursor.execute(sql, params)

    # ── Job CRUD ──

    def save_job(self, job: Dict[str, Any]) -> None:
        """保存或更新作业。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO jobs (
                    job_id, subtask_id, agent_id, task_description,
                    status, progress, result, error, logs,
                    created_at, started_at, completed_at, attempt,
                    pinned_session_id, failure_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                job['job_id'],
                job['subtask_id'],
                job['agent_id'],
                job.get('task_description'),
                job.get('status', 'pending'),
                job.get('progress', 0.0),
                job.get('result'),
                job.get('error'),
                json.dumps(job.get('logs', [])),
                job.get('created_at'),
                job.get('started_at'),
                job.get('completed_at'),
                job.get('attempt', 0),
                job.get('pinned_session_id'),
                job.get('failure_reason')
            ))

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """获取作业详情。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM jobs WHERE job_id = ?', (job_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get('logs'):
                try:
                    d['logs'] = json.loads(d['logs'])
                except json.JSONDecodeError:
                    d['logs'] = []
            else:
                d['logs'] = []
            return d

    def get_jobs_by_subtask(self, subtask_id: str) -> List[Dict[str, Any]]:
        """获取子任务的所有作业。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM jobs WHERE subtask_id = ? ORDER BY created_at', (subtask_id,))
            rows = cursor.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                if d.get('logs'):
                    try:
                        d['logs'] = json.loads(d['logs'])
                    except json.JSONDecodeError:
                        d['logs'] = []
                else:
                    d['logs'] = []
                result.append(d)
            return result

    def get_jobs_by_subtasks(self, subtask_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """批量获取多个子任务的 jobs，避免详情页 N+1 查询。"""
        if not subtask_ids:
            return {}
        placeholders = ','.join('?' for _ in subtask_ids)
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f'''
                SELECT * FROM jobs
                WHERE subtask_id IN ({placeholders})
                ORDER BY subtask_id, created_at
                ''',
                tuple(subtask_ids),
            )
            grouped: Dict[str, List[Dict[str, Any]]] = {subtask_id: [] for subtask_id in subtask_ids}
            for row in cursor.fetchall():
                item = self._decode_job_row(row)
                grouped.setdefault(item.get('subtask_id'), []).append(item)
            return grouped

    # ── Wave CRUD ──

    def save_wave(self, wave: Dict[str, Any]) -> None:
        """保存或更新 wave。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO waves (
                    wave_id, task_id, wave_number, status, is_blocked,
                    governance_status, blocked_by_wave, is_revalidating, owner_decision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                wave['wave_id'],
                wave['task_id'],
                wave['wave_number'],
                wave.get('status', 'pending'),
                1 if wave.get('is_blocked') else 0,
                wave.get('governance_status', 'pending'),
                wave.get('blocked_by_wave'),
                1 if wave.get('is_revalidating') else 0,
                json.dumps(wave.get('owner_decision', {})),
            ))

    def get_waves(self, task_id: str) -> List[Dict[str, Any]]:
        """获取任务的所有 waves。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM waves WHERE task_id = ? ORDER BY wave_number
            ''', (task_id,))
            result = []
            for row in cursor.fetchall():
                item = dict(row)
                item['is_blocked'] = bool(item.get('is_blocked'))
                item['is_revalidating'] = bool(item.get('is_revalidating'))
                try:
                    item['owner_decision'] = json.loads(item['owner_decision']) if item.get('owner_decision') else {}
                except json.JSONDecodeError:
                    item['owner_decision'] = {}
                result.append(item)
            return result

    # ── Event Logging ──

    def log_event(self, task_id: str, event_type: str,
                  subtask_id: str = None, job_id: str = None,
                  data: Dict[str, Any] = None) -> None:
        """记录任务事件。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO task_events (task_id, event_type, subtask_id, job_id, data, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (task_id, event_type, subtask_id, job_id,
                  json.dumps(data) if data else None,
                  datetime.now().timestamp()))

    def get_events(self, task_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取任务事件。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM task_events
                WHERE task_id = ? ORDER BY created_at DESC LIMIT ?
            ''', (task_id, limit))
            rows = cursor.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                if d.get('data'):
                    try:
                        d['data'] = json.loads(d['data'])
                    except json.JSONDecodeError:
                        d['data'] = {}
                result.append(d)
            return result

    # ── Fix Round ──

    def save_fix_round(self, fix_round: Dict[str, Any]) -> None:
        """保存 fix round 记录。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO fix_rounds (task_id, original_subtask_id, fix_subtask_id,
                                       round_number, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                fix_round['task_id'],
                fix_round['original_subtask_id'],
                fix_round['fix_subtask_id'],
                fix_round['round_number'],
                fix_round.get('status'),
                datetime.now().timestamp()
            ))

    def get_fix_rounds(self, task_id: str) -> List[Dict[str, Any]]:
        """获取任务的 fix rounds。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM fix_rounds WHERE task_id = ? ORDER BY round_number
            ''', (task_id,))
            return [dict(r) for r in cursor.fetchall()]

    # ── Artifact ──

    def save_artifact(self, artifact: Dict[str, Any]) -> None:
        """保存产物。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO artifacts (
                    artifact_id, task_id, subtask_id, file_name, file_path, file_size, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                artifact['artifact_id'],
                artifact['task_id'],
                artifact.get('subtask_id'),
                artifact.get('file_name'),
                artifact.get('file_path'),
                artifact.get('file_size'),
                artifact.get('created_at', datetime.now().timestamp())
            ))

    def get_artifacts(self, task_id: str) -> List[Dict[str, Any]]:
        """获取任务的产物。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM artifacts WHERE task_id = ?', (task_id,))
            return [dict(r) for r in cursor.fetchall()]

    def save_task_contract(self, contract: Dict[str, Any]) -> None:
        """保存或更新任务契约。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO task_contracts (
                    contract_id, task_id, subtask_id, wave_number, level, goal,
                    input_artifact_ids, expected_deliverables, acceptance_checks,
                    project_dir, context_mode, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                contract['contract_id'],
                contract['task_id'],
                contract.get('subtask_id'),
                contract.get('wave_number'),
                contract['level'],
                contract['goal'],
                json.dumps(contract.get('input_artifact_ids', [])),
                json.dumps(contract.get('expected_deliverables', [])),
                json.dumps(contract.get('acceptance_checks', [])),
                contract.get('project_dir'),
                contract.get('context_mode', 'summary'),
                contract.get('created_at', datetime.now().timestamp()),
                contract.get('updated_at', datetime.now().timestamp()),
            ))

    def get_task_contracts(self, task_id: str) -> List[Dict[str, Any]]:
        """获取任务的所有契约。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM task_contracts
                WHERE task_id = ?
                ORDER BY level, created_at
            ''', (task_id,))
            rows = cursor.fetchall()
            result = []
            for row in rows:
                item = dict(row)
                for key in ('input_artifact_ids', 'expected_deliverables', 'acceptance_checks'):
                    try:
                        item[key] = json.loads(item[key]) if item.get(key) else []
                    except json.JSONDecodeError:
                        item[key] = []
                result.append(item)
            return result

    def save_artifact_record(self, artifact: Dict[str, Any]) -> None:
        """保存结构化产物记录。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO artifact_records (
                    artifact_id, task_id, subtask_id, wave_number, name, artifact_type,
                    version, status, content_ref, produced_by, schema_version, metadata,
                    source_artifact_ids, supersedes_artifact_id, superseded_by_artifact_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                artifact['artifact_id'],
                artifact['task_id'],
                artifact.get('subtask_id'),
                artifact.get('wave_number'),
                artifact.get('name'),
                artifact['artifact_type'],
                artifact.get('version', 1),
                artifact.get('status', 'accepted'),
                artifact['content_ref'],
                artifact['produced_by'],
                artifact.get('schema_version', '1.0'),
                json.dumps(artifact.get('metadata', {})),
                json.dumps(artifact.get('source_artifact_ids', [])),
                artifact.get('supersedes_artifact_id'),
                artifact.get('superseded_by_artifact_id'),
                artifact.get('created_at', datetime.now().timestamp()),
            ))

    def get_artifact_records(self, task_id: str) -> List[Dict[str, Any]]:
        """获取任务的结构化产物记录。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM artifact_records
                WHERE task_id = ?
                ORDER BY created_at
            ''', (task_id,))
            rows = cursor.fetchall()
            result = []
            for row in rows:
                item = dict(row)
                try:
                    item['metadata'] = json.loads(item['metadata']) if item.get('metadata') else {}
                except json.JSONDecodeError:
                    item['metadata'] = {}
                for key in ('source_artifact_ids',):
                    try:
                        item[key] = json.loads(item[key]) if item.get(key) else []
                    except json.JSONDecodeError:
                        item[key] = []
                result.append(item)
            return result

    def update_artifact_records_for_subtask(
        self,
        task_id: str,
        subtask_id: str,
        status: str,
        current_status: Optional[str] = None,
    ) -> None:
        """批量更新某个子任务的产物状态。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            updates = ['status = ?']
            params: List[Any] = [status]
            cursor.execute(
                'PRAGMA table_info(artifact_records)'
            )
            column_names = {row[1] for row in cursor.fetchall()}
            if 'created_at' in column_names:
                updates.append('created_at = ?')
                params.append(datetime.now().timestamp())
            params.extend([task_id, subtask_id])
            sql = f"UPDATE artifact_records SET {', '.join(updates)} WHERE task_id = ? AND subtask_id = ?"
            if current_status:
                sql += ' AND status = ?'
                params.append(current_status)
            cursor.execute(sql, params)

    def save_acceptance_record(self, record: Dict[str, Any]) -> None:
        """保存验收记录。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO acceptance_records (
                    acceptance_id, task_id, subtask_id, wave_number, level, decision,
                    deterministic_passed, judge_passed, failed_checks,
                    missing_artifacts, feedback, root_cause_scope, root_cause_wave,
                    root_cause_artifact_ids, recommended_action, preferred_agent,
                    owner_session_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record['acceptance_id'],
                record['task_id'],
                record.get('subtask_id'),
                record.get('wave_number'),
                record['level'],
                record['decision'],
                1 if record.get('deterministic_passed') else 0,
                1 if record.get('judge_passed') else 0,
                json.dumps(record.get('failed_checks', [])),
                json.dumps(record.get('missing_artifacts', [])),
                record.get('feedback'),
                record.get('root_cause_scope', 'unknown'),
                record.get('root_cause_wave'),
                json.dumps(record.get('root_cause_artifact_ids', [])),
                record.get('recommended_action', 'approve'),
                record.get('preferred_agent'),
                record.get('owner_session_id'),
                record.get('created_at', datetime.now().timestamp()),
            ))

    def get_acceptance_records(self, task_id: str) -> List[Dict[str, Any]]:
        """获取任务的验收记录。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM acceptance_records
                WHERE task_id = ?
                ORDER BY created_at
            ''', (task_id,))
            rows = cursor.fetchall()
            result = []
            for row in rows:
                item = dict(row)
                for key in ('failed_checks', 'missing_artifacts', 'root_cause_artifact_ids'):
                    try:
                        item[key] = json.loads(item[key]) if item.get(key) else []
                    except json.JSONDecodeError:
                        item[key] = []
                item['deterministic_passed'] = bool(item.get('deterministic_passed'))
                item['judge_passed'] = bool(item.get('judge_passed'))
                result.append(item)
            return result

    def save_task_user_review(
        self,
        task_id: str,
        review_status: str,
        *,
        accepted_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Persist the user's final review independently of task ownership."""
        normalized_status = str(review_status or "").strip().lower()
        if normalized_status not in {"pending", "accepted"}:
            raise ValueError(f"Unsupported task review status: {review_status}")
        now = datetime.now().timestamp()
        confirmed_at = accepted_at if normalized_status == "accepted" else None
        if normalized_status == "accepted" and confirmed_at is None:
            confirmed_at = now
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT INTO task_user_reviews (task_id, review_status, accepted_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    review_status = excluded.review_status,
                    accepted_at = excluded.accepted_at,
                    updated_at = excluded.updated_at
                ''',
                (task_id, normalized_status, confirmed_at, now),
            )
        return self.get_task_user_review(task_id) or {
            "task_id": task_id,
            "review_status": normalized_status,
            "accepted_at": confirmed_at,
            "updated_at": now,
        }

    def get_task_user_review(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                SELECT task_id, review_status, accepted_at, updated_at
                FROM task_user_reviews
                WHERE task_id = ?
                ''',
                (task_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    # ── Requirement Manifest (Phase 1) ──

    def save_requirement_manifest(self, manifest: Dict[str, Any]) -> None:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO requirement_manifests (
                    manifest_id, task_id, project_dir, deliverables,
                    quality_checks, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest["manifest_id"],
                    manifest["task_id"],
                    manifest.get("project_dir"),
                    json.dumps(manifest.get("deliverables", [])),
                    json.dumps(manifest.get("quality_checks", [])),
                    manifest.get("created_at"),
                    manifest.get("updated_at"),
                ),
            )

    def get_requirement_manifest(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM requirement_manifests WHERE task_id = ?",
                (task_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            item = dict(row)
            item["deliverables"] = json.loads(item.get("deliverables") or "[]")
            item["quality_checks"] = json.loads(item.get("quality_checks") or "[]")
            return item

    # ── Owner Delivery Contract ──

    def save_delivery_contract(self, contract: Dict[str, Any]) -> None:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO delivery_contracts (
                    contract_id, task_id, contract_version, task_types, delivery_mode,
                    delivery_facets, technology_hypotheses, capabilities, deliverables,
                    deliverable_groups, constraints_json, acceptance_probes, gate_plan,
                    assumptions, project_dir, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                contract['contract_id'],
                contract['task_id'],
                contract.get('contract_version', '1.0'),
                json.dumps(contract.get('task_types', [])),
                contract.get('delivery_mode', 'external'),
                json.dumps(contract.get('delivery_facets', [])),
                json.dumps(contract.get('technology_hypotheses', [])),
                json.dumps(contract.get('capabilities', [])),
                json.dumps(contract.get('deliverables', [])),
                json.dumps(contract.get('deliverable_groups', [])),
                json.dumps(contract.get('constraints', [])),
                json.dumps(contract.get('acceptance_probes', [])),
                json.dumps(contract.get('gate_plan', [])),
                json.dumps(contract.get('assumptions', [])),
                contract.get('project_dir'),
                contract.get('created_at'),
                contract.get('updated_at'),
            ))

    def get_delivery_contract(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM delivery_contracts WHERE task_id = ? ORDER BY updated_at DESC LIMIT 1',
                (task_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            item = dict(row)
            item['constraints'] = json.loads(item.pop('constraints_json') or '[]')
            for key in (
                'task_types',
                'delivery_facets',
                'technology_hypotheses',
                'capabilities',
                'deliverables',
                'deliverable_groups',
                'acceptance_probes',
                'gate_plan',
                'assumptions',
            ):
                try:
                    item[key] = json.loads(item[key]) if item.get(key) else []
                except json.JSONDecodeError:
                    item[key] = []
            return item

    # ── Full Task Recovery ──

    def get_full_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取完整的任务数据（包含所有子任务、waves、jobs）。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM tasks WHERE task_id = ?', (task_id,))
            task_row = cursor.fetchone()
            if not task_row:
                return None

            task = self._decode_task_row(task_row)

            cursor.execute(
                'SELECT * FROM subtasks WHERE task_id = ? ORDER BY created_at',
                (task_id,),
            )
            subtasks = [self._decode_subtask_row(row) for row in cursor.fetchall()]

            subtask_ids = [st['subtask_id'] for st in subtasks if st.get('subtask_id')]
            jobs_by_subtask: Dict[str, List[Dict[str, Any]]] = {subtask_id: [] for subtask_id in subtask_ids}
            if subtask_ids:
                placeholders = ','.join('?' for _ in subtask_ids)
                cursor.execute(
                    f'''
                    SELECT * FROM jobs
                    WHERE subtask_id IN ({placeholders})
                    ORDER BY subtask_id, created_at
                    ''',
                    tuple(subtask_ids),
                )
                for row in cursor.fetchall():
                    job = self._decode_job_row(row)
                    jobs_by_subtask.setdefault(job.get('subtask_id'), []).append(job)
            for subtask in subtasks:
                subtask['jobs'] = jobs_by_subtask.get(subtask.get('subtask_id'), [])

            cursor.execute('SELECT * FROM waves WHERE task_id = ? ORDER BY wave_number', (task_id,))
            waves = [self._decode_wave_row(row) for row in cursor.fetchall()]

            cursor.execute('SELECT * FROM artifacts WHERE task_id = ? ORDER BY created_at', (task_id,))
            artifacts = [dict(row) for row in cursor.fetchall()]

            cursor.execute(
                '''
                SELECT * FROM artifact_records
                WHERE task_id = ?
                ORDER BY created_at
                ''',
                (task_id,),
            )
            artifact_records = [self._decode_artifact_record_row(row) for row in cursor.fetchall()]

            cursor.execute(
                '''
                SELECT * FROM task_contracts
                WHERE task_id = ?
                ORDER BY level, created_at
                ''',
                (task_id,),
            )
            task_contracts = [self._decode_task_contract_row(row) for row in cursor.fetchall()]

            cursor.execute(
                '''
                SELECT * FROM acceptance_records
                WHERE task_id = ?
                ORDER BY created_at
                ''',
                (task_id,),
            )
            acceptance_records = [self._decode_acceptance_record_row(row) for row in cursor.fetchall()]

            cursor.execute('SELECT * FROM fix_rounds WHERE task_id = ? ORDER BY round_number', (task_id,))
            fix_rounds = [dict(row) for row in cursor.fetchall()]

            cursor.execute('SELECT * FROM requirement_manifests WHERE task_id = ?', (task_id,))
            manifest_row = cursor.fetchone()

            cursor.execute(
                'SELECT * FROM delivery_contracts WHERE task_id = ? ORDER BY updated_at DESC LIMIT 1',
                (task_id,),
            )
            delivery_contract_row = cursor.fetchone()

        task['subtasks'] = subtasks
        task['waves'] = waves
        task['artifacts'] = artifacts
        task['artifact_records'] = artifact_records
        task['task_contracts'] = task_contracts
        task['acceptance_records'] = acceptance_records
        task['fix_rounds'] = fix_rounds
        task['requirement_manifest'] = self._decode_requirement_manifest_row(manifest_row) if manifest_row else None
        task['owner_delivery_contract'] = self._decode_delivery_contract_row(delivery_contract_row) if delivery_contract_row else None

        return task

    def _decode_json(self, value: Any, default: Any) -> Any:
        if not value:
            return default
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default

    def _is_original_business_subtask_id(self, subtask_id: str) -> bool:
        if not subtask_id:
            return False
        if subtask_id.endswith("-decompose"):
            return False
        if subtask_id.startswith("st-quality-"):
            return False
        if "-integration-fix" in subtask_id:
            return False
        return re.sub(r"-(?:fix-\d+|v\d+)$", "", subtask_id) == subtask_id

    def _get_business_subtask_counts(self, cursor: Any, task_ids: List[str]) -> Dict[str, tuple[int, int]]:
        if not task_ids:
            return {}
        placeholders = ",".join("?" for _ in task_ids)
        cursor.execute(
            f'''
            SELECT task_id, subtask_id, status
            FROM subtasks
            WHERE task_id IN ({placeholders})
            ''',
            tuple(task_ids),
        )
        counts: Dict[str, List[int]] = {task_id: [0, 0] for task_id in task_ids}
        for row in cursor.fetchall():
            subtask_id = row["subtask_id"]
            if not self._is_original_business_subtask_id(subtask_id):
                continue
            task_counts = counts.setdefault(row["task_id"], [0, 0])
            task_counts[1] += 1
            if row["status"] == "completed":
                task_counts[0] += 1
        return {task_id: (value[0], value[1]) for task_id, value in counts.items()}

    def _decode_task_row(self, row: Any) -> Dict[str, Any]:
        item = dict(row)
        for key in ('owner_state_summary', 'last_owner_decision'):
            item[key] = self._decode_json(item.get(key), {})
        for key in ('allowed_subtask_agents', 'task_types'):
            item[key] = self._decode_json(item.get(key), [])
        item['delivery_mode'] = item.get('delivery_mode') or 'external'
        return item

    def _decode_subtask_row(self, row: Any) -> Dict[str, Any]:
        item = dict(row)
        item['dependencies'] = self._decode_json(item.get('dependencies'), [])
        return item

    def _decode_job_row(self, row: Any) -> Dict[str, Any]:
        item = dict(row)
        item['logs'] = self._decode_json(item.get('logs'), [])
        return item

    def _decode_wave_row(self, row: Any) -> Dict[str, Any]:
        item = dict(row)
        item['is_blocked'] = bool(item.get('is_blocked'))
        item['is_revalidating'] = bool(item.get('is_revalidating'))
        item['owner_decision'] = self._decode_json(item.get('owner_decision'), {})
        return item

    def _decode_task_contract_row(self, row: Any) -> Dict[str, Any]:
        item = dict(row)
        for key in ('input_artifact_ids', 'expected_deliverables', 'acceptance_checks'):
            item[key] = self._decode_json(item.get(key), [])
        return item

    def _decode_artifact_record_row(self, row: Any) -> Dict[str, Any]:
        item = dict(row)
        item['metadata'] = self._decode_json(item.get('metadata'), {})
        item['source_artifact_ids'] = self._decode_json(item.get('source_artifact_ids'), [])
        return item

    def _decode_acceptance_record_row(self, row: Any) -> Dict[str, Any]:
        item = dict(row)
        for key in ('failed_checks', 'missing_artifacts', 'root_cause_artifact_ids'):
            item[key] = self._decode_json(item.get(key), [])
        item['deterministic_passed'] = bool(item.get('deterministic_passed'))
        item['judge_passed'] = bool(item.get('judge_passed'))
        return item

    def _decode_requirement_manifest_row(self, row: Any) -> Dict[str, Any]:
        item = dict(row)
        item['deliverables'] = self._decode_json(item.get('deliverables'), [])
        item['quality_checks'] = self._decode_json(item.get('quality_checks'), [])
        return item

    def _decode_delivery_contract_row(self, row: Any) -> Dict[str, Any]:
        item = dict(row)
        item['constraints'] = self._decode_json(item.pop('constraints_json', None), [])
        for key in (
            'task_types',
            'delivery_facets',
            'technology_hypotheses',
            'capabilities',
            'deliverables',
            'deliverable_groups',
            'acceptance_probes',
            'gate_plan',
            'assumptions',
        ):
            item[key] = self._decode_json(item.get(key), [])
        return item
