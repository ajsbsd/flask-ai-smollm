# === STANDARD LIBRARY ===
import os
import sqlite3
import json
import secrets
import re
import logging

# === THIRD-PARTY ===
import torch
import markdown
from flask import Flask, render_template, request, session, g, jsonify, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from markupsafe import Markup

# === OPTIONAL DEPENDENCIES ===
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

# --- 1. AI SETUP (SmolLM-135M-Instruct) ---
print("Initializing system...")
CHECKPOINT = "HuggingFaceTB/SmolLM-135M-Instruct"
device = "cuda" if torch.cuda.is_available() else "cpu"
tokenizer = None
model = None

def load_ai():
    global tokenizer, model
    if model is None:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(CHECKPOINT)
        model = AutoModelForCausalLM.from_pretrained(CHECKPOINT).to(device)
        print(f"AI Model loaded on {device}")

# --- 2. CONFIG ---
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_key_892301823091')
    DATABASE = 'micropress.db'
    ARCHIVE_DB = 'imperium_archive.db'
    DEBUG = True

# --- 3. APP INITIALIZATION ---
app = Flask(__name__)
app.config.from_object(Config)

# --- 4. RATE LIMITING ---
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per hour", "10 per minute"],
    storage_uri="memory://"
)

# --- 5. DATABASE HELPER ---
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

# --- 6. TERMINAL API ---
@app.route('/')
def terminal_index():
    return render_template('terminal.html')

@app.route('/api/exec', methods=['POST'])
@limiter.limit("30 per minute")
def execute():
    """Main terminal command dispatcher."""
    data = request.get_json()
    raw_input = data.get('command', '').strip()
    if not raw_input:
        return jsonify(output="")

    parts = raw_input.split(' ')
    cmd = parts[0].lower()
    args = " ".join(parts[1:])
    db = get_db()

    if cmd == 'help':
        return jsonify(output="Available: ls, cat [id], search [term], ai [prompt], clear, whoami")

    elif cmd == 'ls':
        posts = db.execute('SELECT id, title FROM posts').fetchall()
        if not posts:
            return jsonify(output="No documents found.")
        return jsonify(output="\n".join([f"ID: {p['id']} | {p['title']}" for p in posts]))

    elif cmd == 'cat':
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
        logger.debug(f"Generating response for prompt: {args[:100]}...")
        load_ai()
        if args.lower().startswith("based on the search") and 'last_search' in session:
            ctx = session['last_search']
            context_text = "\n".join([f"[PG {r['page_number']}]: {r['snippet']}" for r in ctx['results']])
            system_prompt = f"You are an analyst. Use ONLY these retrieved snippets to answer. If the answer isn't in the snippets, say 'Insufficient context.'\n\nRETRIEVED CONTEXT:\n{context_text}\n\nUSER QUESTION: {args}"
        else:
            system_prompt = args
        messages = [{"role": "user", "content": system_prompt}]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=150,
                do_sample=True,
                temperature=0.3,
                pad_token_id=tokenizer.eos_token_id,
                repetition_penalty=1.2,
                no_repeat_ngram_size=3
            )
        generated = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        if generated.count("This is because") > 2:
            generated = generated.split("This is because")[0].strip()
        logger.debug(f"Generated {len(generated.split())} tokens")
        return jsonify(output=f"ORACLE> {generated.strip()}")

    elif cmd == 'clear':
        return jsonify(action='clear')

    elif cmd == 'whoami':
        return jsonify(output="aaron@ajsbsd.net (Senior Systems Engineer)")

    return jsonify(output=f"sh: command not found: {cmd}")

# --- 7. HEALTH CHECK ---
@app.route('/health')
def health():
    return jsonify({
        "status": "ok",
        "model_loaded": model is not None,
        "db_ok": os.path.exists(app.config['DATABASE']),
        "archive_ok": os.path.exists(app.config['ARCHIVE_DB'])
    })

# --- 8. INIT ---
if __name__ == '__main__':
    with app.app_context():
        db = get_db()
        db.execute('CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY, title TEXT, content TEXT)')
        db.commit()
    app.run(debug=True, use_reloader=False)
