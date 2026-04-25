import sqlite3
import os
import sys
import re

def init_db(db_path=":memory:"):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Drop old table if exists
    cur.execute("DROP TABLE IF EXISTS wiki_index;")
    
    # We will try to create a table with a custom tokenizer if possible, or just use unicode61
    # But since SQLite unicode61 tokenizer struggles with continuous Chinese characters (like "接入"),
    # we'll build a slightly smarter query mechanism.
    cur.execute('''
        CREATE VIRTUAL TABLE IF NOT EXISTS wiki_index 
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
                        # A simple trick for FTS5 unicode61 with Chinese: 
                        # Insert spaces between Chinese characters so they become individual tokens.
                        # This makes MATCH query find adjacent characters.
                        spaced_content = re.sub(r'([\u4e00-\u9fa5])', r' \1 ', content)
                        cur.execute('''
                            INSERT INTO wiki_index(filename, filepath, content) 
                            VALUES(?, ?, ?)
                        ''', (file, filepath, spaced_content))
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
        
    fts_terms = []
    for kw in keywords:
        # If it contains Chinese, split it into characters and wrap in double quotes to form a phrase
        if re.search(r'[\u4e00-\u9fa5]', kw):
            chars = list(kw)
            phrase = " ".join(chars)
            fts_terms.append(f'"{phrase}"')
        else:
            fts_terms.append(f'"{kw}"')
            
    fts_query = " AND ".join(fts_terms)
    print(f"[FTS Query] {fts_query}")
    
    try:
        cur.execute('''
            SELECT 
                filename, 
                snippet(wiki_index, 2, '>>>', '<<<', '...', 25) as match_snippet,
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
            # Remove the extra spaces we injected for Chinese characters, just for display
            clean_snippet = re.sub(r' ([\u4e00-\u9fa5]) ', r'\1', row[1])
            # Fix up the >>> <<< tags that might have spaces around them
            clean_snippet = clean_snippet.replace('>>> ', '>>>').replace(' <<<', '<<<')
            print(f"Snippet:\n{clean_snippet}\n")
            
    except Exception as e:
        print(f"[Search Error] {e}")

if __name__ == "__main__":
    db_conn = init_db()
    wiki_path = "/Users/fanhcy/Documents/mywiki"
    
    index_wiki(db_conn, wiki_path)
    search_wiki(db_conn, "Hermes agent 接入")
    search_wiki(db_conn, "OpenClaw Dreaming")
