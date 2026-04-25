import sqlite3
import os
from typing import List, Dict, Any
from datetime import datetime

class DatabaseManager:
    def __init__(self, db_path: str = None):
        if db_path is None:
            # Use a local db file in the user's home directory for persistence
            home_dir = os.path.expanduser("~")
            app_dir = os.path.join(home_dir, ".across_agents")
            os.makedirs(app_dir, exist_ok=True)
            self.db_path = os.path.join(app_dir, "assistant.db")
        else:
            self.db_path = db_path
            
        self._init_db()

    def _get_connection(self):
        # We need a new connection per thread in sqlite3 by default
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Create Sessions Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create Messages Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT,
                tool_call_id TEXT,
                tool_calls TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        ''')
        
        # Try to add tool_call_id column if it doesn't exist
        try:
            cursor.execute('ALTER TABLE messages ADD COLUMN tool_call_id TEXT')
        except Exception:
            pass
        try:
            cursor.execute('ALTER TABLE messages ADD COLUMN tool_calls TEXT')
        except Exception:
            pass
            
        # Create Audit Logs Table for external system tools
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                tool_args TEXT,
                risk_level TEXT,
                decision TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        ''')
        
        # Create Tool Authorizations Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tool_authorizations (
                tool_name TEXT PRIMARY KEY,
                is_always_allowed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Indices
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audit_logs_session_id ON audit_logs(session_id)')
        
        conn.commit()
        conn.close()

    # --- Session Management ---
    
    def get_or_create_session(self, session_id: str):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id FROM sessions WHERE id = ?', (session_id,))
        row = cursor.fetchone()
        
        if not row:
            cursor.execute('INSERT INTO sessions (id) VALUES (?)', (session_id,))
            
        conn.commit()
        conn.close()

    def update_session_timestamp(self, session_id: str):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?', (session_id,))
        conn.commit()
        conn.close()

    # --- Message Management ---
    
    def add_message(self, session_id: str, role: str, content: str, tool_call_id: str = None, tool_calls: str = None):
        self.get_or_create_session(session_id)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO messages (session_id, role, content, tool_call_id, tool_calls) VALUES (?, ?, ?, ?, ?)',
            (session_id, role, content, tool_call_id, tool_calls)
        )
        conn.commit()
        conn.close()
        
        self.update_session_timestamp(session_id)

    def get_messages(self, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT id, role, content, tool_call_id, tool_calls, created_at FROM messages WHERE session_id = ? ORDER BY created_at DESC LIMIT ?',
            (session_id, limit)
        )
        
        # Reverse to get chronological order
        rows = list(cursor.fetchall())
        rows.reverse()
        
        conn.close()
        return [dict(row) for row in rows]
        
    def update_system_message(self, session_id: str, new_content: str):
        conn = self._get_connection()
        cursor = conn.cursor()
        # Find the first system message for this session and update its content
        cursor.execute('SELECT id FROM messages WHERE session_id = ? AND role = "system" ORDER BY created_at ASC LIMIT 1', (session_id,))
        row = cursor.fetchone()
        if row:
            cursor.execute('UPDATE messages SET content = ? WHERE id = ?', (new_content, row['id']))
        conn.commit()
        conn.close()

    def clear_session(self, session_id: str):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
        conn.commit()
        conn.close()

    # --- Audit & Security ---
    
    def add_audit_log(self, session_id: str, tool_name: str, tool_args: Dict[str, Any], risk_level: str, decision: str):
        self.get_or_create_session(session_id)
        
        import json
        args_str = json.dumps(tool_args, ensure_ascii=False) if tool_args else "{}"
        
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO audit_logs (session_id, tool_name, tool_args, risk_level, decision) VALUES (?, ?, ?, ?, ?)',
            (session_id, tool_name, args_str, risk_level, decision)
        )
        conn.commit()
        conn.close()
        
    def get_audit_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT ?', (limit,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
    
    def get_tool_authorization(self, tool_name: str) -> bool:
        """Check if a tool is 'Always Allowed'"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT is_always_allowed FROM tool_authorizations WHERE tool_name = ?', (tool_name,))
        row = cursor.fetchone()
        conn.close()
        return bool(row and row['is_always_allowed'])

    def set_tool_authorization(self, tool_name: str, is_always_allowed: bool):
        """Set or update the 'Always Allow' status for a tool"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO tool_authorizations (tool_name, is_always_allowed) 
            VALUES (?, ?)
            ON CONFLICT(tool_name) DO UPDATE SET 
            is_always_allowed = excluded.is_always_allowed,
            updated_at = CURRENT_TIMESTAMP
        ''', (tool_name, is_always_allowed))
        conn.commit()
        conn.close()
        
    def get_all_authorizations(self) -> List[Dict[str, Any]]:
        """Get all explicitly authorized tools"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT tool_name, is_always_allowed, updated_at FROM tool_authorizations')
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows

# Singleton instance
db = DatabaseManager()
