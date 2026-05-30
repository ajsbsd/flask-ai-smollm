#!/usr/bin/env python3
import sys
import sqlite3
from werkzeug.security import generate_password_hash

DATABASE = '{{ app_name }}.db'

def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def add_user(username, password, role='user'):
    """Hashes password and inserts user into the SQLite database."""
    conn = get_connection()
    hashed_password = generate_password_hash(password)
    try:
        conn.execute(
            'INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
            (username, hashed_password, role)
        )
        conn.commit()
        print(f"SUCCESS: User '{username}' successfully registered as '{role}'.")
    except sqlite3.IntegrityError:
        print(f"ERROR: Username '{username}' is already taken.")
    finally:
        conn.close()

def list_users():
    """Outputs all currently registered users in a clean console format."""
    conn = get_connection()
    try:
        users = conn.execute('SELECT id, username, role, created_at FROM users').fetchall()
        print("\n" + "=" * 65)
        print(f"{'ID':<5} | {'Username':<20} | {'Role':<10} | {'Created At':<20}")
        print("=" * 65)
        for u in users:
            print(f"{u['id']:<5} | {u['username']:<20} | {u['role']:<10} | {u['created_at']}")
        print("=" * 65 + "\n")
    except sqlite3.OperationalError:
        print("ERROR: Database table 'users' does not exist. Run the Flask server once to initialize it.")
    finally:
        conn.close()

def show_usage():
    print("Sovereign User Management Tool")
    print("Usage:")
    print("  python3 manage_users.py add <username> <password> <role>")
    print("  python3 manage_users.py list")
    print("\nRoles:")
    print("  admin  - Has full access to the administrative post and contact controls")
    print("  user   - Has restricted access to standard user transmissions/messages")
    print("\nExamples:")
    print("  python3 manage_users.py add alex securepass123 user")
    print("  python3 manage_users.py add aaron complexpass456 admin")

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
        username = sys.argv[2].strip()
        password = sys.argv[3].strip()
        role = sys.argv[4].strip().lower()
        
        if role not in ['admin', 'user']:
            print("Error: Role must be either 'admin' or 'user'.")
            sys.exit(1)
            
        add_user(username, password, role)
        
    elif action == 'list':
        list_users()
        
    else:
        show_usage()
