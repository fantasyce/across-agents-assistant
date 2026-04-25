import sqlite3
import os
import sys

def init_db(db_path=":memory:"):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Using trigram if available, else unicode61
    try:
        cur.execute('''
            CREATE VIRTUAL TABLE wiki_index 
            USING fts5(filename, filepath UNINDEXED, content, tokenize='trigram');
        ''')
        print("[System] Using FTS5 with 'trigram' tokenizer (Excellent for Chinese!)")
    except Exception:
        print("[System] 'trigram' tokenizer not available. Falling back to 'unicode61'.")
        cur.execute('''
            CREATE VIRTUAL TABLE wiki_index 
            USING fts5(filename, filepath UNINDEXED, content, tokenize='unicode61');
        ''')
    conn.commit()
    return conn

def index_wiki(conn, folder_path):
    cur = conn.cursor()
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
                    pass
    conn.commit()
    print(f"Indexed {count} files.")

def search_wiki(conn, query_str):
    cur = conn.cursor()
    print(f"\n--- Searching for: '{query_str}' ---")
    
    keywords = query_str.split()
    if not keywords:
        return
        
    fts_query = " AND ".join(f'"{kw}"' for kw in keywords)
    print(f"[FTS Query] {fts_query}")
    
    try:
        cur.execute('''
            SELECT 
                filename, 
                snippet(wiki_index, 2, '>>>', '<<<', '...', 40) as match_snippet,
                rank 
            FROM wiki_index 
            WHERE wiki_index MATCH ? 
            ORDER BY rank 
            LIMIT 3;
        ''', (fts_query,))
        
        results = cur.fetchall()
        if not results:
            print("No results found.")
            return
            
        for row in results:
            print(f"File: {row[0]}")
            print(f"Snippet:\n{row[1]}\n")
            
    except Exception as e:
        print(f"[Search Error] {e}")

if __name__ == "__main__":
    db_conn = init_db()
    wiki_path = "/Users/fanhcy/Documents/mywiki"
    
    index_wiki(db_conn, wiki_path)
    search_wiki(db_conn, "Hermes agent 接入")
    search_wiki(db_conn, "OpenClaw Dreaming")
    search_wiki(db_conn, "OpenClaw DeerFlow 集成")
