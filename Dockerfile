# FROM python:3.12-slim
# WORKDIR /app
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt
# COPY . .
# EXPOSE 8000
# CMD ["uvicorn", "src.cleeroute.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Utilisez une image Python légère
FROM python:3.12-slim

WORKDIR /app

# Installez les dépendances système nécessaires
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copiez les fichiers nécessaires pour l'installation
COPY requirements.txt .

# Installez les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiez le reste de l'application
COPY . .

# Créez un script d'entrée pour démarrer FastAPI et Celery
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Exposez le port pour FastAPI
EXPOSE 8000

# Commande pour démarrer l'application
CMD ["/entrypoint.sh"]
