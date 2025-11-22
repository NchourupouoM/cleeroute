# FROM python:3.12-slim
# WORKDIR /app
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt
# COPY . .
# EXPOSE 8000
# CMD ["uvicorn", "src.cleeroute.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.12-slim
WORKDIR /app

# Installe les dépendances système pour Celery et Redis
RUN apt-get update && apt-get install -y \
    redis-tools \
    gcc \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Installe supervisord pour gérer plusieurs processus
RUN apt-get update && apt-get install -y supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 8000

# Lance supervisord qui va gérer FastAPI et Celery
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
