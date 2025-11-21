# Fichier: src/cleeroute/db/app_db.py

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from psycopg_pool import AsyncConnectionPool
from psycopg.connection_async import AsyncConnection
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

# --- Variable Globale pour le Pool de la BDD Applicative ---
# On la déclare comme optionnelle pour une initialisation paresseuse
app_db_pool: Optional[AsyncConnectionPool] = None

@asynccontextmanager
async def app_db_lifespan(app):
    """
    Gestionnaire de cycle de vie pour le pool de connexions de la BDD applicative.
    """
    global app_db_pool
    
    app_db_url = os.getenv("APP_DATABASE_URL")
    if not app_db_url:
        raise ValueError("APP_DATABASE_URL must be set in env.")
        
    print("--- Application Startup: Creating Application DB Connection Pool ---")
    
    # =================================================================
    # CORRECTION : On suit la meilleure pratique
    # =================================================================
    
    # 1. On crée le pool sans l'ouvrir
    app_db_pool = AsyncConnectionPool(
        conninfo=app_db_url,
        open=False # On passe à False pour supprimer le warning
    )

    # 2. On ouvre le pool explicitement. C'est la méthode recommandée.
    await app_db_pool.open()
    
    # =================================================================

    yield # L'application tourne

    print("--- Application Shutdown: Closing Application DB Connection Pool ---")
    if app_db_pool:
        await app_db_pool.close()
        
async def get_app_db_connection() -> AsyncGenerator[AsyncConnection, None]:
    """
    Dépendance FastAPI qui fournit une connexion unique depuis le pool
    pour un seul endpoint, et la libère automatiquement.
    """
    if not app_db_pool:
        raise RuntimeError("Application DB pool is not initialized. Check the FastAPI lifespan.")
        
    async with app_db_pool.connection() as conn:
        yield conn