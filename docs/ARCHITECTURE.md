🔐 Security Notes
Do not use the default SECRET_KEY in production
Bind to 127.0.0.1 + reverse proxy (Caddy/Nginx) for HTTPS
Rate limiting is enabled by default on /api/exec
Model weights cached in ~/.cache/huggingface/ — ensure disk encryption for sensitive deployments
🤝 Contributing
This is a reference architecture for sovereign AI. If you're building something similar:
Fork the repo
Create a feature branch (git checkout -b feat/your-idea)
Test thoroughly (python -m py_compile app.py)
Open a PR with a clear description
🪙 Support Sovereign Infrastructure
This project is maintained independently. If it saves you time or advances your work:
🌐 Blog: ongoingstoriesofmysoul.org
💬 Contact: hello@ajsbsd.net
🪙 Crypto Donations: TRON (TRX) — [Contact for address]
📜 License
MIT License — see LICENSE for details.
Build boldly. Verify everything.


docker-compose up -d
# → Open http://localhost:3000

Terminal Data Flow

$ help
Available: ls, cat [id], search [term], ai [prompt], clear, whoami

$ search "Europe"
PG 372: ...In this War, the Liberation Front speaks for [Europe]...
PG 371: ...This is democratic [Europe], liberal [Europe]...

$ ai "Based on the search results, what is the main insight?"
ORACLE> The retrieved snippets frame "Europe" as a contested political concept... [REF: PG 371, 372] [CONTEXT: grounded]

$ grep -r "Liberation Front" ~/archive/  # Verify the claim

# Architecture

[User Terminal] 
       ↓ (HTTP/JSON)
[Flask API + Rate Limiter]
       ↓
[BM25 Search (SQLite FTS5)] ←→ [imperium_archive.db]
       ↓
[Session Context] → [SmolLM-135M (CPU)]
       ↓
[Grounded Response + REF Tags]

# Configuration

Env Var	Default	Purpose
SECRET_KEY	dev_key_...	Flask session signing
DATABASE	micropress.db	Blog/posts SQLite DB
ARCHIVE_DB	imperium_archive.db	BM25 research index
LOG_LEVEL	debug	Gunicorn logging verbosity


🔐 Security Notes
Do not use the default SECRET_KEY in production
Bind to 127.0.0.1 + reverse proxy (Caddy/Nginx) for HTTPS
Rate limiting is enabled by default on /api/exec
Model weights cached in ~/.cache/huggingface/ — ensure disk encryption for sensitive deployments
