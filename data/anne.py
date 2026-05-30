import fitz  # PyMuPDF
import sqlite3
import os

# 1. Extract PDF pages into (page_num, content) tuples
def extract_pdf_to_pages(pdf_path):
    print(f"[*] Opening PDF: {pdf_path}...")
    doc = fitz.open(pdf_path)
    pages_data = []
    total_chars = 0
    for page_idx, page in enumerate(doc):
        text = page.get_text("text")
        total_chars += len(text.strip())
        pages_data.append((page_idx + 1, text)) 
    print(f"[+] Extracted {len(pages_data)} pages ({total_chars} characters).")
    return pages_data

# 2. Build the database using the schema expected by query_index
def build_index(pages_data, db_path="applebaum_archive.db"):
    print(f"[*] Building FTS5 index in '{db_path}'...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS search_index")
    cursor.execute("""
        CREATE VIRTUAL TABLE search_index USING fts5(
            page_num UNINDEXED, 
            content
        )
    """)
    cursor.executemany(
        "INSERT INTO search_index (page_num, content) VALUES (?, ?)", 
        pages_data
    )
    conn.commit()
    print(f"[+] Index built successfully.")
    return conn

# 3. Your query_index function (with a check for empty results)
def query_index(conn, search_term):
    cursor = conn.cursor()
    query = """
        SELECT 
            page_num, 
            snippet(search_index, 1, '<b>', '</b>', '...', 20) as excerpt,
            bm25(search_index) as rank
        FROM search_index 
        WHERE content MATCH ?
        ORDER BY rank ASC
        LIMIT 5
    """
    try:
        results = cursor.execute(query, (search_term,)).fetchall()
        
        if not results:
            print(f"\n[!] No matches found for: '{search_term}'\n")
            return
            
        print(f"\n--- Matches for '{search_term}' ({len(results)} found) ---")
        for row in results:
            print(f"PAGE {row[0]} (Score: {round(row[2], 2)})")
            print(f"Excerpt: {row[1]}\n")
            
    except sqlite3.OperationalError as e:
        print(f"\n[!] SQLite query error: {e}")
        print("    Try adjusting your search syntax.\n")

# --- EXECUTION & REPL LOOP ---
if __name__ == "__main__":
    pdf_file = "anne_applebaum_article.pdf"
    db_file = "applebaum_archive.db"
    
    # Check if the index database already exists. If not, build it.
    if not os.path.exists(db_file):
        if not os.path.exists(pdf_file):
            print(f"[!] Error: Database '{db_file}' does not exist, and cannot find source PDF '{pdf_file}' to build it.")
            print("    Please place the PDF in this folder and try again.")
            exit(1)
        
        data = extract_pdf_to_pages(pdf_file)
        db_conn = build_index(data, db_file)
    else:
        print(f"[+] Database '{db_file}' found. Skipping indexing phase and loading index...")
        db_conn = sqlite3.connect(db_file)
    
    # Enter the interactive console loop
    print("\n=============================================")
    print("    BM25 ARCHIVE INTERACTIVE SEARCH")
    print("=============================================")
    print("Type your search term and press Enter.")
    print("To stop, type 'exit', 'quit', or 'q'.\n")
    
    try:
        while True:
            try:
                search_term = input("Search query > ").strip()
            except EOFError:
                break
            
            # Check for termination commands
            if search_term.lower() in ('exit', 'quit', 'q'):
                print("Exiting. Goodbye!")
                break
            
            # Ignore blank inputs
            if not search_term:
                continue
            
            # Execute the query
            query_index(db_conn, search_term)
            print("-" * 50)
            
    except KeyboardInterrupt:
        print("\nExiting. Goodbye!")
    finally:
        db_conn.close()
