import io
import os
import uuid
from pypdf import PdfReader
from docx import Document
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# On garde le modèle Vision pour les images
VISION_MODEL = os.getenv("MODEL_2", "gemini-2.5-flash")

class FileIngestionService:
    def __init__(self):
        self.vision_llm = ChatGoogleGenerativeAI(
            model=VISION_MODEL, 
            google_api_key=os.getenv("GEMINI_API_KEY")
        )

    async def process_file(self, session_id: str, filename: str, file_bytes: bytes, file_type: str, db):
        """
        Extrait le texte intégral et le sauvegarde dans la BDD.
        """
        text_content = ""
        
        # --- 1. EXTRACTION DU TEXTE ---
        try:
            if "pdf" in file_type:
                reader = PdfReader(io.BytesIO(file_bytes))
                for page in reader.pages:
                    text_content += (page.extract_text() or "") + "\n"
            
            elif "word" in file_type or "docx" in file_type:
                doc = Document(io.BytesIO(file_bytes))
                for para in doc.paragraphs:
                    text_content += para.text + "\n"
                    
            elif "image" in file_type:
                # Pour les images, on génère toujours une description détaillée
                print(f"--- Vision Analysis for {filename} ---")
                message = HumanMessage(
                    content=[
                        {"type": "text", "text": "Transcribe any text visible in this image exactly. If it is code, preserve the formatting. Then describe any diagrams or visual context."},
                        {"type": "image_url", "image_url": {"url": f"data:{file_type};base64,{file_bytes.decode('utf-8')}" if isinstance(file_bytes, str) else file_bytes}}
                    ]
                )
                res = await self.vision_llm.ainvoke([message])
                text_content = f"[CONTENT OF IMAGE {filename}]:\n{res.content}"
                
            # Fallback pour les fichiers texte brut (code source .py, .js, .txt)
            elif "text" in file_type or "javascript" in file_type or "json" in file_type:
                text_content = file_bytes.decode("utf-8")

        except Exception as e:
            print(f"Error parsing file: {e}")
            raise ValueError("Could not extract text from file.")

        if not text_content.strip():
            raise ValueError("File appears empty or unreadable.")

        # --- 2. SAUVEGARDE EN BDD (Full Text) ---
        file_id = str(uuid.uuid4())
        
        # On sauvegarde le texte brut directement
        await db.execute(
            """
            INSERT INTO knowledge_files (id, session_id, filename, file_type, extracted_text) 
            VALUES (%s, %s, %s, %s, %s)
            """,
            (file_id, session_id, filename, file_type, text_content)
        )
        
        # On retourne la taille pour info
        return len(text_content)

    async def retrieve_relevant_context(self, session_id: str, db) -> str:
        """
        Récupère TOUS les fichiers associés à la session et les concatène.
        Plus de recherche vectorielle.
        """
        # Récupération de tous les fichiers de la session
        cursor = await db.execute(
            "SELECT filename, extracted_text FROM knowledge_files WHERE session_id = %s ORDER BY uploaded_at ASC",
            (session_id,)
        )
        files = await cursor.fetchall()
        
        if not files:
            return ""
            
        # Construction du contexte global
        context_str = "\n\n=== 📂 USER UPLOADED FILES (PRIMARY CONTEXT) ===\n"
        context_str += "The user has uploaded the following files to this chat. Use this content specifically to answer their questions.\n"
        
        for row in files:
            # Gestion tuple vs dict
            fname = row[0] if isinstance(row, tuple) else row['filename']
            raw_content = row[1] if isinstance(row, tuple) else row['extracted_text']
            
            # --- CORRECTION ICI ---
            # Si extracted_text est None (ancien fichier), on met un placeholder ou une chaine vide
            content = raw_content if raw_content is not None else "[Content not available for this file - Please re-upload]"
            
            context_str += f"\n--- START OF FILE: {fname} ---\n"
            context_str += content
            context_str += f"\n--- END OF FILE: {fname} ---\n"
            
        return context_str