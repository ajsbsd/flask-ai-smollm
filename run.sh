source .env
export SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
echo $SECRET_KEY
gunicorn -w 1 --threads 4 --bind 127.0.0.1:3000 app:app
