import asyncio
import os
import logging
from psycopg_pool import AsyncConnectionPool
from celery import shared_task
from src.cleeroute.langGraph.learners_api.chats.services.ytbe_transcripts import TranscriptService

logger = logging.getLogger(__name__)
DB_URL = os.getenv("APP_DATABASE_URL")

@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def ingest_transcript_by_id_task(self, subsection_id: str):
    """
    Tâche optimisée : Ingère le transcript d'une sous-section via son UUID.
    Appelée par l'endpoint de 'Préchauffage'.
    """
    try:
        return asyncio.run(_ingest_transcript_by_id_async(subsection_id))
    except Exception as e:
        logger.error(f"Erreur ingestion transcript (ID: {subsection_id}): {e}")
        raise self.retry(exc=e)

async def _ingest_transcript_by_id_async(subsection_id: str):
    transcript_service = TranscriptService()

    # Config SSL si nécessaire
    conn_kwargs = {"autocommit": True}
    if "azure.com" in DB_URL or "52." in DB_URL:
         conn_kwargs["sslmode"] = "require"

    # Pool éphémère pour le worker
    async with AsyncConnectionPool(
        conninfo=DB_URL,
        min_size=1, max_size=1, timeout=30.0, kwargs=conn_kwargs 
    ) as pool:
        async with pool.connection() as conn:
            # On appelle directement le service qui gère la logique "If needed"
            # (Vérifie si déjà fait, sinon vectorise et résume)
            await transcript_service.ingest_transcript_if_needed(conn, subsection_id)
            
            logger.info(f"--- [Celery] Ingestion finished for subsection {subsection_id} ---")
            return "processed"