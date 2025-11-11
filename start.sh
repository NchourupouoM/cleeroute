#!/bin/sh

# Ce script lance le worker Celery en arrière-plan et le serveur Uvicorn au premier plan.
# Le 'set -e' garantit que si une commande échoue, le script entier s'arrête,
# ce qui est une bonne pratique pour les scripts de démarrage de conteneurs.
set -e

# Lancer le worker Celery en arrière-plan.
# - 'celery': La commande principale.
# - '-A src.cleeroute.tasks': Pointe vers votre application Celery. 'src.cleeroute.tasks' doit correspondre
#   au chemin d'importation de votre objet `celery_app`.
# - 'worker': Spécifie que ce processus est un worker.
# - '--loglevel=info': Définit le niveau de journalisation pour le worker.
# - '&': L'esperluette est cruciale. Elle envoie ce processus en arrière-plan (background),
#   permettant au script de continuer à exécuter la commande suivante.
echo "--- Starting Celery Worker in the background ---"
celery -A src.cleeroute.tasks worker --loglevel=info &

# Lancer le serveur web Uvicorn au premier plan.
# Ce processus doit rester au premier plan, car c'est le processus principal
# du conteneur. Si ce processus se termine, le conteneur s'arrêtera.
echo "--- Starting Uvicorn Server in the foreground ---"
uvicorn src.cleeroute.main:app --host 0.0.0.0 --port 8000