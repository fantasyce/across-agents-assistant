import sqlite3
import os
import sys

def init_db(db_path=":memory:"):
    conn = sqlite3.connect(db_path)
    # Check if FTS5 is available
    cur = conn.cursor()
    try:
        cur.execute("CREATE VIRTUAL TABLE test_fts USING fts5(text);")
        cur.execute("DROP TABLE test_fts;")
        print("[System] SQLite FTS5 is available.")
    except Exception as e:
        print(f"[System Error] FTS5 not available: {e}")
        sys.exit(1)
        
    # We create an FTS5 table
    # Using 'unicode61' tokenizer is standard. 
    # For Chinese characters, newer SQLite has 'trigram', but let's try default first.
    cur.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS wiki_index 
        USING fts5(filename, filepath UNINDEXED, content, tokenize='unicode61');
    ''')
    conn.commit()
    return conn

def index_wiki(conn, folder_path):
    cur = conn.cursor()
    cur.execute("DELETE FROM wiki_index;")
    
    count = 0
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
                        count += 1
                except Exception as e:
                    print(f"[Warning] Failed to read {file}: {e}")
    conn.commit()
    print(f"[Index] Successfully indexed {count} markdown/txt files from {folder_path}.")

def search_wiki(conn, query_str):
    cur = conn.cursor()
    print(f"\n--- Searching for: '{query_str}' ---")
    
    # We split query into keywords.
    # In FTS5, multiple words can be joined by AND or OR.
    # We use AND to ensure all keywords exist.
    keywords = query_str.split()
    if not keywords:
        return
        
    # FTS5 query syntax: "keyword1" AND "keyword2"
    # Wrapping in quotes helps avoid issues with special characters.
    fts_query = " AND ".join(f'"{kw}"' for kw in keywords)
    print(f"[FTS Query] {fts_query}")
    
    try:
        # We use snippet() to highlight matches
        # snippet(table_name, column_index, start_match, end_match, ellipsis, max_tokens)
        # Column 2 is 'content' (0: filename, 1: filepath, 2: content)
        cur.execute('''
            SELECT 
                filename, 
                snippet(wiki_index, 2, '>>>', '<<<', '...', 30) as match_snippet,
                rank 
            FROM wiki_index 
            WHERE wiki_index MATCH ? 
            ORDER BY rank 
            LIMIT 5;
        ''', (fts_query,))
        
        results = cur.fetchall()
        if not results:
            print("No results found. (Maybe tokenizer issue or keywords don't match)")
            return
            
        for row in results:
            print(f"File: {row[0]} | Score/Rank (lower is better): {row[2]:.4f}")
            print(f"Snippet:\n{row[1]}\n")
            
    except Exception as e:
        print(f"[Search Error] {e}")

if __name__ == "__main__":
    db_conn = init_db()
    wiki_path = "/Users/fanhcy/Documents/mywiki"
    
    index_wiki(db_conn, wiki_path)
    
    # Let's run a few test queries
    search_wiki(db_conn, "Hermes agent")
    search_wiki(db_conn, "Hermes agent 接入")
    search_wiki(db_conn, "OpenClaw")
