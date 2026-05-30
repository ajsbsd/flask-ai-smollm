# === STANDARD LIBRARY ===
import logging
import os
import sqlite3
import threading

# === THIRD-PARTY ===
import torch
from flask import Flask, g, jsonify, render_template, request, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# === LOGGING SETUP ===
logger = logging.getLogger("ai.engine")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s:%(name)s:%(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

# --- 1. AI SETUP (SmolLM-135M-Instruct) ---
print("Initializing system...")
CHECKPOINT = "HuggingFaceTB/SmolLM-135M-Instruct"
device = "cuda" if torch.cuda.is_available() else "cpu"
tokenizer = None
model = None

# Track background load state: "unloaded", "loading", "loaded", "failed"
model_status = "unloaded"


def load_ai():
    """Initializes and loads the model into memory."""
    global tokenizer, model, model_status
    if model is None:
        try:
            model_status = "loading"
            logger.info(
                "Initializing SmolLM-135M-Instruct on background thread...")
            from transformers import AutoModelForCausalLM, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(CHECKPOINT)
            model = AutoModelForCausalLM.from_pretrained(CHECKPOINT).to(device)

            model_status = "loaded"
            logger.info(f"AI Model successfully loaded on {device}")
        except Exception as e:
            model_status = "failed"
            logger.error(f"Failed to load AI model: {e}")

# Trigger asynchronous startup load to prevent blocking client requests


def start_model_loading():
    thread = threading.Thread(target=load_ai, daemon=True)
    thread.start()


# --- 2. CONFIG & PATHS ---
# Resolve the absolute base directory of the project to ensure SQLite files
# are always found regardless of the process working directory.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev_key_892301823091')
    DATABASE = os.path.join(BASE_DIR, 'micropress.db')
    ARCHIVE_DB = os.path.join(BASE_DIR, 'imperium_archive.db')
    DEBUG = True


# --- 3. APP INITIALIZATION ---
app = Flask(__name__)
app.config.from_object(Config)

# --- 4. DATABASE HELPER ---


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(
            app.config['DATABASE'], timeout=30.0)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL;')
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


# Initialize database tables on application import (ensures table exists
# for Gunicorn)
with app.app_context():
    db = get_db()
    db.execute(
        'CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY, title TEXT, content TEXT)')
    db.commit()

# --- 5. RATE LIMITING ---
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per hour", "10 per minute"],
    storage_uri="memory://"
)

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
        return jsonify(output=(
            "Available: ls, cat [id], search [term], query [question], "
            "ai [prompt], clear, whoami"
        ))

    elif cmd == 'ls':
        posts = db.execute('SELECT id, title FROM posts').fetchall()
        if not posts:
            return jsonify(output="No documents found.")
        return jsonify(output="\n".join(
            [f"ID: {p['id']} | {p['title']}" for p in posts]))

    elif cmd == 'cat':
        post = db.execute(
            'SELECT content FROM posts WHERE id=?', (args,)).fetchone()
        return jsonify(output=post['content']
                       if post else "Error: Document not found.")

    elif cmd == 'search':
        if not os.path.exists(app.config['ARCHIVE_DB']):
            return jsonify(
                output="Error: imperium_archive.db not found. Build your index first.")

        if not args:
            return jsonify(output="Error: Please specify a search term.")

        try:
            with sqlite3.connect(app.config['ARCHIVE_DB']) as search_db:
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
            return jsonify(output="\n".join(
                [f"PG {r[0]}: {r[1]}" for r in results]))
        except sqlite3.OperationalError as e:
            # Handle SQLite FTS5 query parser exceptions gracefully
            if "fts5" in str(e).lower() or "syntax error" in str(e).lower():
                return jsonify(
                    output="Error: Invalid search syntax. Please try simple keywords.")
            return jsonify(output=f"Archive Error: {e}")
        except sqlite3.Error as e:
            return jsonify(output=f"Archive Error: {e}")

    elif cmd == 'query':
        """Unified automated RAG: searches context, extracts matching segments, and runs AI generation."""
        if model_status != "loaded":
            return jsonify(
                output=f"ORACLE> Initialization in progress (Status: {model_status}). Please wait.")

        if not os.path.exists(app.config['ARCHIVE_DB']):
            return jsonify(
                output="Error: imperium_archive.db not found. Build your index first.")

        if not args:
            return jsonify(output="Error: Please specify a valid query.")

        try:
            with sqlite3.connect(app.config['ARCHIVE_DB']) as search_db:
                results = search_db.execute("""
                    SELECT page_number, snippet(document_pages, 1, '[', ']', '...', 10)
                    FROM document_pages WHERE content MATCH ?
                    ORDER BY bm25(document_pages) LIMIT 3
                """, (args,)).fetchall()
        except sqlite3.OperationalError as e:
            if "fts5" in str(e).lower() or "syntax error" in str(e).lower():
                return jsonify(
                    output="Error: Invalid query syntax. Please try simple keywords.")
            return jsonify(output=f"Archive Query Error: {e}")
        except sqlite3.Error as e:
            return jsonify(output=f"Archive Query Error: {e}")

        if not results:
            return jsonify(
                output="ORACLE> Insufficient local context to safely address that question.")

        # Construct safe system prompt with the retrieved document context
        context_text = "\n".join([f"[PG {r[0]}]: {r[1]}" for r in results])
        system_prompt = (
            f"You are an analyst. Use ONLY the retrieved context to answer the question. "
            f"If the answer is not contained in the context, respond with 'Insufficient context.'\n\n"
            f"RETRIEVED CONTEXT:\n{context_text}\n\n"
            f"USER QUESTION: {args}"
        )

        logger.debug(f"Unified RAG Prompt size: {len(system_prompt)} chars")

        messages = [{"role": "user", "content": system_prompt}]
        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True)
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
        generated = tokenizer.decode(
            outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
        return jsonify(output=f"ORACLE> {generated.strip()}")

    elif cmd == 'ai':
        """General non-RAG prompt execution."""
        if model_status != "loaded":
            return jsonify(
                output=f"ORACLE> Initialization in progress (Status: {model_status}). Please wait.")

        logger.debug(
            f"Generating response for general prompt: {args[:100]}...")

        # Backward-compatible RAG if the manual prefix is detected
        if args.lower().startswith("based on the search") and 'last_search' in session:
            ctx = session['last_search']
            context_text = "\n".join(
                [f"[PG {r['page_number']}]: {r['snippet']}" for r in ctx['results']])
            system_prompt = (
                f"You are an analyst. Use ONLY these retrieved snippets to answer. "
                f"If the answer isn't in the snippets, say 'Insufficient context.'\n\n"
                f"RETRIEVED CONTEXT:\n{context_text}\n\n"
                f"USER QUESTION: {args}"
            )
        else:
            system_prompt = args

        messages = [{"role": "user", "content": system_prompt}]
        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True)
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
        generated = tokenizer.decode(
            outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)

        # Simple heuristic pattern cleaning
        if generated.count("This is because") > 2:
            generated = generated.split("This is because")[0].strip()

        logger.debug(f"Generated {len(generated.split())} tokens")
        return jsonify(output=f"ORACLE> {generated.strip()}")

    elif cmd == 'clear':
        return jsonify(action='clear')

    elif cmd == 'whoami':
        return jsonify(output="aaron@ajsbsd.net (Senior Systems Engineer)")

    return jsonify(output=f"sh: command not found: {cmd}")

# --- 8. HEALTH CHECK ---


@app.route('/health')
def health():
    return jsonify({
        "status": "ok",
        "model_loaded": model is not None,
        "model_status": model_status,
        "db_ok": os.path.exists(app.config['DATABASE']),
        "archive_ok": os.path.exists(app.config['ARCHIVE_DB'])
    })


# Start the model loader inside an asynchronous daemon thread immediately
# on import
start_model_loading()

# --- 9. LOCAL DEV EXECUTION ENTRYPOINT ---
if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)
