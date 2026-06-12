import sys
import os
import sqlite3
import re
from mcp.server.fastmcp import FastMCP

from ..paths import component_data_home

mcp = FastMCP("Local Knowledge Base")

kb_dir = ""
db_conn = None


def default_kb_dir():
    return str(component_data_home() / "local-knowledge")

def get_db():
    global db_conn
    if db_conn is not None:
        return db_conn

    # We create an in-memory SQLite database for blazing fast indexing and retrieval.
    # Since we are local, we can afford to rebuild it quickly on startup or lazy load it.
    db_conn = sqlite3.connect(":memory:", check_same_thread=False)
    cur = db_conn.cursor()

    try:
        cur.execute('''
            CREATE VIRTUAL TABLE wiki_index
            USING fts5(filename, filepath UNINDEXED, content, tokenize='trigram');
        ''')
    except Exception:
        cur.execute('''
            CREATE VIRTUAL TABLE wiki_index
            USING fts5(filename, filepath UNINDEXED, content, tokenize='unicode61');
        ''')
    db_conn.commit()

    # Auto-index the directory if it exists
    if kb_dir and os.path.exists(kb_dir):
        _index_directory(kb_dir)

    return db_conn

def _index_directory(folder_path):
    cur = db_conn.cursor()
    cur.execute("DELETE FROM wiki_index;")

    for root, _, files in os.walk(folder_path):
        for file in files:
            if file.endswith('.md') or file.endswith('.txt'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        cur.execute('''
                            INSERT INTO wiki_index(filename, filepath, content)
                            VALUES(?, ?, ?)
                        ''', (file, filepath, content))
                except Exception:
                    pass
    db_conn.commit()

@mcp.tool(name="search_local_wiki")
def search_local_wiki(query: str) -> str:
    """Search the local knowledge base (Wiki folder) for a specific query.
    ALWAYS USE THIS TOOL FIRST when you need to answer questions about topics, entities, or concepts that might be in the local knowledge base.
    Returns matching snippets from Markdown files.
    """
    if not kb_dir or not os.path.exists(kb_dir):
        return f"Error: Wiki directory {kb_dir} does not exist."

    conn = get_db()
    cur = conn.cursor()

    keywords = query.split()
    if not keywords:
        return "Error: Empty query."

    # Build a forgiving OR query for FTS5
    fts_query = " OR ".join(f'"{kw}"' for kw in keywords)

    try:
        cur.execute('''
            SELECT
                filename,
                snippet(wiki_index, 2, '[[[', ']]]', '...', 60) as match_snippet,
                rank
            FROM wiki_index
            WHERE wiki_index MATCH ?
            ORDER BY rank
            LIMIT 5;
        ''', (fts_query,))

        results = cur.fetchall()
        if not results:
            return f"No results found for '{query}' in {kb_dir}."

        output = ["Search Results:\n"]
        best_rank = results[0][2]

        for row in results:
            rank = row[2]
            if rank == 0.0 and best_rank < -1.0:
                continue

            filename = row[0]
            snip = row[1].replace('\n', ' ')
            snip = re.sub(r'\s+', ' ', snip)

            output.append(f"File: {filename}")
            output.append(f"Snippet: {snip}\n")

        if len(output) == 1:
            return f"No strong matching results found for '{query}'."

        return "\n".join(output)

    except Exception as e:
        return f"Error during search: {str(e)}"

@mcp.tool(name="list_wiki_pages")
def list_wiki_pages() -> str:
    """List all available pages in the local Wiki folder.
    Use this tool ONLY if the user explicitly asks to see the directory structure or list of files.
    For answering specific questions, use search_local_wiki instead.
    """
    if not kb_dir or not os.path.exists(kb_dir):
        return f"Error: Wiki directory {kb_dir} does not exist."

    pages = []
    for root, _, files in os.walk(kb_dir):
        for file in files:
            if file.endswith('.md') or file.endswith('.txt'):
                rel_path = os.path.relpath(os.path.join(root, file), kb_dir)
                pages.append(rel_path)

    if not pages:
        return "The Wiki folder is empty."

    return "Available pages:\n" + "\n".join(f"- {p}" for p in pages)

@mcp.tool(name="read_wiki_page")
def read_wiki_page(filepath: str) -> str:
    """Read the full content of a specific Wiki page.
    Use this tool after using search_local_wiki or list_wiki_pages to get more details from a specific file.
    Args:
        filepath: The relative path to the page (e.g., 'notes.md').
    """
    if not kb_dir or not os.path.exists(kb_dir):
        return f"Error: Wiki directory {kb_dir} does not exist."

    full_path = os.path.join(kb_dir, filepath)
    if not os.path.exists(full_path):
        return f"Error: File {filepath} not found."

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

def main():
    global kb_dir
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=str, help="Path to the Wiki folder")
    args, unknown = parser.parse_known_args()

    if args.dir:
        kb_dir = args.dir
    else:
        kb_dir = default_kb_dir()

    if not os.path.exists(kb_dir):
        try:
            os.makedirs(kb_dir, exist_ok=True)
        except Exception:
            pass

    sys.argv = [sys.argv[0]] + unknown
    mcp.run()

if __name__ == "__main__":
    main()
