# MicroPress with Local SmolLM

A secure, lightweight Flask blog engine featuring Markdown support and an offline AI co-writer powered by SmolLM-135M.

## Setup Instructions

1. Clone the repository:
   ```bash
   git clone git@github.com:ajsbsd/flask-ai-smollm.git
   cd flask-ai-smollm

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

    pip install torch transformers accelerate
    ```

2.  Environment Variables

    ```bash
    export FLASK_DEBUG="False"
    export SECRET_KEY="your-random-production-key"
    python app.py
    ```
