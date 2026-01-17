import io
import os
import uuid
import base64
from typing import Dict, Any

# Libraries d'extraction
import pdfplumber
from docx import Document
from PIL import Image

# LangChain / Google
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

# Config
VISION_MODEL = os.getenv("MODEL_2", "gemini-2.5-flash")

class FileIngestionService:
    def __init__(self):
        # On utilise un modèle rapide et peu coûteux
        self.llm = ChatGoogleGenerativeAI(
            model=VISION_MODEL, 
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0.1
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
        if not text or len(text) < 10: return "No content detected."
        
        # On limite l'input
        input_text = text[:15000] 
        
        prompt = f"""
            You are a concise data summarizer for a UI Sidebar.
            
            **TASK:** Create a summary of the following content.
            
            **CONSTRAINTS (MUST FOLLOW):**
            1. Output EXACTLY shorts bullet points (using '- ').
            2. NO introductory phrases (Never say "Here is a summary", "The file contains").
            3. NO bolding (**text**) or markdown formatting other than the dash.
            4. Be technical and direct.
            
            **CONTENT:**
            {input_text}
        """
        try:
            res = await self.llm.ainvoke(prompt)
            # Nettoyage de sécurité post-LLM
            clean_summary = res.content.strip()
            # Si le LLM a mis "Here is...", on le coupe (fallback python)
            if "Here is" in clean_summary:
                clean_summary = clean_summary.split("\n", 1)[-1].strip()
                
            return clean_summary
        except:
            return "Summary unavailable."

    async def process_file(self, session_id: str, filename: str, file_bytes: bytes, file_type: str, db) -> Dict[str, Any]:
        """Orchestre l'extraction et la sauvegarde."""
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
                
        except Exception as e:
            print(f"Extraction failed for {filename}: {e}")
            raise e

        # 2. Résumé
        summary = await self.generate_summary(extracted_text)

        # 3. Sauvegarde BDD
        file_id = str(uuid.uuid4())
        await db.execute(
            """
            INSERT INTO knowledge_files (id, session_id, filename, file_type, extracted_text, summary, file_size) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (file_id, session_id, filename, file_type, extracted_text, summary, len(file_bytes))
        )

        return {
            "file_id": file_id,
            "filename": filename,
            "summary": summary
        }

    async def retrieve_relevant_context(self, session_id: str, db) -> str:
        """
        Récupère TOUT le contenu des fichiers de cette session pour le Chat.
        """
        cursor = await db.execute(
            "SELECT filename, extracted_text FROM knowledge_files WHERE session_id = %s ORDER BY uploaded_at ASC",
            (session_id,)
        )
        files = await cursor.fetchall()
        
        if not files: return ""
            
        context = "\n\n=== USER UPLOADED FILES (High Priority) ===\n"
        for row in files:
            fname = row[0] if isinstance(row, tuple) else row['filename']
            content = row[1] if isinstance(row, tuple) else row['extracted_text']
            
            # Protection contre les anciens fichiers NULL
            safe_content = content if content else "[No content extracted]"
            
            context += f"\n--- START FILE: {fname} ---\n{safe_content}\n--- END FILE ---\n"
            
        return context