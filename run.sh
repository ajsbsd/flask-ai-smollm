source .env
SECRET_KEY=$(openssl rand -hex 32) gunicorn -w 1 --threads 4 --bind 127.0.0.1:3000 app:app
