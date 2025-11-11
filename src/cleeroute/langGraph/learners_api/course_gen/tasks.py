# Fichier: src/cleeroute/langGraph/learners_api/course_gen/tasks.py

import os
import asyncio
from src.cleeroute.tasks import celery_app
from .graph import create_syllabus_generation_graph
from .state import GraphState
from src.cleeroute.db.checkpointer import db_pool

@celery_app.task(name="generate_syllabus_task")
def generate_syllabus_task(thread_id: str, initial_state_dict: dict, youtube_api_key: str):
    print(f"--- [CELERY WORKER] Received task for thread: {thread_id} ---")
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(_run_async_graph(thread_id, initial_state_dict, youtube_api_key))

async def _run_async_graph(thread_id: str, initial_state_dict: dict, youtube_api_key: str):
        
            # **Validation de l'état initial**
        for key, value in initial_state_dict.items():
            if not isinstance(value, (str, int, float, bool, list, dict, type(None))):
                print(f"--- WARNING: Invalid value type for key '{key}': {type(value)}. Converting to str. ---")
                initial_state_dict[key] = str(value)

        async with db_pool.connection():
            try:
                os.environ['YOUTUBE_API_KEY'] = youtube_api_key
                syllabus_graph = create_syllabus_generation_graph()
                config = {"configurable": {"thread_id": thread_id}}
                final_state = await syllabus_graph.ainvoke(initial_state_dict, config)
                if final_state:
                    await syllabus_graph.aupdate_state(config, final_state)
                return {"status": "SUCCESS", "thread_id": thread_id}
            except Exception as e:
                print(f"--- [CELERY WORKER] FATAL ERROR: {e}")
                raise