from src.cleeroute.db.db import get_db_connection
from src.cleeroute.db.models import VideoSearch
from sentence_transformers import SentenceTransformer
import numpy as np
import json
import torch 
import psycopg2
from psycopg2.extras import RealDictCursor
import time
import os

# --- Database Connection Parameters ---
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME") 
DB_USER = os.getenv("USER")
DB_PASS = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT")

# --- Model Configuration ---
MODEL_CONFIG = {
    "model_name": "intfloat/multilingual-e5-small",
    "use_gpu": True,
    "use_fp16": True 
}

# Global model cache to avoid reloading
_model_cache = {}

def get_sentence_transformer_model(config):
    model_name = config["model_name"]
    if model_name not in _model_cache:
        print(f"Loading SentenceTransformer model: {model_name}...")
        start_time = time.time()
        # Explicitly check if GPU is requested AND available
        if config.get("use_gpu", False) and torch.cuda.is_available():
            device = 'cuda'
            print("Using GPU.")
        else:
            device = 'cpu'
            if config.get("use_gpu", False):
                 print("GPU requested but not available. Falling back to CPU.")
            else:
                 print("Using CPU (GPU not requested).")

        _model_cache[model_name] = SentenceTransformer(model_name, device=device)

        if config.get("use_fp16", False) and device == 'cuda':
             print("FP16 mode suggested for GPU. PyTorch/model will handle precision (likely using AMP).")
             pass # Remove or comment out model.half() unless specifically needed and tested.

        print(f"Model loaded in {time.time() - start_time:.2f}s (Device: {device})")
    return _model_cache[model_name]

def get_embedding(text, model_config):
    model = get_sentence_transformer_model(model_config)
    print(f"Generating embedding for subsection: '{text[:50]}...'")
    start_time = time.time()
   
    embedding = model.encode(text, convert_to_numpy=True)
    print(f"Subsection embedding generated in {time.time() - start_time:.2f}s (Shape: {embedding.shape})")
    return embedding


# (Assuming your DB_VARS are defined)

def fetch_channel_categories(category_name, max_position=1):
    conn = None
    results = None
    sql_query = """
        SELECT channel_name 
        FROM channel_category
        WHERE category = %s AND "position" <= %s;
    """

    print(f"Executing query to fetch channel names for category: '{category_name}'")

    try:
        conn = psycopg2.connect(
            host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASS, port=DB_PORT
        )
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql_query, (category_name, max_position))
            # fetchall() will return a list of RealDictRow objects, e.g., [{'channel_name': 'MKBHD'}, {'channel_name': 'LTT'}]
            results = cur.fetchall()

    except (Exception, psycopg2.Error) as error:
        print(f"Error while fetching channel categories: {error}")
        return [] # Return an empty list on error
    finally:
        if conn:
            conn.close()


    if results:
        return [row['channel_name'] for row in results]
    else:
        return []


def search_videos_pgvector_manual_string(subsection_text, channel_names_list, top_k=1000):
    if not channel_names_list:
        print("Error: Channel names list cannot be empty.")
        return []

    overall_start_time = time.time()

    # 1. Get subsection embedding
    subsection_embedding_np = get_embedding(subsection_text, MODEL_CONFIG)

    # Convert NumPy embedding to string format for pgvector: e.g., "[0.1,0.2,0.3]"
    embedding_str = '[' + ','.join(map(str, subsection_embedding_np.tolist())) + ']'

    conn = None
    results = None
    try:
        conn_start_time = time.time()
        conn = psycopg2.connect(
            host=DB_HOST, database=DB_NAME,
            user=DB_USER, password=DB_PASS, port=DB_PORT
        )
        print(f"DB connection established in {time.time() - conn_start_time:.2f}s")
        # Removed: register_vector(conn)

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            
            sql_query = f"""
                SELECT
                    id, video_id, title, channel_name,thumbnail,duration,created_at,
                    1 - (embedding <=> %s::vector) AS cosine_similarity
                FROM videos
                WHERE channel_name = ANY(%s) -- Filter by channel names
                ORDER BY cosine_similarity DESC
                LIMIT %s;
            """
            # Parameters: embedding_str, channel_names_list, top_k
            params = (embedding_str, channel_names_list, top_k)

            print(f"Executing database search with manual string embedding...")
            db_search_start_time = time.time()
            cur.execute(sql_query, params)
            results = cur.fetchall()
            db_search_duration = time.time() - db_search_start_time
            print(f"Database search and fetch (found {len(results) if results else 0} results) completed in {db_search_duration:.2f}s")

    except (Exception, psycopg2.Error) as error:
        print(f"Error during database operation: {error}")
        return None
    finally:
        if conn:
            conn.close()

    print(f"Total search_videos_pgvector_manual_string function execution time: {time.time() - overall_start_time:.2f}s")
    return results