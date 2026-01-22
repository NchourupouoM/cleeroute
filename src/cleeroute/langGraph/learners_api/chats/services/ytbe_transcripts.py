import json
import math
from typing import List, Dict, Any
from psycopg.connection_async import AsyncConnection
from src.cleeroute.langGraph.learners_api.utils import get_embedding_model, get_llm
from src.cleeroute.langGraph.learners_api.chats.prompts import SUMMARY_TIMESTAMPED_YT_TRANSCRIPT
import os


class TranscriptService:
    def __init__(self):
        self.embeddings = get_embedding_model(api_key=os.getenv("GEMINI_API_KEY"))
        self.llm = get_llm(api_key=os.getenv("GEMINI_API_KEY"))

    def _format_seconds(self, seconds: float) -> str:
        """Convertit 125.5 -> '02:05'"""
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _prepare_chunks(self, transcript_json: List[Dict], chunk_size: int = 800):
        """
        Transforme le JSON brut en chunks textuels avec timestamps.
        Regroupe les petites phrases en paragraphes cohérents.
        """
        chunks = []
        current_chunk_text = ""
        current_start_time = 0.0
        current_length = 0
        
        # On suppose que transcript_json est une liste de dicts triée
        # [{'text': 'Hello', 'offset': '0.0'}, ...]
        
        for i, item in enumerate(transcript_json):
            text = item.get('text', '').strip()
            # offset est parfois string, parfois float
            try:
                start = float(item.get('offset', 0))
            except:
                start = 0.0
                
            if i == 0: 
                current_start_time = start

            # On ajoute le timestamp dans le texte pour que le LLM ait la notion du temps
            # Format: "[00:12] Le texte..."
            time_tag = f"[{self._format_seconds(start)}] "
            segment = f"{time_tag}{text} "
            
            # Si le chunk devient trop gros, on le ferme et on en ouvre un nouveau
            if current_length + len(segment) > chunk_size:
                chunks.append({
                    "content": current_chunk_text.strip(),
                    "start_seconds": current_start_time
                })
                current_chunk_text = segment
                current_length = len(segment)
                current_start_time = start
            else:
                current_chunk_text += segment
                current_length += len(segment)

        # Dernier chunk
        if current_chunk_text:
            chunks.append({
                "content": current_chunk_text.strip(),
                "start_seconds": current_start_time
            })
            
        return chunks

    async def generate_timestamped_summary(self, full_text_with_timestamps: str) -> str:
        """Génère un résumé avec chapitrage."""
        # On tronque pour le résumé si trop long (Gemini supporte beaucoup, mais restons prudents)
        input_text = full_text_with_timestamps
        
        chain = SUMMARY_TIMESTAMPED_YT_TRANSCRIPT | self.llm
        try:
            res = await chain.ainvoke({"input_text": input_text})
            return res.content
        except:
            return "Summary unavailable."

    async def ingest_transcript_if_needed(self, db: AsyncConnection, subsection_id: str):
        """
        Vérifie si le transcript est déjà ingéré pour cette vidéo. Sinon, le traite.
        """
        # 1. Vérifier si déjà ingéré (table summaries est un bon indicateur)
        cursor = await db.execute("SELECT 1 FROM transcript_summaries WHERE subsection_id = %s", (subsection_id,))
        if await cursor.fetchone():
            return # Déjà fait
            
        print(f"--- Ingesting Transcript for Subsection {subsection_id} ---")
        
        # 2. Récupérer le JSON brut depuis la table existante
        cursor = await db.execute("SELECT content FROM subsection_transcripts WHERE subsection_id = %s", (subsection_id,))
        row = await cursor.fetchone()
        
        if not row:
            print("No transcript found in DB.")
            return

        # row[0] est déjà un objet Python (list/dict) grâce à psycopg et JSONB
        transcript_data = row[0] 
        if not transcript_data or not isinstance(transcript_data, list):
            return

        # 3. Préparer les Chunks
        chunks = self._prepare_chunks(transcript_data)
        
        # 4. Vectoriser (Batch)
        texts_to_embed = [c["content"] for c in chunks]
        try:
            vectors = await self.embeddings.aembed_documents(texts_to_embed)
        except Exception as e:
            print(f"Embedding error: {e}")
            return

        # 5. Sauvegarder Chunks + Vecteurs
        for i, (chunk_data, vector) in enumerate(zip(chunks, vectors)):
            await db.execute(
                """
                INSERT INTO transcript_chunks (subsection_id, chunk_index, start_seconds, content, embedding)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (subsection_id, i, chunk_data["start_seconds"], chunk_data["content"], str(vector))
            )

        # 6. Générer et Sauvegarder le Résumé
        # On reconstruit un texte complet léger pour le résumé
        full_text = "\n".join([c["content"] for c in chunks])
        summary = await self.generate_timestamped_summary(full_text)
        
        await db.execute(
            """
            INSERT INTO transcript_summaries (subsection_id, summary_text)
            VALUES (%s, %s)
            ON CONFLICT (subsection_id) DO UPDATE SET summary_text = EXCLUDED.summary_text
            """,
            (subsection_id, summary)
        )
        print("--- Transcript Ingestion Complete ---")

    async def retrieve_context(self, db: AsyncConnection, subsection_id: str, user_query: str, limit: int = 3):
        """
            Récupère : 
                1. Le résumé global, 
                2. Les passages précis liés à la question.
        """
        # A. Récupérer le résumé
        cursor = await db.execute("SELECT summary_text FROM transcript_summaries WHERE subsection_id = %s", (subsection_id,))
        row = await cursor.fetchone()
        summary = row[0] if row else "No summary available."
        
        context_str = f"=== CURRENT VIDEO CONTEXT (Timestamps included) ===\n\n**Video Summary:**\n{summary}\n\n"

        # B. Recherche Vectorielle (RAG)
        if len(user_query) > 5:
            try:
                query_vector = await self.embeddings.aembed_query(user_query)
                
                cursor = await db.execute(
                    """
                    SELECT content, start_seconds
                    FROM transcript_chunks
                    WHERE subsection_id = %s
                    ORDER BY embedding <=> %s
                    LIMIT %s
                    """,
                    (subsection_id, str(query_vector), limit)
                )
                results = await cursor.fetchall()
                
                if results:
                    context_str += "**Relevant Transcript Segments:**\n"
                    for res in results:
                        text = res[0] if isinstance(res, tuple) else res['content']
                        # start = res[1] # Pas besoin de l'afficher, il est déjà dans le texte [MM:SS]
                        context_str += f"... {text} ...\n\n"
            except Exception as e:
                print(f"Transcript RAG Error: {e}")

        return context_str