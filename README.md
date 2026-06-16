# 📟 ajsbsd.net 
**Version:** v0.7.7  
**Status:** Stable  

Welcome to the **ajsbsd.net** workspace. A lightweight, secure, and AI-enhanced terminal environment built with Flask, SQLite, and local LLM inference.

---

## 🚀 Key Features in v0.7.7
- **Refactored Command Dispatcher:** Replaced monolithic routing with a clean, extensible `COMMAND_MAP` dictionary.
- **Enhanced Security:** Eliminated plaintext password logging, enforced strict `SECRET_KEY` environment variables to prevent session resets, and added a robust XSS sanitization fallback.
- **Local AI:** Integrated `SmolLM2-360M-Instruct` via `llama-cpp-python` for local, private, and snappy AI queries directly in the shell.
- **Ambient Audio Subsystem:** Added a `music` command that cleanly separates backend logic from frontend audio playback via JSON action payloads.

---

## 🛠️ Installation & Setup

### 1. Prerequisites
Ensure you have Python 3.8+ installed. Create and activate a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install flask flask-limiter werkzeug bleach huggingface_hub llama-cpp-python
