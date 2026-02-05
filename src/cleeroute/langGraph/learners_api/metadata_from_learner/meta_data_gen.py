import os
import time
import asyncio
import logging
from typing import List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Header, Depends, status
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

# On suppose que ton utilitaire est ici
from src.cleeroute.langGraph.learners_api.utils import get_llm
# Si tu as besoin du contexte externe
from src.cleeroute.langGraph.learners_api.metadata_from_learner.prompt_tamplate import CONTEXTE
from src.cleeroute.langGraph.learners_api.metadata_from_learner.prompt_tamplate import SUMMARY_PROMPT, DETAILS_PROMPT

load_dotenv()

# Configuration du Logger (plus propre que print)
logger = logging.getLogger("uvicorn.error")

class SinglePromptRequest(BaseModel):
    user_prompt: str = Field(..., example="Learning langgraph")
    language: str = Field(default="English", description="Target language (e.g., 'French', 'Spanish').")

class CourseSummary(BaseModel):
    """Concise summary of a new course."""
    title: str = Field(description="Concise and descriptive title.")
    domains: List[str] = Field(description="Primary knowledge domains.")
    categories: List[str] = Field(description="Specific categories.")
    desired_level: str = Field(default="Beginner",description="Target proficiency: 'Beginner', 'Intermediate', 'Advanced'.")


class CourseDetails(BaseModel):
    """Detailed section of a new course."""
    topics: List[str] = Field(description="Comprehensive list of keywords/concepts.")
    objectives: List[str] = Field(description="Measurable learning objectives (first-person plural).")
    expectations: List[str] = Field(description="Expectations from participants.")
    prerequisites: List[str] = Field(description="Essential prior knowledge.")

class FullCourseMetadata(BaseModel):
    """Combined model for optimization."""
    summary: CourseSummary
    details: CourseDetails

async def get_llm_service(
    x_gemini_api_key: Optional[str] = Header(None, alias="X-Gemini-Api-Key")
) -> ChatGoogleGenerativeAI:
    """
    Dependency to validate API Key and return the LLM instance.
    """
    api_key = x_gemini_api_key or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=400, 
            detail="Gemini API key missing. Set GEMINI_API_KEY env var or use X-Gemini-Api-Key header."
        )
    
    # Assure-toi que get_llm configure bien le modèle (ex: gemini-1.5-flash est BEAUCOUP plus rapide)
    return get_llm(api_key=api_key)

async def generate_summary_task(llm, user_prompt: str, language: str, context: str) -> CourseSummary:
    prompt_template = ChatPromptTemplate.from_messages(SUMMARY_PROMPT)
    chain = prompt_template | llm.with_structured_output(CourseSummary)
    
    # Utilisation de ainvoke (Asynchrone)
    return await chain.ainvoke({
        "prompt": f"I want to learn {user_prompt}",
        "context": context,
        "language": language
    })

async def generate_details_task(llm, user_prompt: str, language: str, context: str) -> CourseDetails:
    prompt_template = ChatPromptTemplate.from_messages(DETAILS_PROMPT)
    chain = prompt_template | llm.with_structured_output(CourseDetails)
    
    # Utilisation de ainvoke (Asynchrone)
    # Note: On peut utiliser le user_prompt comme contexte si le résumé n'est pas encore dispo
    return await chain.ainvoke({
        "prompt": f"I want to learn {user_prompt}",
        "context": context, # Ici on passe le prompt brut ou un contexte spécifique
        "language": language
    })

router_metadata = APIRouter()

@router_metadata.post("/generate-full-metadata", response_model=FullCourseMetadata)
async def generate_full_metadata(
    request: SinglePromptRequest,
    llm=Depends(get_llm_service)
):
    """
    OPTIMIZED ENDPOINT: Generates both Summary and Details in PARALLEL.
    This is the fastest method (Latence = Max(Summary, Details) instead of Sum).
    """
    start_time = time.perf_counter()
    logger.info(f"Starting parallel generation for: {request.user_prompt}")

    try:
        # Lancement des deux tâches en parallèle
        # On passe CONTEXTE pour le résumé, et le user_prompt (ou CONTEXTE) pour les détails
        summary_task = generate_summary_task(llm, request.user_prompt, request.language, CONTEXTE)
        details_task = generate_details_task(llm, request.user_prompt, request.language, request.user_prompt)

        # Attente simultanée
        summary_res, details_res = await asyncio.gather(summary_task, details_task)

        duration = time.perf_counter() - start_time
        logger.info(f"Full metadata generated in {duration:.2f}s")

        return FullCourseMetadata(summary=summary_res, details=details_res)

    except Exception as e:
        logger.error(f"Error in generation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_metadata.post("/first-generate", response_model=CourseSummary)
async def generate_summary_only(
    request: SinglePromptRequest,
    llm=Depends(get_llm_service)
):
    """Optimized async summary generation."""
    try:
        return await generate_summary_task(llm, request.user_prompt, request.language, CONTEXTE)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router_metadata.post("/second-generate", response_model=CourseDetails)
async def generate_details_only(
    request: SinglePromptRequest,
    llm=Depends(get_llm_service)
):
    """Optimized async details generation."""
    try:
        return await generate_details_task(llm, request.user_prompt, request.language, request.user_prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))