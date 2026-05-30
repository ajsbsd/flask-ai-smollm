# === STANDARD LIBRARY ===
import os
import sqlite3
import json
import secrets
import re
import logging
import threading
import time
from functools import wraps

# === THIRD-PARTY ===
import markdown
from flask import Flask, render_template, request, session, g, jsonify, current_app, redirect, url_for, abort
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from markupsafe import Markup

# === OPTIONAL DEPENDENCIES ===
try:
    from dotenv import load_dotenv
    load_dotenv()  # Explicitly inject .env values into os.environ for Gunicorn
except ImportError:
    pass

try:
    import bleach
    BLEACH_AVAILABLE = True
except ImportError:
    BLEACH_AVAILABLE = False

# === LOGGING SETUP ===
logger = logging.getLogger("ai.engine")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s %(levelname)s:%(name)s:%(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

# --- 1. AI SETUP (SmolLM2-360M-Instruct GGUF via Unsloth) ---
print("Initializing system...")
GGUF_REPO = "unsloth/SmolLM2-360M-Instruct-GGUF"
GGUF_FILE = "SmolLM2-360M-Instruct-Q4_K_M.gguf"

# Global thread lock and model pointer
ai_lock = threading.Lock()
model = None

def load_ai():
    global model
    with ai_lock:
        if model is None:
            from llama_cpp import Llama
            from huggingface_hub import hf_hub_download
            
            logger.info("Downloading/loading SmolLM2 GGUF model...")
            model_path = hf_hub_download(repo_id=GGUF_REPO, filename=GGUF_FILE)
            
            model = Llama(
                model_path=model_path,
                n_ctx=2048,  # SmolLM2 supports up to 8192 context size, but 2048 is faster on CPU
                n_threads=1,
                n_gpu_layers=0,
                verbose=False
            )
            print("AI Model loaded (SmolLM2-360M-Instruct GGUF 4-bit) on CPU")

# --- 2. CONFIG ---
class Config:
    DATABASE = 'micropress.db'
    ARCHIVE_DB = 'imperium_archive.db'
    DEBUG = True
    SESSION_COOKIE_SECURE = False  # Set to True if deploying on HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Secure Session Key management
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        is_dev = os.environ.get('FLASK_DEBUG') in ['1', 'True', 'true'] or os.environ.get('FLASK_ENV') == 'development'
        if is_dev:
            logger.warning("WARNING: No SECRET_KEY set. Falling back to insecure development key.")
            SECRET_KEY = 'dev_key_892301823091_insecure_fallback'
        else:
            logger.warning("WARNING: SECRET_KEY environment variable not found. Generating a secure transient key.")
            SECRET_KEY = secrets.token_hex(32)

    # Admin Credentials Setup
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
    
    if not ADMIN_PASSWORD:
        is_dev = os.environ.get('FLASK_DEBUG') in ['1', 'True', 'true'] or os.environ.get('FLASK_ENV') == 'development'
        if is_dev:
            logger.warning("WARNING: ADMIN_PASSWORD not set. Falling back to development default: 'admin'")
            ADMIN_PASSWORD = 'admin'
        else:
            # Generate a secure transient admin password on boot so there is no hardcoded backdoor
            ADMIN_PASSWORD = secrets.token_hex(16)
            print("\n" + "=" * 70)
            print("SECURITY WARNING: ADMIN_PASSWORD environment variable not found.")
            print(f"GENERATED TRANSIENT ADMIN PASSWORD FOR THIS LIFECYCLE:\n{ADMIN_PASSWORD}")
            print("=" * 70 + "\n")
            logger.info("Generated secure transient admin password for Gunicorn lifecycle.")

# --- 3. APP INITIALIZATION ---
app = Flask(__name__)
app.config.from_object(Config)

# --- 4. RATE LIMITING ---
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per hour", "20 per minute"],
    storage_uri="memory://"
)

# --- 5. DECORATORS & SECURITY HELPERS ---
def login_required(role='user'):
    """Restricts route access based on active role ('admin' or 'user')."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('user_id'):
                if request.path.startswith('/api/'):
                    return jsonify(output="Error: Unauthorized. Login required."), 401
                return redirect(url_for('login'))
            
            current_role = session.get('role', 'user')
            if role == 'admin' and current_role != 'admin':
                if request.path.startswith('/api/'):
                    return jsonify(output="Error: Forbidden. Admin permissions required."), 403
                abort(403)
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def sanitize_input(text):
    """Sanitizes text content to mitigate XSS risks before database storage."""
    if BLEACH_AVAILABLE and text:
        # Strip all HTML tags entirely for plain-text storage safety
        return bleach.clean(text, tags=[], strip=True)
    return text

# --- 6. DATABASE HELPER ---
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['DATABASE'], timeout=30.0)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL;')
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# --- 7. APP STARTUP: Ensure DB schema exists ---
def init_db():
    """Create tables if they don't exist and automatically migrate schema."""
    with app.app_context():
        try:
            db = get_db()
            
            # 1. Users table (Supports both admin and messaging users)
            db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            db.commit()

            # 2. Seed default system admin if missing from SQLite
            admin_user = app.config['ADMIN_USERNAME']
            raw_pass = app.config['ADMIN_PASSWORD']
            
            if not raw_pass.startswith(('pbkdf2:', 'scrypt:', 'bcrypt:')):
                hashed_pass = generate_password_hash(raw_pass)
            else:
                hashed_pass = raw_pass

            admin_exists = db.execute('SELECT 1 FROM users WHERE username = ?', (admin_user,)).fetchone()
            if not admin_exists:
                db.execute(
                    'INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)',
                    (admin_user, hashed_pass, 'admin')
                )
                db.commit()
                logger.info(f"Seeded default administrator profile: '{admin_user}'")

            # 3. Direct Messages table (Communications database)
            db.execute('''
                CREATE TABLE IF NOT EXISTS direct_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_username TEXT NOT NULL,
                    receiver_username TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            db.commit()

            # 4. Posts table
            db.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL
                )
            ''')
            db.commit()
            
            # 5. Contacts table for storing contact command submissions
            db.execute('''
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            db.commit()
            
            # Auto-migration: ensure created_at column is present on posts
            try:
                db.execute('ALTER TABLE posts ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
                db.commit()
                logger.info("Applied migration: created_at column ensured")
            except sqlite3.OperationalError:
                pass
                
            logger.info("Database schema initialized")
        except Exception as e:
            logger.error(f"DB init error: {e}")

# Call immediately after app config to initialize DB and pre-load model on Gunicorn worker startup
init_db()
load_ai()

# --- 8. TERMINAL API ---
@app.route('/')
def index():
    """Renders the interactive terminal console with transient MOTD checks [2]."""
    show_motd = not session.get('terminal_motd_shown', False)
    if show_motd:
        session['terminal_motd_shown'] = True # Block subsequent load displays [2]
    return render_template('terminal.html', show_motd=show_motd)

@app.route('/api/exec', methods=['POST'])
@limiter.limit("30 per minute")
def execute():
    """Main terminal command dispatcher."""
    data = request.get_json() or {}
    raw_input = data.get('command', '').strip()
    if not raw_input:
        return jsonify(output="")

    db = get_db()
    parts = raw_input.split(' ')
    cmd = parts[0].lower()
    args = " ".join(parts[1:])

    # --- COMMANDS ---
    if cmd == 'help':
        return jsonify(output="Available: ls, cat [id], search [term], ai [prompt], contact [email] [message], startx, motd, clear, whoami")

    elif cmd == 'ls':
        posts = db.execute('SELECT id, title FROM posts').fetchall()
        if not posts:
            return jsonify(output="No documents found.")
        return jsonify(output="\n".join([f"ID: {p['id']} | {p['title']}" for p in posts]))

    elif cmd == 'cat':
        if not args:
            return jsonify(output="Usage: cat [id]")
        post = db.execute('SELECT content FROM posts WHERE id=?', (args,)).fetchone()
        return jsonify(output=post['content'] if post else "Error: Document not found.")

    elif cmd == 'search':
        if not os.path.exists(app.config['ARCHIVE_DB']):
            return jsonify(output="Error: imperium_archive.db not found. Build your index first.")
        
        search_db = sqlite3.connect(app.config['ARCHIVE_DB'])
        try:
            results = search_db.execute("""
                SELECT page_number, snippet(document_pages, 1, '[', ']', '...', 10)
                FROM document_pages WHERE content MATCH ?
                ORDER BY bm25(document_pages) LIMIT 3
            """, (args,)).fetchall()
            
            if not results:
                return jsonify(output="No matches found in research archive.")
            
            session['last_search'] = {
                "query": args,
                "results": [{"page_number": r[0], "snippet": r[1]} for r in results]
            }
            return jsonify(output="\n".join([f"PG {r[0]}: {r[1]}" for r in results]))
        except sqlite3.Error as e:
            return jsonify(output=f"Archive Error: {e}")
        finally:
            search_db.close()

    elif cmd == 'ai':
        # === SPECIFIC RATE LIMIT (COOLDOWN) ===
        last_ai_time = session.get('last_ai_time', 0.0)
        now = time.time()
        if now - last_ai_time < 5.0:
            cooldown_remaining = int(5.0 - (now - last_ai_time))
            return jsonify(output=f"SYSTEM> Cooldown active. Please wait {cooldown_remaining} seconds before querying the AI again.")
        session['last_ai_time'] = now

        logger.debug(f"Generating response for prompt: {args[:100]}...")
        load_ai()
        
        # === RAG CONTEXT INJECTION ===
        context_injected = False
        context_text = ""
        
        prompt_lower = args.lower().strip()
        if any(phrase in prompt_lower for phrase in [
            "based on the search", 
            "from the results", 
            "using the snippets",
            "according to the archive"
        ]) and 'last_search' in session:
            
            ctx = session['last_search']
            if ctx.get('results'):
                context_text = "\n".join([f"[PG {r['page_number']}]: {r['snippet']}" for r in ctx['results']])
                logger.debug(f"Injected RAG context: {len(ctx['results'])} snippets")
                context_injected = True
        
        if context_injected:
            system_prompt = f"""You are a research analyst. Answer using ONLY the retrieved snippets below. If the answer isn't in the snippets, say "Insufficient context in archive."

RETRIEVED CONTEXT:
{context_text}

USER QUESTION: {args}"""
        else:
            if 'last_search' not in session:
                logger.warning("No last_search in session — RAG context unavailable")
            system_prompt = args
        
        # === MODEL GENERATION ===
        messages = [{"role": "user", "content": system_prompt}]
        
        # Serialize model invocation to prevent threading/CPU race conditions inside llama-cpp
        with ai_lock:
            response = model.create_chat_completion(
                messages=messages,
                max_tokens=150,
                temperature=0.2,
                repeat_penalty=1.2,
                stop=["<|im_end|>", "\n\n"]
            )
        
        generated = response['choices'][0]['message']['content']
        
        # Extract and hide thinking block (kept as a safety mechanism)
        if "<think>" in generated and "</think>" in generated:
            parts = generated.split("</think>")
            thoughts = parts[0].replace("<think>", "").strip()
            logger.debug(f"ORACLE INTERNAL THOUGHTS: {thoughts}") 
            generated = parts[1].strip()
        
        if generated.count("This is because") > 2:
            generated = generated.split("This is because")[0].strip()
        
        suffix = " [CONTEXT: grounded]" if context_injected else " [CONTEXT: none]"
        logger.debug(f"Generated {len(generated.split())} tokens{suffix}")
        
        return jsonify(output=f"ORACLE> {generated.strip()}{suffix}")

    elif cmd == 'contact':
        if not args:
            return jsonify(output="Usage: contact <email> <your message>\nExample: contact ajsbsd@gmail.com Hi, love the site!")
            
        parts = args.split(' ', 1)
        email = parts[0].strip()
        
        email_regex = r"^[\w\.-]+@[\w\.-]+\.\w+$"
        if not re.match(email_regex, email):
            return jsonify(output="Error: A valid email address is mandatory.\nUsage: contact <email> <message>")
            
        if len(parts) < 2 or not parts[1].strip():
            return jsonify(output="Error: Message content cannot be empty.\nUsage: contact <email> <message>")
            
        message = sanitize_input(parts[1].strip())
        
        try:
            db.execute('INSERT INTO contacts (email, message) VALUES (?, ?)', (email, message))
            db.commit()
            logger.info(f"New contact submission registered from: {email}")
            return jsonify(output="SYSTEM> Connection established. Message successfully logged to database.")
        except Exception as e:
            logger.error(f"Failed to log contact message: {e}")
            return jsonify(output=f"SYSTEM ERROR: Transmission failed. {e}")

    elif cmd == 'startx':
        if session.get('user_id'):
            role = session.get('role', 'user')
            if role == 'admin':
                return jsonify(action='redirect', url=url_for('admin_dashboard'))
            else:
                return jsonify(action='redirect', url=url_for('user_dashboard'))
        
        return jsonify(action='startx', url=url_for('login'), output="SYSTEM> Requesting graphics server interface...")

    elif cmd == 'motd':
        # Direct CLI invocation for the MOTD banner [3]
        motd_text = (
            "======================================================================\n"
            "* Sovereign OS v0.6 - SYSTEM MESSAGE OF THE DAY (MOTD) *\n"
            "======================================================================\n"
            "Welcome to the workspace of Aaron (Senior Linux Engineer).\n\n"
            "To establish communication or submit direct inquiries:\n"
            "- EMAIL: ajsbsd@gmail.com\n"
            "- SHELL: Run the 'contact <email> <message>' command directly \n"
            "         from this terminal console.\n\n"
            "* Type 'help' to view all available shell subcommands.\n"
            "======================================================================"
        )
        return jsonify(output=motd_text)

    elif cmd == 'clear':
        return jsonify(action='clear')

    elif cmd == 'whoami':
        return jsonify(output="ajsbsd@gmail.com (Senior Linux Engineer)")

    return jsonify(output=f"sh: command not found: {cmd}")

# --- 9. ADMIN DASHBOARD & CRUD ROUTES ---

@app.route('/admin')
@limiter.exempt
@login_required(role='admin')
def admin_dashboard():
    """Renders the admin dashboard with posts, feedback forms, and inbox."""
    db = get_db()
    posts = db.execute('SELECT * FROM posts ORDER BY created_at DESC').fetchall()
    messages = db.execute('SELECT * FROM contacts ORDER BY created_at DESC').fetchall()
    
    show_motd = session.get('show_motd', False)
    if show_motd:
        session['show_motd'] = False # Reset flag
        
    return render_template('admin.html', posts=posts, messages=messages, show_motd=show_motd)

@app.route('/admin/new', methods=['GET', 'POST'])
@limiter.exempt
@login_required(role='admin')
def new_post():
    """Handles displaying the 'New Post' page and saving the post."""
    if request.method == 'POST':
        title = sanitize_input(request.form.get('title', '').strip())
        content = sanitize_input(request.form.get('content', '').strip())
        
        if title and content:
            db = get_db()
            try:
                db.execute('INSERT INTO posts (title, content) VALUES (?, ?)', (title, content))
                db.commit()
                logger.info(f"Created new post: '{title}'")
                return redirect(url_for('admin_dashboard'))
            except Exception as e:
                logger.error(f"Error creating post: {e}")
                
    return render_template('new_post.html')


@app.route('/admin/edit/<int:post_id>', methods=['GET', 'POST'])
@limiter.exempt
@login_required(role='admin')
def edit_post(post_id):
    """Handles retrieving a post to edit and updating its content."""
    db = get_db()
    post = db.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    
    if not post:
        abort(404, description="Post not found")
        
    if request.method == 'POST':
        title = sanitize_input(request.form.get('title', '').strip())
        content = sanitize_input(request.form.get('content', '').strip())
        
        if title and content:
            try:
                db.execute('UPDATE posts SET title = ?, content = ? WHERE id = ?', (title, content, post_id))
                db.commit()
                logger.info(f"Updated post ID {post_id}: '{title}'")
                return redirect(url_for('admin_dashboard'))
            except Exception as e:
                logger.error(f"Error updating post ID {post_id}: {e}")
                
    return render_template('edit_post.html', post=post)


@app.route('/admin/delete/<int:post_id>', methods=['POST'])
@limiter.exempt
@login_required(role='admin')
def delete_post(post_id):
    """Handles safe deletion of a post via a POST request."""
    db = get_db()
    try:
        db.execute('DELETE FROM posts WHERE id = ?', (post_id,))
        db.commit()
        logger.info(f"Deleted post ID {post_id}")
    except Exception as e:
        logger.error(f"Failed to delete post ID {post_id}: {e}")
        
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/messages')
@limiter.exempt
@login_required(role='admin')
def admin_messages():
    """Renders contact us submissions using template file."""
    db = get_db()
    messages = db.execute('SELECT * FROM contacts ORDER BY created_at DESC').fetchall()
    return render_template('admin/messages.html', messages=messages)


# --- 10. USER PORTAL & COMMUNICATION ENDPOINTS ---

@app.route('/user')
@limiter.exempt
@login_required(role='user')
def user_dashboard():
    """Renders standard user messaging interface using external template file."""
    db = get_db()
    current_username = session.get('username')
    
    show_motd = session.get('show_motd', False)
    if show_motd:
        session['show_motd'] = False # Clear from session after load
        
    received = db.execute('''
        SELECT * FROM direct_messages 
        WHERE receiver_username = ? 
        ORDER BY created_at DESC
    ''', (current_username,)).fetchall()
    
    sent = db.execute('''
        SELECT * FROM direct_messages 
        WHERE sender_username = ? 
        ORDER BY created_at DESC
    ''', (current_username,)).fetchall()

    users = db.execute('SELECT username FROM users WHERE username != ?', (current_username,)).fetchall()
    return render_template('user/dashboard.html', received=received, sent=sent, users=users, show_motd=show_motd)

@app.route('/user/message/new', methods=['POST'])
@limiter.limit("15 per minute")
@login_required(role='user')
def new_user_message():
    """Handles dispatching message validations and SQLite injection protection."""
    recipient = request.form.get('recipient', '').strip()
    raw_message = request.form.get('message', '').strip()
    sender = session.get('username')
    db = get_db()

    if not recipient or not raw_message:
        return "Error: Missing parameters.", 400

    if recipient == 'system':
        recipient = app.config['ADMIN_USERNAME']

    recipient_check = db.execute('SELECT 1 FROM users WHERE username = ?', (recipient,)).fetchone()
    if not recipient_check:
        return f"Error: Target recipient '{recipient}' does not exist.", 404

    message = sanitize_input(raw_message)

    try:
        db.execute('''
            INSERT INTO direct_messages (sender_username, receiver_username, message)
            VALUES (?, ?, ?)
        ''', (sender, recipient, message))
        db.commit()
        logger.info(f"Direct transmission successfully routed: '{sender}' -> '{recipient}'")
    except Exception as e:
        logger.error(f"Failed to record communication: {e}")
        return "Internal server transmission error.", 500

    return redirect(url_for('user_dashboard'))


# --- 11. AUTH ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
@limiter.exempt
def login():
    """Handles dynamic user and administrator authentications via SQL database."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        db = get_db()
        
        user_record = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if user_record and check_password_hash(user_record['password_hash'], password):
            session['user_id'] = user_record['id']
            session['username'] = user_record['username']
            session['role'] = user_record['role']
            session['show_motd'] = True # Trigger transient dashboard banner
            logger.info(f"Session established successfully for username: '{username}' (Role: '{user_record['role']}')")
            
            if user_record['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('user_dashboard'))
        else:
            logger.warning(f"Failed authentication attempt for username: '{username}'")
            
    return render_template('login.html')

@app.route('/logout')
@limiter.exempt
def logout():
    """Clears the session and redirects to the home console."""
    session.clear()
    logger.info("User session terminated cleanly")
    return redirect(url_for('index'))


# --- 12. HEALTH CHECK ---
@app.route('/health')
@limiter.exempt
def health():
    try:
        db = get_db()
        post_count = db.execute('SELECT COUNT(*) FROM posts').fetchone()[0]
    except Exception as e:
        logger.error(f"Health check failed to query database: {e}")
        post_count = -1
    
    return jsonify({
        "status": "ok",
        "model_loaded": model is not None,
        "db_ok": os.path.exists(app.config['DATABASE']),
        "archive_ok": os.path.exists(app.config['ARCHIVE_DB']),
        "posts_count": post_count
    })


# --- 13. DIRECT RUN (for dev only) ---
if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
