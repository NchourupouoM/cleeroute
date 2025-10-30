# In app/database.py

import os
import pickle
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from dotenv import load_dotenv
from typing import AsyncGenerator
from psycopg.connection_async import AsyncConnection
from contextlib import asynccontextmanager

load_dotenv()

# =========================================================================
# 1. CLASSE DE SÉRIALISATION (Serde)
# Utilise 'pickle' pour une sérialisation binaire robuste de n'importe quel
# objet Python, y compris vos modèles Pydantic.
# =========================================================================

class PickleSerde:
    """
    Un objet sérialiseur/désérialiseur qui utilise le protocole 'pickle' de Python.
    """
    @staticmethod
    def dumps(obj: any) -> bytes:
        """Sérialise un objet en une chaîne binaire."""
        return pickle.dumps(obj)

    @staticmethod
    def loads(s: bytes) -> any:
        """Désérialise une chaîne binaire en un objet Python."""
        return pickle.loads(s)


# =========================================================================
# 2. CONFIGURATION DE LA BASE DE DONNÉES ET DU POOL DE CONNEXIONS
# Ce pool est le seul moyen d'accéder à la base de données pour toute l'application.
# =========================================================================

db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise ValueError("DATABASE_URL must be set in env")

keepalive_args = "keepalives=1&keepalives_idle=30&keepalives_interval=10&keepalives_count=5"
# On ajoute les paramètres à l'URL de base, en gérant le cas où
# il y a déjà des paramètres (? existant) ou non.
separator = '&' if '?' in db_url else '?'
db_url_with_keepalives = f"{db_url}{separator}{keepalive_args}"

# Le pool de connexions asynchrone est configuré pour être robuste
# aux timeouts réseau des services cloud comme Azure.
db_pool = AsyncConnectionPool(
    conninfo=db_url_with_keepalives, 
    open=False, # Important: Le cycle de vie est géré par le 'lifespan' de FastAPI
    max_size=20,
    # Timeout pour obtenir une connexion du pool (en secondes)
    timeout=10, 
    # Temps max d'inactivité (en secondes). Après ce délai, la connexion est fermée proprement.
    max_idle=180,
    # La ligne la plus importante : VÉRIFIE si une connexion est toujours vivante
    # avant de la donner à votre code. Si elle est morte, il en ouvrira une nouvelle.
    check=AsyncConnectionPool.check_connection 
)


# =========================================================================
# 3. INITIALISATION DU CHECKPOINTER
# Le checkpointer pour LangGraph est configuré pour utiliser notre pool et notre sérialiseur.
# Chaque graphe créera sa propre instance de checkpointer.
# =========================================================================

# Nous ne créons plus de checkpointer global ici pour éviter les conflits.
# À la place, nous fournissons la configuration pour le créer.

def get_checkpointer() -> AsyncPostgresSaver:
    """
    Crée et retourne une nouvelle instance du checkpointer.
    Doit être appelé une fois par graphe.
    """
    return AsyncPostgresSaver(
        conn=db_pool, 
        serde=PickleSerde
    )


# =========================================================================
# 4. FONCTIONS DE GESTION DU CYCLE DE VIE (pour le lifespan de FastAPI)
# =========================================================================

@asynccontextmanager
async def lifespan(app):
    """
    Gestionnaire de contexte pour le cycle de vie de l'application FastAPI.
    Ouvre le pool de connexions au démarrage et le ferme à l'arrêt.
    """
    print("--- Application Startup: Opening Database Connection Pool ---")
    await db_pool.open()
    yield
    print("--- Application Shutdown: Closing Database Connection Pool ---")
    await db_pool.close()


# =========================================================================
# 5. DÉPENDANCE FASTAPI (pour les autres endpoints)
# Fournit une connexion unique gérée par le pool pour les endpoints qui
# ont besoin de faire des requêtes SQL directes.
# =========================================================================

async def get_db_connection() -> AsyncGenerator[AsyncConnection, None]:
    """
    Dépendance FastAPI qui fournit une connexion unique depuis le pool
    et la libère automatiquement.
    """
    async with db_pool.connection() as conn:
        yield conn