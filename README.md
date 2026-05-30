# 🗄️ The Archive & The Oracle (v0.6.9)
### Sovereign Intelligence for the Senior Engineer

> A terminal-based, local-first AI analyst that queries your private archive with verifiable, grounded responses. Zero cloud dependency. Zero deep learning framework bloat. Zero hardcoded credentials.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![SmolLM-360M](https://img.shields.io/badge/Model-SmolLM2--360M--Instruct--GGUF-green.svg)](https://huggingface.co/unsloth/SmolLM2-360M-Instruct-GGUF)

---

Version 0.6.9 is a hardening and stability release that resolves all known runtime errors, closes missing route gaps, and tightens session and database security across the stack.

---

## 🚀 What's New in v0.6.9

- **Missing Routes Resolved:** Added `edit_post`, `delete_post`, `new_post`, and `user_dashboard` — all previously referenced in templates but never defined, causing `BuildError` crashes on `/admin` and post-login redirects.
- **DB Init on Gunicorn Startup:** `init_db()` now runs at module load time inside `app.app_context()`, so gunicorn workers correctly initialize the schema on boot without requiring a `__main__` entry point.
- **Stable `SECRET_KEY`:** Previously regenerated on every restart via `secrets.token_hex(32)`, invalidating all active sessions. Now requires a fixed `SECRET_KEY` env var and raises a hard `RuntimeError` at startup if absent.
- **Server-Side AI Cooldown:** The `ai` command cooldown was previously stored in the client session cookie, allowing bypass by clearing cookies. Now enforced server-side in a thread-safe dict keyed by remote IP.
- **`cat` Input Validation:** Now validates that the argument is a digit before casting to `int`, preventing silent type coercion errors on non-numeric input.
- **`whoami` Fixed:** Previously always returned the admin email regardless of who was logged in. Now returns the actual session username and role.
- **Merge Conflicts Cleared:** Resolved committed Jinja `<<<<<<< HEAD` conflict markers in `base.html`, `login.html`, and `new_post.html` that were causing `TemplateAssertionError: block 'title' defined twice`.
- **`manage_users.py` Fixed:** `DATABASE` path was a raw unrendered Jinja string (`{{ app_name }}.db`). Now hardcoded to `wstudio.db`. Added `ensure_table()` so the CLI works standalone without requiring the Flask server to have run first. Added `delete` command.
- **`dashboard.html` Created:** Missing template for the standard user dashboard, referenced by `user_dashboard` route.
- **`new_post.html` Fixed:** Orphaned JavaScript line dangling outside `{% endblock %}` was causing `TemplateSyntaxError`. JS is now properly contained in a `<script>` block with the Oracle AI assistant fully wired up.
- **`DEBUG` Flag:** Was hardcoded `True`. Now reads from `DEBUG` env var, defaulting to `false`.

---

## 🚀 What's New in v0.6

- **Sovereign User Dashboard & Communications:** Standard authenticated users now have access to a dedicated portal at `/dashboard`. Includes secure `direct_messages` database logging for user-to-system and user-to-user messaging.
- **Decoupled Template Architecture:** Eliminated all inline HTML / Jinja string declarations from the backend. All views render from external templates in `/templates`.
- **Offline User Administration CLI:** `manage_users.py` allows secure offline registration, listing, and deletion of users without exposing public registration endpoints.
- **First-Visit MOTD Terminal Banner:** Console-style Message of the Day renders on a user's first visit per session.
- **New `motd` and `startx` Terminal Commands:**
  - `motd` – Outputs system and contact information on demand.
  - `startx` – Routes authenticated users to their correct dashboard based on role.

---

## 🛡️ Security & Performance

- **Multi-Level Authorization:** `login_required` decorator enforces role permissions (`admin` or `user`) across all dashboard routes and CRUD endpoints.
- **Secure Seeding:** On startup, auto-initializes the `users` table and inserts hashed admin credentials from `.env` if absent.
- **XSS Mitigation:** `bleach` sanitization on all user-submitted content before DB writes.
- **Rate Limiting:** `flask-limiter` enforces 30 requests/minute on `/api/exec`. AI command has an additional server-side 5-second per-IP cooldown.
- **Concurrency Safety:** Oracle model access serialized with a threading lock to prevent CPU starvation under concurrent requests.

---

## 📦 Installation

1. **Clone and set up environment:**
   ```bash
   git clone https://github.com/ajsbsd/flask-ai-smollm.git
   cd flask-ai-smollm
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure `.env`:**
   ```ini
   SECRET_KEY="your-secure-32-char-random-string"
   ADMIN_USERNAME="aaron"
   ADMIN_PASSWORD="your_secure_password"
   DEBUG="false"
   ```
   Generate a secret key:
   ```bash
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```

3. **Register additional users offline:**
   ```bash
   python3 manage_users.py add alex securepassword123 user
   python3 manage_users.py list
   python3 manage_users.py delete alex
   ```

4. **Launch:**
   ```bash
   ./run.sh
   ```

---

## 🎯 Why This Exists

The AI era is drowning in black-box APIs, massive package dependencies, and unverified outputs. This project is a minimal, bare-metal showcase proving that you can run **verifiable, sovereign intelligence** locally on standard commodity hardware:

- 🔐 **Sovereign**: Your data never leaves your machine.
- 🔍 **Verifiable**: Every AI response cites reference snippets from your local search context.
- ⚡ **Ultra-Lightweight**: Runs on a single CPU via raw `llama-cpp` bindings. No PyTorch, no Transformers, no cloud overhead.
- 🛡️ **Hardened**: Rate limiting, concurrency locks, input sanitization, role-based access control, and stable session security.

---

## 🤖 AI-Assisted Development

The v0.6.9 bug fixes were diagnosed and patched in a single session using **Claude Sonnet 4.6** (Anthropic, free tier) via [claude.ai](https://claude.ai).

Issues resolved across the session:

- 7 runtime bugs (missing routes, broken DB init, unstable secret key, bad input validation, wrong `whoami` output, client-side cooldown bypass, hardcoded debug flag)
- 3 Jinja template merge conflicts committed to the repo (`base.html`, `login.html`, `new_post.html`)
- 2 missing route groups (`edit_post`/`delete_post`, `user_dashboard`)
- 1 broken CLI tool (`manage_users.py` with unrendered Jinja variable as DB path)
- 1 missing template (`dashboard.html`)

All suggested changes were reviewed, tested, and applied manually by the developer. No code was merged without a passing server log.

> Proof that a free-tier AI session on commodity hardware can do real triage work — consistent with the sovereign, minimal-dependency philosophy of this project.
