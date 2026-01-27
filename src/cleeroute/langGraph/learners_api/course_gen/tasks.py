from src.cleeroute.db.checkpointer import db_pool, PickleSerde
from src.cleeroute.langGraph.learners_api.course_gen.graph_gen import create_syllabus_generation_graph
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from psycopg_pool import AsyncConnectionPool 
import asyncio
import psycopg
import logging
from src.cleeroute.tasks import celery_app

import os
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)
DB_URL = os.getenv("DATABASE_URL") 

@celery_app.task(bind=True)
def generate_syllabus_task(self, thread_id: str, youtube_api_key: str):
    try:
        result = asyncio.run(_generate_syllabus_async(thread_id, youtube_api_key))
        return result
    except Exception as e:
        logger.error(f"Erreur dans la tâche generate_syllabus_task: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=15, max_retries=3)

async def _generate_syllabus_async(thread_id: str, youtube_api_key: str):
    
    conn_kwargs = {"autocommit": True}

    if "azure.com" in DB_URL or "52." in DB_URL:
         conn_kwargs["sslmode"] = "require"

    async with AsyncConnectionPool(
        conninfo=DB_URL,
        min_size=1,
        max_size=10,
        timeout=30.0, 
        kwargs=conn_kwargs 
    ) as temp_pool:
        
        checkpointer = AsyncPostgresSaver(conn=temp_pool, serde=PickleSerde)
        
        # Setup résilient
        try:
            await checkpointer.setup()
        except (psycopg.errors.DuplicateColumn, psycopg.errors.DuplicateTable, psycopg.errors.UniqueViolation):
            pass
        except Exception as e:
            logger.warning(f"Note setup DB: {e}")

        # Lancement LangGraph
        syllabus_graph = create_syllabus_generation_graph(checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        
        os.environ['YOUTUBE_API_KEY'] = youtube_api_key if youtube_api_key else os.getenv("YOUTUBE_API_KEY")

        final_state = await syllabus_graph.ainvoke({}, config)

        return {"status": "completed", "thread_id": thread_id}