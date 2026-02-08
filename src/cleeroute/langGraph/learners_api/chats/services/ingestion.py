import io
import os
import uuid
import base64
from typing import Dict, Any

# Libraries d'extraction
import pdfplumber
from docx import Document
from PIL import Image

from src.cleeroute.langGraph.learners_api.chats.prompts import SOMMARIZE_UPLOADED_FILE_PROMPT

# LangChain / Google
from langchain_core.messages import HumanMessage
from langchain_text_splitters import RecursiveCharacterTextSplitter
from src.cleeroute.langGraph.learners_api.utils import get_vision_model, get_embedding_model

from src.cleeroute.langGraph.learners_api.chats.services.azure_storage_service import AzureStorageService

VISION_MODEL = os.getenv("MODEL")
EMBEDDING_MODEL = "models/text-embedding-004"


class FileIngestionService:
    def __init__(self):
        # On utilise un modèle rapide et peu coûteux
        self.llm = get_vision_model()
        self.embeddings = get_embedding_model()
        self.azure_service = AzureStorageService()

        # Découpage intelligent : on essaie de couper aux paragraphes
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, 
            chunk_overlap=200,
            separators=["\n\n", "\n", ". ", " ", ""]
        )

    async def _extract_text_from_pdf(self, file_bytes: bytes) -> str:
        """Extraction haute fidélité pour PDF."""
        text = ""
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    # layout=True aide à garder la structure visuelle
                    page_text = page.extract_text(layout=True)
                    if page_text:
                        text += page_text + "\n\n"
            return text.strip()
        except Exception as e:
            print(f"Error extracting text from PDF: {e}")
            return ""

    async def _extract_text_from_docx(self, file_bytes: bytes) -> str:
        """Extraction Word."""
        try:
            doc = Document(io.BytesIO(file_bytes))
            return "\n".join([para.text for para in doc.paragraphs]).strip()
        except Exception:
            return ""

    async def _analyze_image(self, file_bytes: bytes, mime_type: str, filename: str) -> str:
        """Utilise Gemini Vision pour décrire une image (OCR intelligent)."""
        b64_data = base64.b64encode(file_bytes).decode('utf-8')
        
        prompt = f"""
            You are a specialized OCR engine for technical documentation.
            Filename: {filename}

            **TASK:**
            Transcribe the content of this image EXACTLY as it appears. 

            **STRICT RULES:**
            1. If the image contains CODE, output it inside markdown code blocks (```language ... ```). Preserve indentation strictly.
            2. Do NOT describe the image visually (e.g., "This is a screenshot of code"). JUST output the text content.
            3. Do NOT add introductions or conclusions like "Here is the code".
            4. If it's a diagram, describe the logic flow simply.
        """
        
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}}
            ]
        )
        res = await self.llm.ainvoke([message])
        return f"[IMAGE CONTENT: {filename}]\n{res.content}"

    async def generate_summary(self, text: str) -> str:
        """
        Génération de résumé ULTRA-CONCISE pour la sidebar UI.
        """
        if not text or len(text) < 10: 
            return "No content detected."
                
        chain = SOMMARIZE_UPLOADED_FILE_PROMPT | self.llm

        try:
            res = await chain.ainvoke({"input_text": text})
            # Nettoyage de sécurité post-LLM
            clean_summary = res.content.strip()
            # Si le LLM a mis "Here is...", on le coupe (fallback python)
            if "Here is" in clean_summary:
                clean_summary = clean_summary.split("\n", 1)[-1].strip()
                
            return clean_summary
        except:
            return "Summary unavailable."

    async def process_file(self, session_id: str, filename: str, file_bytes: bytes, file_type: str, db) -> Dict[str, Any]:
        """
            complete process of ingestion:
            1. Upload to Azure Storage
            2. Extract text based on file type
            3. Generate summary
            4. Store metadata in DB
            5. Chunking & Embedding for RAG
        """

        # 1. UPLOAD SUR AZURE (Nouveau)
        # On le fait en premier pour sécuriser le fichier binaire
        try:
            print(f"--- Uploading {filename} to Azure... ---")
            storage_path = await self.azure_service.upload_file(file_bytes, filename, session_id, content_type=file_type )
        except Exception as e:
            print(f"Azure Upload Failed: {e}")
            raise e # Si l'upload échoue, on arrête tout

        extracted_text = ""
        
        # 1. Extraction
        try:
            if "pdf" in file_type:
                extracted_text = await self._extract_text_from_pdf(file_bytes)
            elif "word" in file_type or "docx" in file_type:
                extracted_text = await self._extract_text_from_docx(file_bytes)
            elif "image" in file_type:
                extracted_text = await self._analyze_image(file_bytes, file_type, filename)
            elif "text" in file_type:
                extracted_text = file_bytes.decode('utf-8')
            else:
                # Tentative fallback texte
                extracted_text = file_bytes.decode('utf-8')

            if not extracted_text.strip():
                raise ValueError("Empty or unreadable file.")
            
            summary = await self.generate_summary(extracted_text)
                
        except Exception as e:
            print(f"Extraction failed for {filename}: {e}")
            raise e

        # 2. Résumé
        summary = await self.generate_summary(extracted_text)

        # 3. Sauvegarde BDD
        file_id = str(uuid.uuid4())
        await db.execute(
            """
            INSERT INTO knowledge_files (id, session_id, filename, file_type, extracted_text, summary, file_size, storage_path) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (file_id, session_id, filename, file_type, extracted_text, summary, len(file_bytes), storage_path)
        )

        # 4. Chunking & Embedding (Le RAG)
        chunks = self.text_splitter.split_text(extracted_text)

        if chunks:
            # Vectorisation par lot (Batch) pour la vitesse
            # Attention aux limites de quota, on peut faire des mini-batchs si nécessaire
            vectors = await self.embeddings.aembed_documents(chunks)
            
            # Insertion des chunks
            values = []
            for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
                # Préparation pour execute_many ou boucle
                await db.execute(
                    """
                    INSERT INTO knowledge_chunks (file_id, chunk_index, content, embedding)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (file_id, i, chunk, str(vector))
                )

        return {
            "file_id": file_id,
            "filename": filename,
            "summary": summary,
            "chunks_count": len(chunks)
        }
    

    async def retrieve_hybrid_context(self, session_id: str,query: str, db, limit: int = 5) -> str:
        """
            Stratégie SOTA : Résumés (Toujours) + Chunks Pertinents (RAG hierarchique).
        """

        # A. Récupérer TOUS les résumés des fichiers de la session
        cursor = await db.execute(
            "SELECT filename, summary FROM knowledge_files WHERE session_id = %s ORDER BY uploaded_at ASC",
            (session_id,)
        )
        files = await cursor.fetchall()
        
        if not files: 
            return ""
            
        context_str = "\n\n=== AVAILABLE DOCUMENTS (SUMMARIES) ===\n"
        for row in files:
            fname = row[0] if isinstance(row, tuple) else row['filename']
            summ = row[1] if isinstance(row, tuple) else row['summary']
            
            context_str += f"File: {fname}\nSummary: {summ}\n---\n"

        # B. Récupérer les Chunks précis via Vector Search
        # Si la requête est vide ou triviale (ex: "Bonjour"), on peut skipper ça pour économiser
        if len(query) > 5:
            try:
                query_vector = await self.embeddings.aembed_query(query)
                
                cursor = await db.execute(
                    """
                    SELECT c.content, f.filename, (c.embedding <=> %s) as distance
                    FROM knowledge_chunks c
                    JOIN knowledge_files f ON c.file_id = f.id
                    WHERE f.session_id = %s
                    ORDER BY distance ASC
                    LIMIT %s
                    """,
                    (str(query_vector), session_id, limit)
                )
                chunks = await cursor.fetchall()
                
                if chunks:
                    context_str += "\n=== RELEVANT DETAILS (RAG) ===\n"
                    for row in chunks:
                        content = row[0] if isinstance(row, tuple) else row['content']
                        fname = row[1] if isinstance(row, tuple) else row['filename']
                        context_str += f"Source ({fname}): ...{content}...\n"
            except Exception as e:
                print(f"RAG Retrieval warning: {e}")
            
        return context_str