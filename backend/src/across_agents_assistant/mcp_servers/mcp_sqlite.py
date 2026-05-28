import sys
import os
import sqlite3
import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("SQLite Database")

db_path = ""


def get_db():
    if not db_path:
        raise ValueError("Database path not configured")
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file not found: {db_path}")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@mcp.tool(name="sqlite_list_tables")
def sqlite_list_tables() -> str:
    """List all tables in the SQLite database. Use this first to understand the database structure."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY type, name;")
        rows = cur.fetchall()
        conn.close()
        if not rows:
            return "No tables or views found in the database."
        result = [f"{row['type'].capitalize()}: {row['name']}" for row in rows]
        return "Tables and Views:\n- " + "\n- ".join(result)
    except Exception as e:
        return f"Error listing tables: {str(e)}"


@mcp.tool(name="sqlite_get_schema")
def sqlite_get_schema(table_name: str) -> str:
    """Get the schema (column definitions) for a specific table.

    Args:
        table_name: The name of the table to get schema for.
    """
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info(\"{table_name}\");")
        rows = cur.fetchall()
        conn.close()
        if not rows:
            return f"Table '{table_name}' not found or has no columns."
        result = ["Columns:"]
        for row in rows:
            pk = " (PRIMARY KEY)" if row["pk"] else ""
            result.append(f"  - {row['name']}: {row['type']}{pk}")
        return "\n".join(result)
    except Exception as e:
        return f"Error getting schema: {str(e)}"


@mcp.tool(name="sqlite_query")
def sqlite_query(sql: str, limit: int = 20) -> str:
    """Execute a SELECT query on the SQLite database and return results as JSON.

    Args:
        sql: The SQL SELECT query to execute. Only SELECT queries are allowed for safety.
        limit: Maximum number of rows to return (default 20, max 100).
    """
    sql = sql.strip()
    if not sql.upper().startswith("SELECT"):
        return "Error: Only SELECT queries are allowed for safety reasons."
    if limit <= 0:
        limit = 20
    if limit > 100:
        limit = 100

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(f"{sql} LIMIT {limit};")
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description] if cur.description else []
        conn.close()

        if not rows:
            return "Query returned no results."

        result = {"columns": columns, "rows": [dict(row) for row in rows], "count": len(rows)}
        return json.dumps(result, default=str, indent=2)
    except Exception as e:
        return f"Error executing query: {str(e)}"


@mcp.tool(name="sqlite_sample_table")
def sqlite_sample_table(table_name: str, limit: int = 5) -> str:
    """Get a sample of rows from a table to understand its content.

    Args:
        table_name: The name of the table to sample.
        limit: Number of rows to return (default 5).
    """
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(f'SELECT * FROM "{table_name}" LIMIT {min(limit, 20)};')
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description] if cur.description else []
        conn.close()

        if not rows:
            return f"Table '{table_name}' is empty."

        result = {"table": table_name, "columns": columns, "sample_rows": [dict(row) for row in rows]}
        return json.dumps(result, default=str, indent=2)
    except Exception as e:
        return f"Error sampling table: {str(e)}"


def main():
    global db_path
    import argparse
    parser = argparse.ArgumentParser(description="SQLite MCP Server")
    parser.add_argument("--db-path", type=str, required=True, help="Path to the SQLite database file")
    args, unknown = parser.parse_known_args()

    db_path = os.path.expanduser(args.db_path)
    sys.argv = [sys.argv[0]] + unknown
    mcp.run()


if __name__ == "__main__":
    main()
