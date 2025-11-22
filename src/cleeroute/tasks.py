import os
import ssl
import asyncio
from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown
from dotenv import load_dotenv
from src.cleeroute.db.checkpointer import db_pool

# Charger les variables
load_dotenv()

REDIS_URL = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL"))

# --- 1. Création de l'application UNIQUE ---
celery_app = Celery(
    'cleeroute_tasks',
    broker=REDIS_URL,
    backend=REDIS_URL,
)

# --- 2. Configuration Centralisée (SSL + Timeouts) ---
# On prépare les options de transport (Timeouts)
transport_opts = {
    'socket_timeout': 60,
    'socket_connect_timeout': 60,
    'socket_keepalive': True,   
    'health_check_interval': 10,
    'visibility_timeout': 3600,
}

# On prépare la config SSL
ssl_conf = None
if REDIS_URL and REDIS_URL.startswith("rediss://"):
    ssl_conf = {
        'ssl_cert_reqs': ssl.CERT_NONE
    }

# On applique TOUT à la configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_pool='solo',                 # Mode Solo pour stabilité mémoire/CPU
    broker_transport_options= transport_opts,
    broker_use_ssl=ssl_conf,            # Applique SSL au Broker
    redis_backend_use_ssl=ssl_conf,     # Applique SSL au Backend (résultats)
    broker_connection_retry_on_startup=True, # Recommandé pour Celery 5+
)

# --- 3. Gestion du cycle de vie (DB Pool) ---  
@worker_process_init.connect
def init_worker(**kwargs):
    print("--- [CELERY WORKER LIFECYCLE] Worker process starting. Opening DB pool. ---")
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(db_pool.open())

@worker_process_shutdown.connect
def shutdown_worker(**kwargs):
    print("--- [CELERY WORKER LIFECYCLE] Worker process shutting down. Closing DB pool. ---")
    try:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(db_pool.close())
    except Exception as e:
        print(f"Error closing pool: {e}")

# Configuration pour trouver les tâches
celery_app.autodiscover_tasks([
    "src.cleeroute.langGraph.learners_api.course_gen"
])