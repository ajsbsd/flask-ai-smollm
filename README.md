# 🗄️ The Archive & The Oracle  
### Sovereign Intelligence for the Senior Engineer

> A terminal-based, local-first AI analyst that queries your private archive with verifiable, grounded responses. Zero cloud dependency. Zero hallucination hand-waving.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://python.org)
[![SmolLM-135M](https://img.shields.io/badge/Model-SmolLM--135M--Instruct-green.svg)](https://huggingface.co/HuggingFaceTB/SmolLM-135M-Instruct)

---

## 🎯 Why This Exists

The AI era is drowning in black-box APIs and unverified outputs. This project proves you can build **verifiable intelligence** that runs entirely on your infrastructure:

- 🔐 **Sovereign**: Your data never leaves your kernel
- 🔍 **Verifiable**: Every AI response cites `[REF: PG #]` from your archive
- ⚡ **Portable**: Runs on 2 vCPU / 4GB RAM; scales to GPU clusters
- 🧭 **Transparent**: `--log-level debug` shows exact prompts + token counts

---

## 🚀 Quick Start

### Option A: Local Dev
```bash
git clone https://github.com/aaron/flask-ai-smollm.git
cd flask-ai-smollm
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
./run.sh
# → Open http://localhost:3000
