import os
from typing import List, Optional
import time

from fastapi import HTTPException, Query, FastAPI, status, Header
from pydantic import BaseModel, Field
from fastapi import APIRouter
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from src.cleeroute.langGraph.learners_api.metadata_from_learner.prompt_tamplate import CONTEXTE
from src.cleeroute.langGraph.learners_api.metadata_from_learner.prompt_tamplate import SUMMARY_PROMPT, DETAILS_PROMPT

load_dotenv()
from src.cleeroute.langGraph.learners_api.utils import get_llm

class Course_summary(BaseModel):
    """
    Concise summary of a new course, project, or training module.
    """
    title: str = Field(description="The concise and descriptive title of the course or project.")
    domains: List[str] = Field(description="A list of primary knowledge domains or fields this course belongs to (e.g., 'Artificial Intelligence', 'Software Engineering', 'Project Management').")
    categories: List[str] = Field(description="A list of more specific categories or sub-fields within the domains (e.g., 'Machine Learning', 'Web Development', 'Agile Methodologies').")
    topics: List[str] = Field(description="A comprehensive list of specific keywords, concepts, or modules that will be covered within the course.")


class Course_details(BaseModel):
    """
    Detailed section of a new course, project, or training module.
    """
    objectives: List[str] = Field(description="A list of clear, measurable learning objectives or goals that participants will achieve by completing the course. Use impersonal language (e.g., 'Participants will be able to...', 'To understand...').")
    expectations: List[str] = Field(description="A list of what is expected from the participants during the course (e.g., 'active participation', 'completion of assignments', 'prioritization of tasks').")
    prerequisites: List[str] = Field(description="A list of essential prior knowledge, skills, or tools participants should possess before starting the course.")
    desired_level: str = Field(description="The target proficiency level for the audience. Must be one of: 'Beginner', 'Intermediate', 'Advanced'.")


# Chaîne LangChain pour la génération du résumé
def get_summary_llm_chain(llm_instance):
    summary_prompt_template = ChatPromptTemplate.from_messages(SUMMARY_PROMPT)
    return summary_prompt_template | llm_instance.with_structured_output(Course_summary)

def get_details_llm_chain(llm_instance):
    details_prompt_template = ChatPromptTemplate.from_messages(DETAILS_PROMPT)
    return details_prompt_template | llm_instance.with_structured_output(Course_details)


# --- DÉFINITION DE L'APPLICATION FASTAPI ---
router_metadata_1 = APIRouter()
router_metadata_2 = APIRouter()


# Modèle de requête commun pour les deux endpoints (seulement user_prompt)
class SinglePromptRequest(BaseModel):
    user_prompt: str = Field(..., example="Learning langgraph and langchain for AI applications in education.")
    language: str = Field(
        default="English", 
        description="Target language for the metadata generation (e.g., 'French', 'Spanish')."
    )

contexte_data = CONTEXTE

@router_metadata_1.post("/first-generate", response_model=Course_summary, summary="Generate Course Summary")
async def generate_summary_endpoint(
    request: SinglePromptRequest,
    x_gemini_api_key: Optional[str] = Header(None, alias="X-Gemini-Api-Key")
):
    """
    This endpoint generates the first part of meta data course based on a user prompt.

    Allows user to provide their own Gemini API key for developpement purpose.
    """
    print(f"[{time.time():.2f}] Requête reçue pour /generate-summary: prompt='{request.user_prompt}'")

    api_key_to_use = x_gemini_api_key if x_gemini_api_key else os.getenv("GEMINI_API_KEY")

    if not api_key_to_use:
        raise HTTPException(status_code=400, detail="Gemini API key is not provided. Please provide it via 'X-Gemini-Api-Key' header or set GEMINI_API_KEY in .env.")
    
    llm_to_use = get_llm(api_key=os.getenv("GEMINI_API_KEY"))

    summary_llm_chain = get_summary_llm_chain(llm_instance=llm_to_use)
    start_time = time.perf_counter()

    try:
        # Utilise le contexte global par défaut, car 'additional_context' n'est plus une entrée.
        context_for_llm = contexte_data 
        
        summary_proposal = summary_llm_chain.invoke({
            "prompt": "I want to learn" + request.user_prompt,
            "context": context_for_llm,
            "language": request.language
        })
        end_time = time.perf_counter()
        generation_time = end_time - start_time
        
        print(f"[{time.time():.2f}] Résumé généré en {generation_time:.2f} secondes.")
        
        # Le timing n'est plus ajouté à l'objet retourné, mais est loggé.
        return summary_proposal
    except Exception as e:
        print(f"[{time.time():.2f}] Erreur lors de la génération du résumé: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate summary: {str(e)}"
        )



@router_metadata_2.post("/second-generate", response_model=Course_details)
async def generate_details_endpoint(
    request: SinglePromptRequest,
    x_gemini_api_key: Optional[str] = Header(None, alias="X-Gemini-Api-Key")
):
    """
    This endpoint generates the second part of meta data course based on a user prompt.
    """
    print(f"[{time.time():.2f}] Requête reçue pour /generate-details: prompt='{request.user_prompt}'")

    api_key_to_use = x_gemini_api_key if x_gemini_api_key else os.getenv("GEMINI_API_KEY")

    if not api_key_to_use:
        raise HTTPException(status_code=400, detail="Gemini API key is not provided. Please provide it via 'X-Gemini-Api-Key' header or set GEMINI_API_KEY in .env.")
    
    llm_to_use = get_llm(api_key=os.getenv("GEMINI_API_KEY"))

    details_llm_chain = get_details_llm_chain(llm_instance=llm_to_use)

    start_time = time.perf_counter() # Temps pour la génération des détails elle-même
    try:        
        # Utilise le contexte global par défaut

        details_proposal = details_llm_chain.invoke({
            "prompt": "I want to learn" + request.user_prompt,
            "context": request.user_prompt,
            "language": request.language
        })
        end_time = time.perf_counter()
        generation_time = end_time - start_time
        
        print(f"[{time.time():.2f}] Détails générés en {generation_time:.2f} secondes.")

        # Le timing n'est plus ajouté à l'objet retourné, mais est loggé.
        return details_proposal
    except Exception as e:
        print(f"[{time.time():.2f}] Erreur lors de la génération des détails: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate details: {str(e)}"
        )