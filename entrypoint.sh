#!/bin/sh

# Démarrez FastAPI en arrière-plan
uvicorn src.cleeroute.main:app --host 0.0.0.0 --port 8000 &

# Attendez que FastAPI soit prêt
sleep 10

# Démarrez Celery avec un utilisateur non-root
celery -A worker worker --loglevel=info --uid=$(id -u)
