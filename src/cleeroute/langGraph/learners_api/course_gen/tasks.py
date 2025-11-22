from celery import Celery
from src.cleeroute.db.checkpointer import get_checkpointer, db_pool, PickleSerde
from src.cleeroute.langGraph.learners_api.course_gen.graph import create_syllabus_generation_graph
from langgraph.pregel import Pregel

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
import asyncio
import logging
from google.api_core.exceptions import GoogleAPICallError, RetryError


import os
from dotenv import load_dotenv
load_dotenv()

app = Celery('tasks', broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"))
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_time_limit=3600,
    task_soft_time_limit=3000,
    broker_transport_options={
        'socket_timeout': 60,
        'socket_connect_timeout': 60,
        'visibility_timeout': 3600, 
    }
)

logger = logging.getLogger(__name__)


@app.task(bind=True)
def generate_syllabus_task(self, thread_id: str, youtube_api_key: str):
    try:
        result = asyncio.run(_generate_syllabus_async(thread_id, youtube_api_key))
        return result
    except Exception as e:
        logger.error(f"Erreur dans la tâche generate_syllabus_task: {e}", exc_info=True)
        raise self.retry(exc=e)

async def _generate_syllabus_async(thread_id: str, youtube_api_key: str):
    try:
        if not db_pool._opened:
            await db_pool.open()

        checkpointer = AsyncPostgresSaver(conn=db_pool, serde=PickleSerde)
        syllabus_graph = create_syllabus_generation_graph(checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        os.environ['YOUTUBE_API_KEY'] = youtube_api_key if youtube_api_key else os.getenv("YOUTUBE_API_KEY")

        final_state = await syllabus_graph.ainvoke({}, config)

        if final_state:
            await syllabus_graph.aupdate_state(config, final_state)

        # Attendre que toutes les tâches asynchrones soient terminées
        pending = asyncio.all_tasks()
        for task in pending:
            if task is not asyncio.current_task():
                await task

        return {"status": "completed", "thread_id": thread_id}
    except Exception as e:
        logger.error(f"Erreur dans _generate_syllabus_async: {e}", exc_info=True)
        raise
