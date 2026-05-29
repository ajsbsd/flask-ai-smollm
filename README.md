# 🗄️ The Archive & The Oracle (v0.5)
### Sovereign Intelligence for the Senior Engineer

> A terminal-based, local-first AI analyst that queries your private archive with verifiable, grounded responses. Zero cloud dependency. Zero deep learning framework bloat. Zero hardcoded credentials.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![SmolLM-360M](https://img.shields.io/badge/Model-SmolLM2--360M--Instruct--GGUF-green.svg)](https://huggingface.co/unsloth/SmolLM2-360M-Instruct-GGUF)

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
