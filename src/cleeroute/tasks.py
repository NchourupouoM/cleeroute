import os
from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown
from dotenv import load_dotenv
from src.cleeroute.db.checkpointer import db_pool
import asyncio
import ssl
# Charger les variables d'environnement pour le worker
load_dotenv()

REDIS_URL = os.getenv("CELERY_BROKER_URL")

# 1. Configuration de l'application Celery
celery_app = Celery(
    'cleeroute_tasks', # Nom de l'application
    broker=REDIS_URL,
    backend=REDIS_URL,
)

# Configuration spécifique pour Azure Redis (SSL)
if REDIS_URL and REDIS_URL.startswith("rediss://"):
    ssl_conf = {
        'ssl_cert_reqs': ssl.CERT_NONE  # Nécessaire pour Azure Redis parfois
    }
    celery_app.conf.broker_use_ssl = ssl_conf
    celery_app.conf.redis_backend_use_ssl = ssl_conf




@worker_process_init.connect
def init_worker(**kwargs):
    print("--- [CELERY WORKER LIFECYCLE] Worker process starting. Opening DB pool. ---")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db_pool.open())

@worker_process_shutdown.connect
def shutdown_worker(**kwargs):
    print("--- [CELERY WORKER LIFECYCLE] Worker process shutting down. Closing DB pool. ---")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(db_pool.close())


# Configuration pour que Celery trouve automatiquement les tâches
celery_app.autodiscover_tasks(
    packages=[
        "src.cleeroute.langGraph.learners_api.course_gen"
    ]
)