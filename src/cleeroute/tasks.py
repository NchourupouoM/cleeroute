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


celery_app.conf.update(
    broker_connection_retry_on_startup=True,

    # Azure Redis recommended configs
    broker_transport_options={
        "visibility_timeout": 3600,   # 1h
        "ssl": {"ssl_cert_reqs": None}, # Azure uses public certs
    },

    result_backend_transport_options={
        "retry_policy": {
            "timeout": 5.0
        }
    },

    task_time_limit=60 * 5,       # Hard timeout 5 min
    task_soft_time_limit=60 * 4,  # Soft timeout 4 min
    worker_concurrency=4,
    worker_prefetch_multiplier=1, # Best for API tasks

    task_default_retry_delay=10,
    task_default_rate_limit="20/m",
    task_acks_late=True,
    worker_max_tasks_per_child=100,
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