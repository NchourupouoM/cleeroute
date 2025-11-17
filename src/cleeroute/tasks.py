import os
from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown
from dotenv import load_dotenv
from src.cleeroute.db.checkpointer import db_pool
import asyncio

# Charger les variables d'environnement pour le worker
load_dotenv()

# 1. Configuration de l'application Celery
celery_app = Celery(
    'cleeroute_tasks', # Nom de l'application
    broker=os.getenv('CELERY_BROKER_URL'),
    backend=os.getenv('CELERY_RESULT_BACKEND'),
)

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