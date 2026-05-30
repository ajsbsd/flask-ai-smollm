# 🗄️ The Archive & The Oracle (v0.6)
### Sovereign Intelligence for the Senior Engineer

> A terminal-based, local-first AI analyst that queries your private archive with verifiable, grounded responses. Zero cloud dependency. Zero deep learning framework bloat. Zero hardcoded credentials.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![SmolLM-360M](https://img.shields.io/badge/Model-SmolLM2--360M--Instruct--GGUF-green.svg)](https://huggingface.co/unsloth/SmolLM2-360M-Instruct-GGUF)

---

Version 0.6 transforms the application's underlying architecture from a single-administrator design to a structured, multi-user **Role-Based Access Control (RBAC)** workspace. This release also decouples the frontend entirely from the core logic, removing all remaining inline templates from `app.py`.

---

## 🚀 What's New in v0.6

- **Sovereign User Dashboard & Communications:** Standard authenticated users now have access to a dedicated portal at `/user`. This includes secure `direct_messages` database logging, enabling users to transmit secure messages directly to the `"system"` (administrator) or other registered users.
- **Decoupled Template Architecture:** Eliminated all inline HTML / Jinja string declarations from the backend. Message tables and user portals now render cleanly using external template lookups from the `/templates` directory.
- **Offline User Administration CLI:** Included `manage_users.py`. This offline terminal utility allows system engineers to securely register, list, or configure administrator and user roles without exposing public registration endpoints to the web.
- **First-Visit MOTD Terminal Banner:** Implemented a console-style Message of the Day (MOTD) banner that renders inside the terminal output strictly on a user's first visit per session.
- **New `motd` and `startx` Terminal Commands:**
  - `motd` – Outputs your custom contact and system information on-demand.
  - `startx` – Triggers client-side redirect animations and routes users dynamically to their correct dashboard interface based on their authenticated role.

---

## 🛡️ Security & Performance Enhancements

- **Multi-Level Authorization:** Refactored the `login_required` decorator to enforce role permissions (`@login_required(role='admin')` or `@login_required(role='user')`) across all dashboard routes and CRUD endpoints.
- **Secure Seeding:** On startup, the database auto-initializes the `users` table and safely hashes and inserts your default `.env` administrator credentials if they are absent.
- **Database Sanitization:** Handled XSS mitigation on user feedback forms and direct communication fields before writing to the database using `bleach`.

---

## 📦 Installation & Getting Started

1. **Set up your environment variables** inside your `.env` file:
   ```ini
   SECRET_KEY="generate-a-secure-32-char-random-string"
   ADMIN_USERNAME="aaron"
   ADMIN_PASSWORD="your_secure_password"
   ```

2. **Run your offline user registration CLI** to add standard accounts:
   ```bash
   python3 manage_users.py add alex securepassword123 user
   ```

3. **Run the optimized launch script:**
   ```bash
   ./run.sh
   ```

   ---

## 🎯 Why This Exists

The AI era is drowning in black-box APIs, massive package dependencies, and unverified outputs. This project is a minimal, bare-metal showcase proving that you can run **verifiable, safe intelligence** locally on standard commodity hardware:

- 🔐 **Sovereign**: Your data never leaves your kernel.
- 🔍 **Verifiable**: Every AI response cites reference snippets from your search context.
- ⚡ **Ultra-Lightweight**: Runs entirely on a single CPU thread via raw `llama-cpp` bindings [1]. No PyTorch, no Hugging Face Transformers library, and no massive system overhead [3, 4].
- 🛡️ **Hardened**: Protects data inputs with HTML sanitization, rate-limits, concurrency locks, and strict access controls.

---

## 🛠️ Key Improvements in v0.5

The `v0.5` release introduces substantial architectural, security, and performance enhancements:

* **Engine Migration:** Shifted to the highly optimized **SmolLM2-360M-Instruct** quantized GGUF model running on native `llama-cpp-python` C-bindings [1, 2].
* **Strict Access Control:** Applied `@login_required` decorator protection to all administrative routes and CRUD endpoints to prevent unauthorized operations [5].
* **Robust Configuration & Environment Support:** Integrated `python-dotenv` to ensure your `.env` variables load reliably during direct launches or Gunicorn worker spawns [6].
* **Credential Security:** Supports storing password hashes (compatible with Werkzeug `check_password_hash`) to avoid storing plain-text keys in your environment configurations [7].
* **Resource and CPU Protection:** 
  * Implemented serializing locks (`with ai_lock:`) to prevent simultaneous multi-threaded queries from causing CPU starvation.
  * Added a per-session 5-second rate-limiting cooldown specifically for the `ai` terminal subcommand to prevent manual or automated request flooding.
* **XSS Defenses:** Includes dynamic HTML sanitization helpers powered by `bleach` to cleanse blog content and contact messages before database insertion [8].

---

## 🚀 Quick Start

### Step 1: Clone and Configure
Clone the repository and set up your virtual environment:

```bash
git clone https://github.com/ajsbsd/flask-ai-smollm.git
cd flask-ai-smollm
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
