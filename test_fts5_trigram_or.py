import sqlite3
import os
import sys
import re

def init_db(db_path=":memory:"):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # We will use trigram if available, else unicode61 with a space injection trick
    try:
        cur.execute('''
            CREATE VIRTUAL TABLE wiki_index 
            USING fts5(filename, filepath UNINDEXED, content, tokenize='trigram');
        ''')
        print("[System] Using FTS5 with 'trigram' tokenizer")
    except Exception:
        print("[System] 'trigram' not available, using 'unicode61'")
        cur.execute('''
            CREATE VIRTUAL TABLE wiki_index 
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
                        # If using unicode61, we should inject spaces between Chinese characters
                        # but let's assume macOS sqlite3 has trigram (it usually does on newer macOS)
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
        
    # Crucial logic: We want documents that match AS MANY keywords as possible.
    # By default, FTS5 matches exact phrases. If we use OR, it returns any match, but ranks higher 
    # those with more matches. If we use AND, it strictly requires all.
    # To simulate Google-like search, we can use a weighted OR approach or rely on BM25 rank.
    # BM25 (rank) automatically scores documents with more matched terms higher.
    
    # We format the query as: "word1" OR "word2" OR "word3"
    fts_query = " OR ".join(f'"{kw}"' for kw in keywords)
    print(f"[FTS Query] {fts_query}")
    
    try:
        # snippet() automatically highlights whatever matched
        # syntax: snippet(table, col, start_tag, end_tag, ellipsis, max_tokens)
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
            print("No results found.")
            return
            
        # Filter out weak matches
        # We can calculate the minimum acceptable rank based on the best match
        best_rank = results[0][2]
        
        for row in results:
            rank = row[2]
            # If the rank is much worse than the best rank (e.g. 0.0 when best is -4.0), it's probably a single word match
            # FTS5 rank is negative. A rank of 0 means almost no relevance or very common word.
            if rank == 0.0 and best_rank < -1.0:
                continue
                
            print(f"File: {row[0]} | Rank: {rank:.4f}")
            
            # Clean up the snippet slightly for display
            snip = row[1].replace('\n', ' ')
            # Collapse multiple spaces
            snip = re.sub(r'\s+', ' ', snip)
            print(f"Snippet: {snip}\n")
            
    except Exception as e:
        print(f"[Search Error] {e}")

if __name__ == "__main__":
    db_conn = init_db()
    wiki_path = "/Users/fanhcy/Documents/mywiki"
    
    index_wiki(db_conn, wiki_path)
    
    search_wiki(db_conn, "Hermes agent 接入")
    search_wiki(db_conn, "OpenClaw DeerFlow 集成")
    search_wiki(db_conn, "macos app development")
