import os
import logging
from psycopg_pool import AsyncConnectionPool
from dotenv import load_dotenv

# On importe ton accesseur de pool existant
from src.cleeroute.db.app_db import get_active_pool

load_dotenv()

logger = logging.getLogger(__name__)

async def check_user_premium_status(user_id: str) -> bool:
    """
    Vérifie si un utilisateur possède un abonnement 'active' dans la table subscriptions.
    
    Logique de résilience :
    1. Essaie d'utiliser le pool global de l'application (cas API/FastAPI).
    2. Si le pool n'est pas initialisé (cas Celery Worker), crée une connexion temporaire.
    
    Returns:
        bool: True si premium, False sinon (ou en cas d'erreur).
    """
    if not user_id:
        return False

    # Requête SQL optimisée : on cherche juste l'existence d'une ligne active
    # On suppose que la colonne de jointure est 'user_id'. Adapte si c'est 'id' ou 'userId'.
    query = """
        SELECT 1 
        FROM subscriptions 
        WHERE user_id = %s AND status = 'active'
        LIMIT 1
    """

    try:
        # --- CAS 1 : Utilisation du Pool Global (Contexte FastAPI) ---
        try:
            pool = get_active_pool()
            async with pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(query, (user_id,))
                    result = await cur.fetchone()
                    
                    is_premium = result is not None
                    _log_status(user_id, is_premium)
                    return is_premium

        except RuntimeError:
            # --- CAS 2 : Pool Global non initialisé (Contexte Worker/Script) ---
            # Le pool n'existe pas car on n'est pas passé par app_db_lifespan.
            # On crée une connexion "One-Shot".
            
            db_url = os.getenv("APP_DATABASE_URL")
            if not db_url:
                logger.error("APP_DATABASE_URL missing for manual connection.")
                return False

            # On ouvre un pool temporaire juste pour cette vérification
            async with AsyncConnectionPool(conninfo=db_url, min_size=1, max_size=1) as temp_pool:
                async with temp_pool.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(query, (user_id,))
                        result = await cur.fetchone()
                        
                        is_premium = result is not None
                        _log_status(user_id, is_premium)
                        return is_premium

    except Exception as e:
        # En cas d'erreur DB (timeout, auth...), on ne bloque pas l'utilisateur.
        # On le considère comme "Standard" par défaut pour que le système continue de fonctionner.
        logger.error(f"Error checking premium status for user {user_id}: {e}")
        return False

def _log_status(user_id: str, is_premium: bool):
    """Petit helper pour logger proprement"""
    status_icon = "💎" if is_premium else "👤"
    status_text = "PREMIUM" if is_premium else "STANDARD"
    # Utilise print ou logger selon ta préférence
    print(f"--- {status_icon} User {user_id} is {status_text} ---")