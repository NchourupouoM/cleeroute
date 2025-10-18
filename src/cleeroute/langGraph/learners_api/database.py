# In app/database.py
import os
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from dotenv import load_dotenv

load_dotenv()

# --- Database Singleton Setup ---
db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise ValueError("DATABASE_URL must be set in env")

# This code runs only ONCE when the module is first imported.
# db_pool will be a singleton instance for the entire application lifecycle.
print("--- Creating Database Connection Pool (Singleton) ---")
db_pool = AsyncConnectionPool(conninfo=db_url, max_size=20, open=True, timeout=10, max_idle=180, check=AsyncConnectionPool.check_connection)

# The checkpointer is also created once, using the singleton pool.
checkpointer = AsyncPostgresSaver(db_pool)

# We can also add a function to handle graceful shutdown if needed,
# though we won't have a direct hook from FastAPI without lifespan.
# --- Fonctions de gestion du pool ---

# async def open_db_pool():
#     print("--- Opening Database Connection Pool ---")
#     await db_pool.open()

async def close_db_pool():
    print("--- Closing Database Connection Pool ---")
    await db_pool.close()