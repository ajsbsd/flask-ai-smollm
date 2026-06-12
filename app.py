import logging
import os
import re
import sqlite3
import threading
import time
from functools import wraps

from flask import (Flask, abort, current_app, g, jsonify, redirect,
                   render_template, request, session, url_for)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from markupsafe import escape
from werkzeug.security import check_password_hash, generate_password_hash

# Optional: For XSS protection
try:
    import bleach
    BLEACH_AVAILABLE = True
except ImportError:
    BLEACH_AVAILABLE = False

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s:%(name)s:%(message)s'
)

logger = logging.getLogger(__name__)


# --- 1. CONFIGURATION ---


class Config:
    APP_NAME = "ajsbsd"
    ORG_NAME = "ajsbsd.net"
    VERSION = "v0.7.7"
    ADMIN_EMAIL = "ajsbsd@gmail.com"

    DATABASE = f"{APP_NAME}.db"
    ARCHIVE_DB = 'imperium_archive.db'

    # Fail fast if SECRET_KEY is not set
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY environment variable is not set. Run:\n"
            "export SECRET_KEY=$(python3 -c 'import secrets; "
            "print(secrets.token_hex(32))')"
        )

    DEBUG = os.environ.get('DEBUG', 'false').lower() == 'true'

    # Session Security
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Admin Defaults
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin')


# --- 2. AI MANAGER (The Oracle) ---
_ai_cooldowns = {}
_ai_cooldown_lock = threading.Lock()


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
                from huggingface_hub import hf_hub_download
                from llama_cpp import Llama

                logger.info(f"Loading Oracle: {self.file}")
                path = hf_hub_download(repo_id=self.repo, filename=self.file)
                self.model = Llama(
                    model_path=path, n_ctx=2048, n_threads=6,
                    n_gpu_layers=0, verbose=False
                )
                logger.info("Oracle Online.")

    def generate(self, prompt, system_context=""):
        self.load()
        if system_context:
            full_prompt = (
                f"CONTEXT:\n{system_context}\n\nQUESTION: {prompt}"
            )
        else:
            full_prompt = prompt

        start = time.perf_counter()
        with self.lock:
            response = self.model.create_chat_completion(
                messages=[{"role": "user", "content": full_prompt}],
                max_tokens=250, temperature=0.2
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


def get_archive_db():
    """Helper to connect to the archive database."""
    if 'archive_db' not in g:
        db_path = current_app.config['ARCHIVE_DB']
        if not os.path.exists(db_path):
            return None
        g.archive_db = sqlite3.connect(db_path, timeout=30.0)
        g.archive_db.row_factory = sqlite3.Row
    return g.archive_db


def init_db(app):
    with app.app_context():
        db = get_db()
        # Use executescript for cleaner multi-table creation
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE,
                password_hash TEXT, role TEXT DEFAULT 'user',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT, message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS direct_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, sender_username TEXT,
                receiver_username TEXT, message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        """)

        admin_user = app.config['ADMIN_USERNAME']
        if not db.execute(
            'SELECT 1 FROM users WHERE username = ?',
            (admin_user,)
        ).fetchone():
            db.execute(
                'INSERT INTO users (username, password_hash, role) '
                'VALUES (?, ?, ?)',
                (
                    admin_user,
                    generate_password_hash(app.config['ADMIN_PASSWORD']),
                    'admin'
                )
            )
        db.commit()


# --- 4. APP SETUP ---
app = Flask(__name__)
app.config.from_object(Config)

limiter = Limiter(
    app=app, key_func=get_remote_address, storage_uri="memory://"
)

with app.app_context():
    init_db(app)


@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db is not None:
        db.close()

    archive_db = g.pop('archive_db', None)
    if archive_db is not None:
        archive_db.close()


@app.context_processor
def inject_branding():
    return {
        'app_name': app.config['APP_NAME'],
        'org_name': app.config['ORG_NAME'],
        'sys_ver': app.config['VERSION'],
        'admin_email': app.config['ADMIN_EMAIL']}

# --- 5. SECURITY & UTILITIES ---


def login_required(role='user'):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                if request.path.startswith('/api/'):
                    return jsonify(output="Auth Required."), 401
                return redirect(url_for('login'))
            if role == 'admin' and session.get('role') != 'admin':
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


def sanitize(text):
    """Sanitize text to prevent XSS."""
    if not text:
        return ""
    if BLEACH_AVAILABLE:
        return bleach.clean(text, tags=[], strip=True)
    # Fallback to basic HTML escaping if bleach is missing (prevents failing
    # open)
    return str(escape(text))

# --- 6. TERMINAL COMMAND DISPATCHER ---


class CommandHandler:
    @staticmethod
    def ls(args, ctx):
        posts = ctx['db'].execute('SELECT id, title FROM posts').fetchall()
        return (
            "\n".join([f"ID: {p['id']} | {p['title']}" for p in posts])
            if posts else "No records."
        )

    @staticmethod
    def cat(args, ctx):
        if not args.strip():
            return "Usage: cat [id]"
        if not args.strip().isdigit():
            return "Error: ID must be a number. Usage: cat [id]"

        post_id = int(args.strip())
        res = ctx['db'].execute(
            'SELECT content FROM posts WHERE id=?', (post_id,)).fetchone()
        return res['content'] if res else f"No post with ID {post_id}."

    @staticmethod
    def search(args, ctx):
        if not args.strip():
            return "Usage: search [term]\nExample: search Avakov"

        clean_args = re.sub(r'[^a-zA-Z0-9\s*]', '', args).strip()
        if not clean_args:
            return "Error: Search term must contain letters or numbers."

        s_db = get_archive_db()
        if not s_db:
            return (
                "Error: imperium_archive.db not found. "
                "Build your index first."
            )

        try:
            rows = s_db.execute(
                "SELECT page_number, "
                "snippet(document_pages, 1, '[', ']', '...', 10) "
                "FROM document_pages WHERE content MATCH ? LIMIT 3",
                (clean_args,)
            ).fetchall()

            if not rows:
                return f"No matches found for '{clean_args}'."

            # Update session via the context dictionary
            ctx['session']['last_search'] = {"results": [
                {"page_number": r[0], "snippet": r[1]} for r in rows]}
            return "\n".join([f"PG {r[0]}: {r[1]}" for r in rows])

        except sqlite3.OperationalError as e:
            logger.error(f"FTS5 Search Query failed: {e}")
            return (
                "Error: Invalid search syntax. "
                "Please use alphanumeric characters only."
            )

    @staticmethod
    def ai(args, ctx):
        ip = ctx['ip']
        now = time.time()

        with _ai_cooldown_lock:
            last = _ai_cooldowns.get(ip, 0)
            wait = 5 - (now - last)
            if wait > 0:
                return f"Wait {int(wait) + 1}s before next query."
            _ai_cooldowns[ip] = now

        ctx_text = ""
        last_search = ctx['session'].get('last_search', {})
        if "results" in last_search and "based on" in args.lower():
            ctx_text = "\n".join(
                [f"Snippet: {r['snippet']}" for r in last_search['results']])

        result = oracle.generate(args, ctx_text)
        return (
            f"ORACLE> {result['text']}\n"
            f"({result['stats']['tps']} t/s | {result['stats']['time']}s)"
        )

    @staticmethod
    def contact(args, ctx):
        parts = args.split(' ', 1)
        if len(parts) < 2:
            return "Usage: contact <email> <msg>"

        ctx['db'].execute(
            'INSERT INTO contacts (email, message) VALUES (?, ?)',
            (parts[0], sanitize(parts[1]))
        )
        ctx['db'].commit()
        return "Logged."

    @staticmethod
    def help(args, ctx):
        cmds = [
            "ls",
            "cat",
            "search",
            "ai",
            "contact",
            "clear",
            "music",
            "docs",
            "frames",
            "motd",
            "whoami",
            "startx"]
        return "Available: " + ", ".join(cmds)


    @staticmethod
    def docs(args, ctx):
        a_db = get_archive_db()
        if not a_db:
            return "Error: imperium_archive.db not found."

        try:
            rows = a_db.execute(
                """
                SELECT id, title
                FROM documents
                ORDER BY id
                """
            ).fetchall()

            if not rows:
                return "No documents found."

            return "\n".join(
                f"{row['id']}: {row['title']}"
                for row in rows
            )

        except sqlite3.OperationalError as exc:
            return f"Database error: {exc}"

    @staticmethod
    def clear(args, ctx): return {"action": "clear"}

    @staticmethod
    def music(args, ctx):
        if args in ("start", "on"):
            return {
                "action": "play_music",
                "output": "[ OK ] Ambient audio enabled."}
        elif args in ("stop", "off"):
            return {
                "action": "stop_music",
                "output": "[ OK ] Ambient audio terminated."}
        return "Usage: music [start|stop]"

    @staticmethod
    def whoami(args, ctx):
        username = ctx['session'].get('username', 'guest')
        role = ctx['session'].get('role', 'guest')
        return f"{username} ({role})"

    @staticmethod
    def motd(args, ctx):
        return (
            f"Welcome to {current_app.config['ORG_NAME']} "
            f"Shell {current_app.config['VERSION']}"
        )

    @staticmethod
    def startx(args, ctx):
        if 'user_id' in ctx['session']:
            target = (
                'admin_dashboard'
                if ctx['session'].get('role') == 'admin'
                else 'user_dashboard'
            )
            return {"action": "redirect", "url": url_for(target)}
        return {"action": "startx", "url": url_for('login')}

    @staticmethod
    def frames(args, ctx):
        """Displays video stills associated with a document ID."""
        if not args.strip():
            return "Usage: frames [document_id]"
        if not args.strip().isdigit():
            return "Error: ID must be a number. Usage: frames [id]"

        doc_id = int(args.strip())
        a_db = get_archive_db()
        if not a_db:
            return "Error: imperium_archive.db not found."

        try:
            rows = a_db.execute(
                "SELECT frame_path, timestamp_sec "
                "FROM video_frames WHERE document_id = ? "
                "ORDER BY timestamp_sec",
                (doc_id,)
            ).fetchall()

            if not rows:
                return f"No video frames found for document ID {doc_id}."

            # We use <br> tags to create line breaks in the HTML terminal
            output = ["<br>--- Video Stills ---<br>"]

            for row in rows:
                # row[0] is 'static/images/...' -> url_for needs 'images/...'
                filename = row[0].replace('static/', '', 1)
                img_url = url_for('static', filename=filename)
                timestamp = row[1]

                # Create an HTML image tag with inline CSS for terminal style
                img_html = (
                    f'<img src="{img_url}" style="max-width: 300px; '
                    f'display: block; margin: 10px 0; '
                    f'border: 1px solid #444; background: #000;">'
                )
                output.append(img_html)
                output.append(
                    f'<span style="color: #888;">'
                    f'Timestamp: {timestamp}s</span><br>'
                )

            return "\n".join(output)

        except sqlite3.OperationalError:
            return (
                "Error: 'video_frames' table not found. "
                "Did you run the SQL script to create it?"
            )


COMMAND_MAP = {
    "ls": CommandHandler.ls,
    "cat": CommandHandler.cat,
    "search": CommandHandler.search,
    "ai": CommandHandler.ai,
    "contact": CommandHandler.contact,
    "help": CommandHandler.help,
    "clear": CommandHandler.clear,
    "music": CommandHandler.music,
    "docs": CommandHandler.docs,
    "frames": CommandHandler.frames,
    "whoami": CommandHandler.whoami,
    "motd": CommandHandler.motd,
    "startx": CommandHandler.startx,
    }

# --- 7. ROUTES ---


@app.route('/')
def index():
    return render_template('terminal.html',
                           show_motd=not session.get('motd_done'))


@app.route('/api/exec', methods=['POST'])
@limiter.limit("30 per minute")
def execute():
    data = request.get_json() or {}
    raw = data.get('command', '').strip()
    if not raw:
        return jsonify(output="")

    parts = raw.split(' ', 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd not in COMMAND_MAP:
        return jsonify(output=f"Unknown command: {cmd}")

    # Build context for command handlers (decouples them from Flask proxies)
    ctx = {
        'db': get_db(),
        'ip': request.remote_addr,
        'session': dict(session)
    }

    output = COMMAND_MAP[cmd](args, ctx)

    # Write back to session if modified by the command (e.g. search)
    if 'last_search' in ctx['session']:
        session['last_search'] = ctx['session']['last_search']

    # Dict outputs contain special client-side actions (redirects, clears)
    if isinstance(output, dict):
        return jsonify(output)

    return jsonify(output=output)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        db = get_db()
        username = request.form.get('username')
        password = request.form.get('password')

        #logger.debug(f"Login attempt for username: '{username}'")
        # SECURITY FIX: NEVER log passwords in plaintext
        logger.debug(
            "Login attempt for username: '%s'",
            username,
        )

        user = db.execute(
            'SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session.update({
                'user_id': user['id'],
                'username': user['username'],
                'role': user['role']
            })
            logger.debug("Login successful. Redirecting to dashboard...")
            target = (
                'admin_dashboard'
                if user['role'] == 'admin'
                else 'user_dashboard'
            )
            return redirect(url_for(target))

        # Generic error message prevents user enumeration
        logger.warning(f"Authentication failed for username: '{username}'")
        return render_template('login.html',
                               error="Invalid username or password.")

    return render_template('login.html')


@app.route('/admin')
@login_required(role='admin')
def admin_dashboard():
    db = get_db()
    posts = db.execute(
        'SELECT * FROM posts ORDER BY created_at DESC').fetchall()
    msgs = db.execute(
        'SELECT * FROM contacts ORDER BY created_at DESC').fetchall()
    return render_template('admin.html', posts=posts, messages=msgs)


@app.route('/dashboard')
@login_required(role='user')
def user_dashboard():
    return render_template('dashboard.html')


@app.route('/admin/post/new', methods=['GET', 'POST'])
@login_required(role='admin')
def new_post():
    if request.method == 'POST':
        title = sanitize(request.form.get('title', '').strip())
        content = sanitize(request.form.get('content', '').strip())
        if not title or not content:
            return render_template(
                'new_post.html',
                error="Title and content required.")

        db = get_db()
        db.execute(
            'INSERT INTO posts (title, content) VALUES (?, ?)',
            (title, content))
        db.commit()
        return redirect(url_for('admin_dashboard'))
    return render_template('new_post.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route("/admin/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required(role="admin")
def edit_post(post_id):
    db = get_db()
    post = db.execute("SELECT * FROM posts WHERE id=?", (post_id,)).fetchone()
    if not post:
        abort(404)

    if request.method == "POST":
        title = sanitize(request.form.get("title", "").strip())
        content = sanitize(request.form.get("content", "").strip())
        if not title or not content:
            return render_template(
                "edit_post.html",
                post=post,
                error="Title and content required.")

        db.execute("UPDATE posts SET title=?, content=? WHERE id=?",
                   (title, content, post_id))
        db.commit()
        return redirect(url_for("admin_dashboard"))

    return render_template("edit_post.html", post=post)


@app.route("/admin/post/<int:post_id>/delete", methods=["POST"])
@login_required(role="admin")
def delete_post(post_id):
    db = get_db()
    db.execute("DELETE FROM posts WHERE id=?", (post_id,))
    db.commit()
    return redirect(url_for("admin_dashboard"))

@app.route("/player")
def player():
    slides = [
        {
            "start": 0,
            "end": 10,
            "image": url_for(
                "static",
                filename="images/OpenBSD_frames/frame_1.jpg"
            ),
            "text": "Transcript text for first 10 seconds"
        },
        {
            "start": 10,
            "end": 20,
            "image": url_for(
                "static",
                filename="images/OpenBSD_frames/frame_2.jpg"
            ),
            "text": "Transcript text for second 10 seconds"
        },
        {
            "start": 20,
            "end": 30,
            "image": url_for(
                "static",
                filename="images/OpenBSD_frames/frame_3.jpg"
            ),
            "text": "Transcript text for third 10 seconds"
        },
        {
            "start": 30,
            "end": 40,
            "image": url_for(
                "static",
                filename="images/OpenBSD_frames/frame_4.jpg"
            ),
            "text": "Transcript text for fourth 10 seconds"
        }
    ]

    return render_template(
        "player.html",
        slides=slides,
        audio_url=url_for(
            "static",
            filename="audio/OpenBSD.mp3"
        )
    )


# --- BOOT ---
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=3000, debug=True, use_reloader=False)
