import os
import time
import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from src.cleeroute.langGraph.learners_api.utils import get_llm
from src.cleeroute.langGraph.learners_api.metadata_from_learner.prompt_tamplate import CONTEXTE

# On garde la taxonomie pour l'inférence rapide
from src.cleeroute.langGraph.learners_api.metadata_from_learner.taxonomy import (
    ALL_CATEGORIES_STR, 
    get_domain_from_category
)

load_dotenv()

# Configuration du Logger
logger = logging.getLogger("uvicorn.error")

# ==========================================
# 1. MODÈLES DE DONNÉES (REFONDU)
# ==========================================

class SinglePromptRequest(BaseModel):
    user_prompt: str = Field(..., example="Learning langgraph and langchain for AI applications in education.")
    language: str = Field(default="English", description="Target language (e.g., 'French', 'Spanish').")

class AIClassificationResult(BaseModel):
    """
    Modèle INTERMÉDIAIRE (Output IA Endpoint 1).
    Ultra léger : Titre + Catégorie uniquement.
    """
    title: str = Field(description="A concise and engaging title for the course.")
    category: str = Field(description="The exact category selected from the provided list.")

class CourseSummary(BaseModel):
    """
    Modèle FINAL Endpoint 1 (API Response).
    Ne contient plus les topics.
    """
    title: str = Field(description="Concise and descriptive title.")
    domains: List[str] = Field(description="Primary knowledge domains (Inferred).")
    categories: List[str] = Field(description="Specific categories.")
    desired_level: str = Field(description="Target proficiency, hardcoded to Beginner.")

class CourseDetails(BaseModel):
    """
    Modèle FINAL Endpoint 2.
    Contient maintenant les Topics (Génération créative).
    """
    topics: List[str] = Field(description="A comprehensive list of 5-7 specific keywords/concepts/modules.")
    objectives: List[str] = Field(description="Measurable learning objectives (first-person plural).")
    expectations: List[str] = Field(description="Expectations from participants.")
    prerequisites: List[str] = Field(description="Essential prior knowledge.")
    desired_level: str = Field(description="Target proficiency: 'Beginner', 'Intermediate', 'Advanced'.")

class FullCourseMetadata(BaseModel):
    """Combined model."""
    summary: CourseSummary
    details: CourseDetails

# ==========================================
# 2. PROMPTS CORRIGÉS & OPTIMISÉS
# ==========================================

# CORRECTION CRITIQUE : Ajout de la variable {user_prompt}
CLASSIFICATION_PROMPT = """
SYSTEM: You are an expert educational classifier.

TASK: Analyze the USER REQUEST below and map it to ONE category from the list.
Language: {language}

AVAILABLE CATEGORIES:
[{all_categories}]

USER REQUEST:
"{user_prompt}"

INSTRUCTIONS:
1. **Title**: Create a short, engaging course title based on the request.
2. **Category**: Select the SINGLE most relevant category from the list above. It must match EXACTLY.

OUTPUT: Return strictly a JSON object matching `AIClassificationResult` (Title + Category).
"""

# Nouveau Prompt pour le second endpoint (incluant les topics)
DETAILS_GENERATION_PROMPT = """
SYSTEM: You are an expert instructional designer.
Role: Define the detailed curriculum structure for a course.
Language: {language}

USER REQUEST:
"{user_prompt}"

INSTRUCTIONS:
1. **Topics**: Generate 5 to 7 specific technical keywords or module names covered in this course.
2. **Objectives**: Write clear learning goals (start with "We will...", "You will learn...").
3. **Prerequisites**: What is needed before starting?
4. **Level**: Determine the best fit (Beginner/Intermediate/Advanced) based on the request complexity.

OUTPUT: Return strictly a JSON object matching `CourseDetails`.
"""

# ==========================================
# 3. DEPENDENCIES
# ==========================================

async def get_llm_service(
    x_gemini_api_key: Optional[str] = Header(None, alias="X-Gemini-Api-Key")
) -> ChatGoogleGenerativeAI:
    api_key = x_gemini_api_key or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="Gemini API key missing.")
    return get_llm(api_key=api_key)

# ==========================================
# 4. TASKS (LOGIQUE MÉTIER)
# ==========================================

async def generate_summary_task(llm, user_prompt: str, language: str) -> CourseSummary:
    """
    TASK 1 (Ultra Fast): Classification + Inference.
    NO TOPICS generated here.
    """
    prompt_template = ChatPromptTemplate.from_template(CLASSIFICATION_PROMPT)
    chain = prompt_template | llm.with_structured_output(AIClassificationResult)
    
    # Appel LLM (Input: Prompt + Taxonomie)
    ai_result = await chain.ainvoke({
        "user_prompt": user_prompt,
        "language": language,
        "all_categories": ALL_CATEGORIES_STR 
    })

    # Inférence Python (Domaine)
    inferred_domain = get_domain_from_category(ai_result.category)

    return CourseSummary(
        title=ai_result.title,
        domains=[inferred_domain],
        categories=[ai_result.category],
        desired_level="Beginner" # Hardcoded comme demandé
    )

async def generate_details_task(llm, user_prompt: str, language: str) -> CourseDetails:
    """
    TASK 2 (Creative): Topics + Details.
    """
    prompt_template = ChatPromptTemplate.from_template(DETAILS_GENERATION_PROMPT)
    chain = prompt_template | llm.with_structured_output(CourseDetails)
    
    return await chain.ainvoke({
        "user_prompt": user_prompt,
        "language": language
    })

# ==========================================
# 5. ROUTER & ENDPOINTS
# ==========================================

router_metadata = APIRouter()

@router_metadata.post("/generate-full-metadata", response_model=FullCourseMetadata)
async def generate_full_metadata(
    request: SinglePromptRequest,
    llm=Depends(get_llm_service)
):
    """
    PARALLEL GENERATION:
    - Task 1: Title/Category (Classification) -> Instant
    - Task 2: Topics/Details (Generation) -> Fast
    """
    start_time = time.perf_counter()
    logger.info(f"Starting parallel generation for: {request.user_prompt}")

    try:
        # Lancement parallèle
        summary_task = generate_summary_task(llm, request.user_prompt, request.language)
        details_task = generate_details_task(llm, request.user_prompt, request.language)

        summary_res, details_res = await asyncio.gather(summary_task, details_task)

        return FullCourseMetadata(summary=summary_res, details=details_res)

    except Exception as e:
        logger.error(f"Error in generation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router_metadata.post("/first-generate", response_model=CourseSummary)
async def generate_summary_only(
    request: SinglePromptRequest,
    llm=Depends(get_llm_service)
):
    """
    ULTRA FAST: Title & Category only.
    Python infers Domain. Level is Beginner.
    """
    try:
        result = await generate_summary_task(llm, request.user_prompt, request.language)
        return result
    except Exception as e:
        logger.error(f"Summary generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router_metadata.post("/second-generate", response_model=CourseDetails)
async def generate_details_only(
    request: SinglePromptRequest,
    llm=Depends(get_llm_service)
):
    """
    CREATIVE: Generates Topics, Objectives, Prerequisites.
    """
    try:
        return await generate_details_task(llm, request.user_prompt, request.language)
    except Exception as e:
        logger.error(f"Details generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))