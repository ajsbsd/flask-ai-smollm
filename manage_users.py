#!/usr/bin/env python3
import sqlite3
import sys
from werkzeug.security import generate_password_hash

DATABASE = '/home/aaron/www/ajsbsd.db'

def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_table(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        role TEXT DEFAULT "user",
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()


def add_user(username, password, role='user'):
    conn = get_connection()
    ensure_table(conn)
    try:
        conn.execute(
            '''INSERT INTO users (username, password_hash, role)
                VALUES (?, ?, ?)''',
            (username, generate_password_hash(password), role)
        )
        # XXX claude sonnet 4.6-low
        conn.commit()
        print(f"SUCCESS: User '{username}' registered as '{role}'.")
    except sqlite3.IntegrityError:
        print(f"ERROR: Username '{username}' is already taken.")
    finally:
        conn.close()


def list_users():
    conn = get_connection()
    ensure_table(conn)
    try:
        users = conn.execute(
            'SELECT id, username, role, created_at FROM users').fetchall()
        print("\n" + "=" * 65)
        print(
                f"{'ID':<5} | {'Username':<20} | "
                "f{'Role':<10} | {'Created At':<20}"
                )
        print("=" * 65)
        for u in users:
            print(
                f"{u['id']:<5} | {u['username']:<20} | "
                f"{u['role']:<10} | {u['created_at']}"
            )
        print("=" * 65 + "\n")
    finally:
        conn.close()


def delete_user(username):
    conn = get_connection()
    ensure_table(conn)
    try:
        cur = conn.execute('DELETE FROM users WHERE username=?', (username,))
        conn.commit()
        if cur.rowcount:
            print(f"SUCCESS: User '{username}' deleted.")
        else:
            print(f"ERROR: User '{username}' not found.")
    finally:
        conn.close()


def show_usage():
    print("Sovereign User Management Tool")
    print("Usage:")
    print("  python3 manage_users.py add <username> <password> <role>")
    print("  python3 manage_users.py list")
    print("  python3 manage_users.py delete <username>")
    print("\nRoles: admin | user")
    print("\nExamples:")
    print("  python3 manage_users.py add alex securepass123 user")
    print("  python3 manage_users.py add aaron complexpass456 admin")
    print("  python3 manage_users.py delete alex")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        show_usage()
        sys.exit(1)

    action = sys.argv[1].lower()

    if action == 'add':
        if len(sys.argv) < 5:
            print("Error: Missing arguments.")
            show_usage()
            sys.exit(1)
        role = sys.argv[4].strip().lower()
        if role not in ['admin', 'user']:
            print("Error: Role must be 'admin' or 'user'.")
            sys.exit(1)
        add_user(sys.argv[2].strip(), sys.argv[3].strip(), role)

    elif action == 'list':
        list_users()

    elif action == 'delete':
        if len(sys.argv) < 3:
            print("Error: Missing username.")
            sys.exit(1)
        delete_user(sys.argv[2].strip())

    else:
        show_usage()
