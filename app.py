import os
import sqlite3
import json
import secrets
import re
from functools import wraps

try:
    import bleach
    BLEACH_AVAILABLE = True
except ImportError:
    BLEACH_AVAILABLE = False
from flask import Flask, render_template, request, redirect, url_for, session, flash, g, jsonify, current_app
from werkzeug.security import generate_password_hash, check_password_hash

# --- 1. SET UP LOCAL AI (SmolLM-135M-Instruct) ---
print("Initializing system...")
try:
    import torch
    # Set thread limit to 1 to prevent OpenMP multi-threaded deadlocks
    # when processing requests within the multi-threaded Flask server
    torch.set_num_threads(1)
    from transformers import AutoModelForCausalLM, AutoTokenizer
    
    print("Loading Local LLM (SmolLM-135M-Instruct)...")
    CHECKPOINT = os.environ.get("AI_CHECKPOINT", "HuggingFaceTB/SmolLM-135M-Instruct")
    tokenizer = AutoTokenizer.from_pretrained(CHECKPOINT)
    
    # Check if a GPU is available, otherwise default to CPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    
    model = AutoModelForCausalLM.from_pretrained(CHECKPOINT).to(device)
    AI_ENABLED = True
    print("Local LLM Loaded Successfully!")
except ImportError:
    print("--- WARNING ---")
    print("AI dependencies (torch, transformers) not found.")
    print("Run: pip install torch transformers accelerate")
    print("Currently running in Standard Mode (AI Features Disabled).")
    print("----------------")
    AI_ENABLED = False


# --- 2. CONFIGURATION MANAGEMENT & APP CONFIG ---
class Config:
    # Read SECRET_KEY from the environment or use a local development default
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        # Standard static key for local development to maintain session persistence
        SECRET_KEY = 'dev_key_change_me_in_production_892301823091'
        
    DATABASE = os.environ.get('DATABASE_PATH', 'micropress.db')
    AI_CHECKPOINT = os.environ.get('AI_CHECKPOINT', 'HuggingFaceTB/SmolLM-135M-Instruct')
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() in ('true', '1', 't')
    
    # Session security cookie policies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = not DEBUG  # Enforces HTTPS in production
    SESSION_COOKIE_SAMESITE = 'Lax'

# --- 3. FLASK SETUP & DATABASE HELPERS ---
app = Flask(__name__)
app.config.from_object(Config)
import markdown

from markupsafe import Markup  # Add this to your imports at the top of app.py

@app.template_filter('markdown')
def render_markdown(text):
    if not text:
        return ""
    # Convert Markdown to raw HTML
    html_content = markdown.markdown(text, extensions=['extra', 'nl2br'])
    
    if BLEACH_AVAILABLE:
        allowed_tags = [
            'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 
            'strong', 'em', 'u', 's', 'ul', 'ol', 'li', 
            'pre', 'code', 'blockquote', 'a', 'img', 
            'table', 'thead', 'tbody', 'tr', 'th', 'td', 'br', 'hr'
        ]
        allowed_attrs = {
            'a': ['href', 'title', 'target'],
            'img': ['src', 'alt', 'title', 'width', 'height'],
            'code': ['class'],
            'pre': ['class']
        }
        cleaned = bleach.clean(html_content, tags=allowed_tags, attributes=allowed_attrs)
        return Markup(cleaned)  # Explicitly tell Jinja this is safe HTML
    else:
        # Fallback sanitization regex routines if bleach is not installed
        current_app.logger.warning("Bleach is not installed. Markdown HTML output is un-sanitized. Run `pip install bleach` to secure it.")
        cleaned = re.sub(r'(?i)<script.*?>.*?</script.*?>', '', html_content)
        cleaned = re.sub(r'(?i)on\w+\s*=', 'data-xss=', cleaned)
        cleaned = re.sub(r'(?i)javascript:', 'noscript:', cleaned)
        return Markup(cleaned)  # Explicitly tell Jinja this is safe HTML

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        # Set busy timeout to 30.0 seconds to prevent operational errors / lockouts
        db = g._database = sqlite3.connect(
            current_app.config['DATABASE'],
            timeout=30.0
        )
        db.row_factory = sqlite3.Row
        # Enable Write-Ahead Logging (WAL) and enforce Foreign Key Constraints
        try:
            db.execute('PRAGMA journal_mode=WAL;')
            db.execute('PRAGMA foreign_keys=ON;')
        except sqlite3.Error as e:
            current_app.logger.error(f"Error setting database pragmas: {e}")
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        try:
            with db:
                db.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password TEXT NOT NULL
                    )
                ''')
                db.execute('''
                    CREATE TABLE IF NOT EXISTS posts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Setup default admin safely
                cursor = db.execute("SELECT 1 FROM users WHERE username = 'admin'")
                if not cursor.fetchone():
                    hashed_pw = generate_password_hash('adminpass')
                    db.execute("INSERT INTO users (username, password) VALUES (?, ?)", ('admin', hashed_pw))
            print("Database initialized successfully.")
        except sqlite3.Error as e:
            print(f"CRITICAL: Failed to initialize database: {e}")


# --- CSRF PROTECTION MIDDLEWARE ---
@app.before_request
def ensure_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)

@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=session.get('csrf_token'))

@app.before_request
def validate_csrf():
    # Validate CSRF for mutable requests (POST, PUT, DELETE, PATCH)
    if request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
        csrf_token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
        
        if not csrf_token and request.is_json:
            try:
                csrf_token = request.get_json().get('csrf_token')
            except Exception:
                pass
        
        session_token = session.get('csrf_token')
        
        if not session_token or not secrets.compare_digest(str(session_token), str(csrf_token or '')):
            current_app.logger.warning(f"CSRF validation failed for path: {request.path}")
            return "CSRF validation failed. Missing or invalid CSRF token.", 400


# --- 4. AUTH DECORATOR ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash('Please log in to access this page.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# --- 5. ROUTES ---

@app.route('/')
def index():
    db = get_db()
    posts = db.execute('SELECT * FROM posts ORDER BY created_at DESC').fetchall()
    return render_template('index.html', posts=posts)

@app.route('/post/<int:post_id>')
def view_post(post_id):
    db = get_db()
    post = db.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    if post is None:
        return "Post not found", 404
    return render_template('post.html', post=post)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if user and check_password_hash(user['password'], password):
            session['logged_in'] = True
            session['username'] = username
            flash('Successfully logged in.')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials.')
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Successfully logged out.')
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin_dashboard():
    db = get_db()
    posts = db.execute('SELECT * FROM posts ORDER BY created_at DESC').fetchall()
    return render_template('admin.html', posts=posts)

@app.route('/admin/new', methods=['GET', 'POST'])
@login_required
def new_post():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        db = get_db()
        try:
            with db:
                db.execute('INSERT INTO posts (title, content) VALUES (?, ?)', (title, content))
            flash('Post published successfully.')
            return redirect(url_for('admin_dashboard'))
        except sqlite3.Error as e:
            current_app.logger.error(f"Database error during post creation: {e}")
            flash('Error publishing post. Please try again.')
    return render_template('editor.html', post=None, ai_enabled=AI_ENABLED)

@app.route('/admin/edit/<int:post_id>', methods=['GET', 'POST'])
@login_required
def edit_post(post_id):
    db = get_db()
    try:
        post = db.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    except sqlite3.Error as e:
        current_app.logger.error(f"Database fetch error: {e}")
        return "Database query error", 500

    if post is None:
        return "Post not found", 404
        
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        try:
            with db:
                db.execute('UPDATE posts SET title = ?, content = ? WHERE id = ?', (title, content, post_id))
            flash('Post updated successfully.')
            return redirect(url_for('admin_dashboard'))
        except sqlite3.Error as e:
            current_app.logger.error(f"Database error during post update: {e}")
            flash('Error updating post. Please try again.')
        
    return render_template('editor.html', post=post, ai_enabled=AI_ENABLED)

@app.route('/admin/delete/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    db = get_db()
    try:
        with db:
            db.execute('DELETE FROM posts WHERE id = ?', (post_id,))
        flash('Post deleted successfully.')
    except sqlite3.Error as e:
        current_app.logger.error(f"Database error during post deletion: {e}")
        flash('Error deleting post. Please try again.')
    return redirect(url_for('admin_dashboard'))


# --- 6. LOCAL AI API ENDPOINT ---
@app.route('/admin/ai-assist', methods=['POST'])
@login_required
def ai_assist():
    if not AI_ENABLED:
        return jsonify({'success': False, 'error': 'AI features are not enabled on this server.'}), 400
        
    try:
        data = request.get_json()
        prompt = data.get('prompt', '')
        
        if not prompt:
            return jsonify({'success': False, 'error': 'No prompt provided.'}), 400
        
        # Format the chat template for SmolLM-Instruct
        messages = [{"role": "user", "content": prompt}]
        formatted_prompt = tokenizer.apply_chat_template(messages, tokenize=False)
        
        # Tokenize and generate response
        inputs = tokenizer(formatted_prompt, return_tensors="pt").to(device)
        
        with torch.no_grad():
            outputs = model.generate(
                **inputs, 
                max_new_tokens=200,   # Keep length short to generate quickly on CPU
                temperature=0.3,      # Lower temperature for more focused outputs
                top_p=0.9, 
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id
            )
            
        # Decode only the generated response tokens
        input_length = inputs.input_ids.shape[1]
        raw_response = tokenizer.decode(outputs[0][input_length:], skip_special_tokens=True)
        
        return jsonify({'success': True, 'response': raw_response.strip()})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    init_db()
    # Disable auto-reloader to prevent the ~360MB model from being loaded twice in memory,
    # which exhausts system resources and causes process-forking/threading deadlocks.
    app.run(debug=True, use_reloader=False)
