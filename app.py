import os
import sqlite3
import secrets
import re
import logging
import threading
import time
from functools import wraps

import markdown
from flask import Flask, render_template, request, session, g, jsonify, current_app, redirect, url_for, abort
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash

# Optional: For XSS protection
try:
    import bleach
    BLEACH_AVAILABLE = True
except ImportError:
    BLEACH_AVAILABLE = False

# === LOGGING SETUP ===
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger("wstudio.engine")

# --- 1. CONFIGURATION ---
class Config:
    APP_NAME = "wstudio"
    ORG_NAME = "wstudio labs"
    VERSION = "v0.6.5"
    ADMIN_EMAIL = "ajsbsd@gmail.com"
    
    DATABASE = f"{APP_NAME}.db"
    ARCHIVE_DB = 'imperium_archive.db'
    
    SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))
    DEBUG = True
    
    # Session Security
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Admin Defaults
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin')

# --- 2. AI MANAGER (The Oracle) ---
class OracleManager:
    """Handles AI Model lifecycle and benchmarking."""
    def __init__(self):
        self.repo = "unsloth/SmolLM2-360M-Instruct-GGUF"
        self.file = "SmolLM2-360M-Instruct-Q4_K_M.gguf"
        self.model = None
        self.lock = threading.Lock()

    def load(self):
        with self.lock:
            if self.model is None:
                from llama_cpp import Llama
                from huggingface_hub import hf_hub_download
                
                logger.info(f"Loading Oracle: {self.file}")
                path = hf_hub_download(repo_id=self.repo, filename=self.file)
                self.model = Llama(
                    model_path=path,
                    n_ctx=2048,
                    n_threads=6, # Optimized for Acer Aspire
                    n_gpu_layers=0,
                    verbose=False
                )
                logger.info("Oracle Online.")

    def generate(self, prompt, system_context=""):
        self.load()
        full_prompt = f"CONTEXT:\n{system_context}\n\nQUESTION: {prompt}" if system_context else prompt
        
        start = time.perf_counter()
        with self.lock:
            response = self.model.create_chat_completion(
                messages=[{"role": "user", "content": full_prompt}],
                max_tokens=250,
                temperature=0.2
            )
        duration = time.perf_counter() - start
        
        tokens = response['usage']['completion_tokens']
        tps = tokens / duration if duration > 0 else 0
        
        return {
            "text": response['choices'][0]['message']['content'].strip(),
            "stats": {"tps": round(tps, 2), "time": round(duration, 2)}
        }

oracle = OracleManager()

# --- 3. DATABASE HELPERS ---
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'], timeout=30.0)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA journal_mode=WAL;')
    return g.db

def init_db(app):
    with app.app_context():
        db = get_db()
        # Schema Initialization
        db.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password_hash TEXT, role TEXT DEFAULT "user", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        db.execute('CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, content TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        db.execute('CREATE TABLE IF NOT EXISTS contacts (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT, message TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        db.execute('CREATE TABLE IF NOT EXISTS direct_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, sender_username TEXT, receiver_username TEXT, message TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        
        # Seed Admin
        admin_user = app.config['ADMIN_USERNAME']
        if not db.execute('SELECT 1 FROM users WHERE username = ?', (admin_user,)).fetchone():
            db.execute('INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)', 
                       (admin_user, generate_password_hash(app.config['ADMIN_PASSWORD']), 'admin'))
        db.commit()

# --- 4. APP SETUP ---
app = Flask(__name__)
app.config.from_object(Config)
limiter = Limiter(app=app, key_func=get_remote_address, storage_uri="memory://")

@app.teardown_appcontext
def close_db(e):
    db = g.pop('db', None)
    if db is not None:
        db.close()

@app.context_processor
def inject_branding():
    return {
        'app_name': app.config['APP_NAME'],
        'org_name': app.config['ORG_NAME'],
        'sys_ver': app.config['VERSION'],
        'admin_email': app.config['ADMIN_EMAIL']
    }

# --- 5. SECURITY DECORATORS ---
def login_required(role='user'):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify(output="Auth Required.") if request.path.startswith('/api/') else redirect(url_for('login'))
            if role == 'admin' and session.get('role') != 'admin':
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator

def sanitize(text):
    return bleach.clean(text, tags=[], strip=True) if BLEACH_AVAILABLE else text

# --- 6. TERMINAL COMMAND DISPATCHER ---
class CommandHandler:
    @staticmethod
    def ls(args, db):
        posts = db.execute('SELECT id, title FROM posts').fetchall()
        return "\n".join([f"ID: {p['id']} | {p['title']}" for p in posts]) if posts else "No records."

    @staticmethod
    def cat(args, db):
        if not args: return "Usage: cat [id]"
        res = db.execute('SELECT content FROM posts WHERE id=?', (args,)).fetchone()
        return res['content'] if res else "Not found."

    @staticmethod
    def search(args, db):
        if not os.path.exists(current_app.config['ARCHIVE_DB']):
            return "Archive DB Missing."
        with sqlite3.connect(current_app.config['ARCHIVE_DB']) as s_db:
            rows = s_db.execute("SELECT page_number, snippet(document_pages, 1, '[', ']', '...', 10) FROM document_pages WHERE content MATCH ? LIMIT 3", (args,)).fetchall()
            if not rows: return "No matches."
            session['last_search'] = {"results": [{"page_number": r[0], "snippet": r[1]} for r in rows]}
            return "\n".join([f"PG {r[0]}: {r[1]}" for r in rows])

    @staticmethod
    def ai(args, db):
        # Cooldown
        last = session.get('last_ai', 0)
        if time.time() - last < 5: return f"Wait {int(5-(time.time()-last))}s"
        session['last_ai'] = time.time()

        ctx_text = ""
        if "results" in session.get('last_search', {}) and "based on" in args.lower():
            ctx_text = "\n".join([f"Snippet: {r['snippet']}" for r in session['last_search']['results']])
        
        result = oracle.generate(args, ctx_text)
        return f"ORACLE> {result['text']}\n({result['stats']['tps']} t/s | {result['stats']['time']}s)"

    @staticmethod
    def contact(args, db):
        parts = args.split(' ', 1)
        if len(parts) < 2: return "Usage: contact <email> <msg>"
        db.execute('INSERT INTO contacts (email, message) VALUES (?, ?)', (parts[0], sanitize(parts[1])))
        db.commit()
        return "Logged."

# --- 7. ROUTES ---
@app.route('/')
def index():
    return render_template('terminal.html', show_motd=not session.get('motd_done'))

@app.route('/api/exec', methods=['POST'])
@limiter.limit("30 per minute")
def execute():
    data = request.get_json() or {}
    raw = data.get('command', '').strip()
    if not raw: return jsonify(output="")

    db = get_db()
    parts = raw.split(' ', 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    # Command Map
    commands = {
        "ls": CommandHandler.ls,
        "cat": CommandHandler.cat,
        "search": CommandHandler.search,
        "ai": CommandHandler.ai,
        "contact": CommandHandler.contact
    }

    if cmd in commands:
        output = commands[cmd](args, db)
        return jsonify(output=output)
    
    # Static logic commands
    if cmd == "help":
        return jsonify(output="Available: " + ", ".join(commands.keys()) + ", clear, motd, whoami, startx")
    if cmd == "clear":
        return jsonify(action="clear")
    if cmd == "whoami":
        return jsonify(output=f"{app.config['ADMIN_EMAIL']} (Principal @ {app.config['APP_NAME']})")
    if cmd == "motd":
        return jsonify(output=f"Welcome to {app.config['ORG_NAME']} Shell {app.config['VERSION']}")
    if cmd == "startx":
        if 'user_id' in session:
            target = 'admin_dashboard' if session['role'] == 'admin' else 'user_dashboard'
            return jsonify(action="redirect", url=url_for(target))
        return jsonify(action="startx", url=url_for('login'))

    return jsonify(output=f"Unknown command: {cmd}")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (request.form.get('username'),)).fetchone()
        if user and check_password_hash(user['password_hash'], request.form.get('password')):
            session.update({'user_id': user['id'], 'username': user['username'], 'role': user['role']})
            return redirect(url_for('admin_dashboard' if user['role'] == 'admin' else 'user_dashboard'))
    return render_template('login.html')

@app.route('/admin')
@login_required(role='admin')
def admin_dashboard():
    db = get_db()
    posts = db.execute('SELECT * FROM posts ORDER BY created_at DESC').fetchall()
    msgs = db.execute('SELECT * FROM contacts ORDER BY created_at DESC').fetchall()
    return render_template('admin.html', posts=posts, messages=msgs)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- BOOT ---
if __name__ == '__main__':
    init_db(app)
    app.run(host='127.0.0.1', port=3000, debug=True, use_reloader=False)