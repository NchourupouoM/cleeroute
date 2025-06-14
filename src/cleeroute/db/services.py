from src.cleeroute.db.db import get_db_connection
from src.cleeroute.db.models import VideoSearch
from sentence_transformers import SentenceTransformer
import numpy as np
import json 

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

def get_embeddings(text: str):
    return model.encode(text).tolist()

def search_similar_videos(search_request: VideoSearch, limit: int = 1000):

    search_text = f"{search_request.section}{search_request.subsection}{search_request.title}"

    # embedding generated for search_text
    search_embedding = get_embeddings(search_text)

    search_embedding_pg_format = json.dumps(search_embedding)
    conn = get_db_connection()
    cur = conn.cursor()

    query = """
    WITH filtered_channels AS (
        SELECT channel_name 
        FROM channel_category
        WHERE category = %s and position < 5
        LIMIT 1000
    ),
    filtered_videos AS (
        SELECT v.video_id, v.thumbnail, v.duration, v.title, v.embedding
        FROM videos v
        JOIN filtered_channels fc ON v.channel_name = fc.channel_name
        LIMIT 100000
    )
    SELECT 
        thumbnail,
        video_id,
        duration, 
        title,
        (embedding <=> %s) as similarity
    FROM filtered_videos
    ORDER BY similarity DESC
    LIMIT %s
    """

    # Exécution avec les paramètres
    cur.execute(query, (
        search_request.category,
        search_embedding_pg_format,
        limit
    ))

    results = cur.fetchall()
    conn.close()
    return results