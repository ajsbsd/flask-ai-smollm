#!/usr/bin/env python3
import argparse
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
            description="Import WordPress SQL dump to SQLite")
    parser.add_argument("dump", type=Path,
                        help="Path to WordPress SQL dump file")
    parser.add_argument("db", type=Path, help="Path to output SQLite database")
    parser.add_argument(
        "--truncate", action="store_true", help="Clear existing posts table"
    )
    return parser.parse_args()


def strip_comments(sql):
    return re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)


def yield_tuples(s):
    depth, in_q, qchar, esc = 0, False, None, False
    start = 0
    for i, c in enumerate(s):
        if esc:
            esc = False
        elif c == "\\":
            esc = True
        elif c in ("'", '"') and not esc:
            if not in_q:
                in_q, qchar = True, c
            elif c == qchar:
                in_q = False
        elif c == "(" and not in_q:
            depth += 1
            if depth == 1:
                start = i
        elif c == ")" and not in_q:
            depth -= 1
            if depth == 0:
                yield s[start: i+1]


def parse_tuple(s):
    inner = s[1:-1].strip()
    if not inner:
        return []
    vals, cur, in_q, esc, qchar = [], [], False, False, None
    for c in inner:
        if esc:
            cur.append(c)
            esc = False
            continue
        if c == "\\":
            cur.append(c)
            esc = True
            continue
        if c in ("'", '"') and not esc:
            if not in_q:
                in_q, qchar = True, c
            elif c == qchar:
                in_q = False
            cur.append(c)
        elif c == "," and not in_q:
            vals.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
    if cur:
        vals.append("".join(cur).strip())
    return vals


def clean(v):
    v = v.strip()
    if v.upper() == "NULL":
        return ""
    if (v.startswith("'") and v.endswith("'")) or (
        v.startswith('"') and v.endswith('"')
    ):
        v = v[1:-1]
    return v.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")


def extract_rows(sql, table):
    rows = []
    pattern = rf"INSERT INTO `{table}` VALUES\s*(\(.*?\));"
    for match in re.finditer(pattern, sql, re.IGNORECASE | re.DOTALL):
        for tuple_str in yield_tuples(match.group(1)):
            cols = parse_tuple(tuple_str)
            if len(cols) >= 21:
                rows.append(cols)
    return rows


def ensure_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY,
            title TEXT,
            content TEXT,
            created_at TEXT,
            post_type TEXT
        )
    """)
    conn.commit()


def main():
    args = parse_args()
    if not args.dump.exists():
        print(f"❌ Not found: {args.dump}")
        sys.exit(1)

    print(f"📦 Reading: {args.dump.name}")
    sql = strip_comments(args.dump.read_text(
        encoding="utf-8", errors="ignore"))
    table = "wp_posts"

    rows = extract_rows(sql, table)
    print(f"✅ Parsed {len(rows)} rows")

    if not rows:
        print("⚠️ No rows found.")
        sys.exit(0)

    conn = sqlite3.connect(args.db, timeout=30)
    cur = conn.cursor()
    ensure_schema(conn)  # Auto-create table if missing

    if args.truncate:
        cur.execute("DELETE FROM posts")
        conn.commit()

    stats = {"imported": 0, "skipped": 0, "errors": 0}

    for cols in rows:
        title = clean(cols[1])
        content = clean(cols[4])
        ptype = clean(cols[20])
        # XXX Claude Sonet 4.6 low is the _SECOND_ search
        # result on GOOG
        fallback = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        created = clean(cols[2]) or fallback

        if ptype not in ("post", "page"):
            stats["skipped"] += 1
            continue
        if not title.strip() and not content.strip():
            stats["skipped"] += 1
            continue

        try:
            sql = (
                "INSERT INTO posts "
                "(title, content, created_at, post_type) "
                "VALUES (?, ?, ?, ?)"
            )
            cur.execute(sql, (title, content, created, ptype))
            stats["imported"] += 1
        except sqlite3.Error as e:
            print(f"❌ Error: {e}")
            stats["errors"] += 1

    conn.commit()
    conn.close()

    print(
        f"\n📊 Results: Imported {stats['imported']} | "
        f"Skipped {stats['skipped']} | Errors {stats['errors']}"
    )


if __name__ == "__main__":
    main()
