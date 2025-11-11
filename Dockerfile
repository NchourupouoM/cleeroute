# Dockerfile
FROM python:3.11-slim

# Installer supervisord
RUN apt-get update && apt-get install -y supervisor

WORKDIR /app

# Copier les fichiers de configuration de supervisord
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le reste de l'application
COPY . .

# Exposer le port de FastAPI
EXPOSE 8000

# Lancer supervisord
CMD ["/usr/bin/supervisord"]
