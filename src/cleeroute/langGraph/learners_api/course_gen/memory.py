# course_generator/memory.py
import os
from dotenv import load_dotenv
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

load_dotenv()

class PostgresCheckpointer:
    def __init__(self):
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise ValueError("DATABASE_URL environment variable must be set.")
        self.checkpointer = AsyncPostgresSaver.from_conn_string(db_url)

    async def ainit(self):
        """Initialise le checkpointer de manière asynchrone."""
        await self.checkpointer.ainit()

    def get_next_version(self, *args, **kwargs):
        """Renvoie la méthode get_next_version du checkpointer."""
        return self.checkpointer.get_next_version(*args, **kwargs)

async def get_checkpointer():
    """Initialise et retourne une instance de PostgresCheckpointer."""
    checkpointer = PostgresCheckpointer()
    await checkpointer.ainit()
    return checkpointer
