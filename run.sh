#!/bin/sh

# 3. Generate and export the secret key
export SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
echo "SECRET_KEY generated."

# 4. Start Gunicorn
#gunicorn -w 1 --threads 4 --bind 127.0.0.1:3000 app:app
gunicorn -w 1 --threads 4 --bind 0.0.0.0:3000 app:app
