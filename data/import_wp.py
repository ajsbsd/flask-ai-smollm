#!/usr/bin/env python3
"""
import_wp_v6.py – MariaDB dump importer with auto-schema creation.
"""
import argparse, re, sqlite3, sys
from pathlib import Path
from datetime import datetime

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("dump", type=Path)
    p.add_argument("-d", "--db", default="wstudio.db")
    p.add_argument("--truncate", action="store_true")
    return p.parse_args()

def strip_comments(s):
    s = re.sub(r'--[^\n]*', '', s)
    return re.sub(r'/\*.*?\*/', '', s, flags=re.DOTALL)

def extract_rows(sql, table):
    rows = []
    pattern = re.compile(rf"INSERT\s+INTO\s+`?{re.escape(table)}`?\s*(?:\([^)]*\)\s*)?VALUES\s*([\s\S]*?);", re.I)
    for match in pattern.finditer(sql):
        for tuple_str in yield_tuples(match.group(1)):
            cols = parse_tuple(tuple_str)
            if len(cols) >= 21: rows.append(cols)
    return rows

def yield_tuples(s):
    i, n = 0, len(s)
    while i < n:
        if s[i] == '(':
            start, depth, in_q, esc, qchar = i, 0, False, False, None
            j = i
            while j < n:
                c = s[j]
                if esc: esc = False
                elif c == '\\': esc = True
                elif c in ("'", '"') and not esc:
                    if not in_q: in_q, qchar = True, c
                    elif c == qchar: in_q = False
                elif c == '(' and not in_q: depth += 1
                elif c == ')' and not in_q:
                    depth -= 1
                    if depth == 0:
                        yield s[start:j+1]
                        i = j + 1
                        break
                j += 1
        i += 1

def parse_tuple(t):
    inner = t[1:-1].strip()
    vals, cur, in_q, esc, qchar = [], [], False, False, None
    for c in inner:
        if esc: cur.append(c); esc = False; continue
        if c == '\\': cur.append(c); esc = True; continue
        if c in ("'", '"') and not esc:
            if not in_q: in_q, qchar = True, c
            elif c == qchar: in_q = False
            cur.append(c)
        elif c == ',' and not in_q:
            vals.append(''.join(cur).strip()); cur = []
        else: cur.append(c)
    if cur: vals.append(''.join(cur).strip())
    return vals

def clean(v):
    v = v.strip()
    if v.upper() == 'NULL': return ''
    if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')): v = v[1:-1]
    return v.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")

def ensure_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            post_type TEXT DEFAULT 'post'
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_post_type ON posts(post_type);")
    conn.commit()

def main():
    args = parse_args()
    if not args.dump.exists(): print(f"❌ Not found: {args.dump}"); sys.exit(1)
    print(f"📦 Reading: {args.dump.name}")
    sql = strip_comments(args.dump.read_text(encoding="utf-8", errors="ignore"))
    
    tbl_match = re.search(r"(?:CREATE TABLE|INSERT INTO)\s+`?([a-zA-Z0-9]+_posts)`?", sql, re.I)
    table = tbl_match.group(1) if tbl_match else "wpstg0_posts"
    print(f"🔍 Target table: `{table}`")
    print("🔍 Extracting rows...")
    rows = extract_rows(sql, table)
    print(f"✅ Parsed {len(rows)} rows")
    if not rows: print("⚠️ No rows found."); sys.exit(0)

    conn = sqlite3.connect(args.db, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    cur = conn.cursor()
    ensure_schema(conn) # 🔑 Auto-create table if missing
    if args.truncate: cur.execute("DELETE FROM posts"); conn.commit()

    stats = {"imported": 0, "skipped": 0, "errors": 0}
    for cols in rows:
        title = clean(cols[5]) or "(untitled)"
        content = clean(cols[4])
        ptype = clean(cols[20])
        created = clean(cols[2]) or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if ptype not in ("post", "page"): stats["skipped"] += 1; continue
        if not title.strip() and not content.strip(): stats["skipped"] += 1; continue
        try:
            cur.execute("INSERT INTO posts (title, content, created_at, post_type) VALUES (?, ?, ?, ?)",
                       (title, content, created, ptype))
            stats["imported"] += 1
        except sqlite3.Error as e: print(f"❌ Error: {e}"); stats["errors"] += 1
    conn.commit(); conn.close()

    print(f"\n📊 Results: Imported {stats['imported']} | Skipped {stats['skipped']} | Errors {stats['errors']}")
    conn = sqlite3.connect(args.db)
    total = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    by_type = {t[0]: t[1] for t in conn.execute("SELECT post_type, COUNT(*) FROM posts GROUP BY post_type")}
    conn.close()
    print(f"🗄️ DB Total: {total} | By type: {by_type}")

if __name__ == "__main__":
    main()
