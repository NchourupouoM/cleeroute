FROM python:3.11-slim

# Créer un utilisateur non-root
RUN useradd -m celeryuser

# Installer supervisord et créer les dossiers de logs
RUN apt-get update && apt-get install -y supervisor && \
    mkdir -p /var/log && \
    chown -R celeryuser:celeryuser /var/log

WORKDIR /app

# Copier les fichiers de configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY celeryconfig.py .

# Installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le reste de l'application
COPY . .

# Changer les permissions pour l'utilisateur non-root
RUN chown -R celeryuser:celeryuser /app

# Exposer le port de FastAPI
EXPOSE 8000

# Lancer supervisord en tant que celeryuser
USER celeryuser
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]