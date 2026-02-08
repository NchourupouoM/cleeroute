from langchain_google_genai import ChatGoogleGenerativeAI
# from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from typing import TypedDict
from fastapi import APIRouter, Header, HTTPException
from typing import Optional
import os
from dotenv import load_dotenv

# Importations des modeles
from src.cleeroute.langGraph.sections_subsections_sep.models import ( # Assurez-vous que le chemin est correct
    CourseInput, 
    SubsectionOutput,
    Course_section,
    SubsectionGenerationInput,
)

# Importations des prompts
from src.cleeroute.langGraph.sections_subsections_sep.prompt import (
    PROMPT_GENERATE_COURSE_OUTLINE, 
    PROMPT_GENERATE_SUBSECTIONS
)

load_dotenv()

# Configuration LLM globall
# llm_gemini = ChatGoogleGenerativeAI( # Renommé pour plus de clarté
#     model=os.getenv("MODEL2"), # Utilisez un modèle robuste pour la génération de structure
#     google_api_key=os.getenv("GEMINI_API_KEY"),
#     temperature=0.2, # Un peu plus de créativité pour les descriptions
# )

# =============================== API 1: Génération de l'esquisse du cours (Header + Sections Skeletons) ================

# Graph State pour la première API.
class CourseOutlineGraphState(TypedDict):
    metadata: CourseInput
    course_section: Course_section


# Node unique: Générer l'esquisse complète du cours
# The LLM in param is just for developpement purposes
def generate_course_outline_node(
        state: CourseOutlineGraphState, 
        llm_instance: ChatGoogleGenerativeAI
    ) -> CourseOutlineGraphState:
    """
    Node to generate the complete course outline including title, introduction, and main sections.
    
    """

    metadata = state["metadata"]
    
    # La chaîne combinée
    # Utilise le prompt unifié et le modèle CourseOutline comme sortie structurée
    combined_chain = ChatPromptTemplate.from_template(PROMPT_GENERATE_COURSE_OUTLINE) | llm_instance.with_structured_output(Course_section)
    
    response: Course_section = combined_chain.invoke({
        "title": metadata.title,
        "domains": metadata.domains,
        "categories": metadata.categories,
        "topics": metadata.topics,
        "objectives": metadata.objectives,
        "expectations": metadata.expectations,
        "prerequisites": metadata.prerequisites,
        "desired_level": metadata.desired_level
    })
    
    return {"course_section": response}

# The LLM in param is just for production purposes
def get_course_outline_graph(llm_instance: ChatGoogleGenerativeAI):
    """
    Create and return the graph for generating the course outline.
    """
    workflow = StateGraph(CourseOutlineGraphState)
    # Un seul nœud suffit maintenant
    workflow.add_node("generate_outline", lambda state: generate_course_outline_node(state, llm_instance = llm_instance))
    
    workflow.set_entry_point("generate_outline")
    workflow.add_edge("generate_outline", END) # Le nœud mène directement à la fin
    
    return workflow.compile()

# API Router pour la première API
course_outline_router = APIRouter() # Renommé pour correspondre à la fonction de sortie

@course_outline_router.post("/course_outline", response_model=Course_section)
async def get_course_outline(
    metadata: CourseInput,
    x_gemini_api_key: Optional[str] = Header(None, alias="X-Gemini-Api-Key")    
):
    """
    Endpoint for generating the course outline, including title, introduction, and main sections.
    """
    api_key_to_use = x_gemini_api_key if x_gemini_api_key else os.getenv("GEMINI_API_KEY")

    if not api_key_to_use:
        raise HTTPException(status_code=400, detail="Gemini API key is not provided. Please provide it via 'X-Gemini-Api-Key' header or set GEMINI_API_KEY in .env.")
    
    llm_to_use = ChatGoogleGenerativeAI(
        model=os.getenv("MODEL"), # Utilisez un modèle robuste pour la génération de structure
        google_api_key=api_key_to_use,
    )
    
    graph = get_course_outline_graph(llm_instance = llm_to_use)
    result = graph.invoke({
        "metadata": metadata,
        "course_section": None # Initialiser l'état avec None pour la sortie
    })
    
    # Le résultat contient directement l'objet CourseOutline
    return result["course_section"]


# --- API 2: Génération des sous-sections pour une section donnée (inchangée) ---

# Chaîne pour générer les sous-sections
def generate_subsections_chain(llm_instance: ChatGoogleGenerativeAI = None):
    prompt = ChatPromptTemplate.from_template(PROMPT_GENERATE_SUBSECTIONS)
    return prompt | llm_instance.with_structured_output(SubsectionOutput) # Utilisation de llm_gemini pour la cohérence

# API Router pour la deuxième API
course_subsections_router = APIRouter()

@course_subsections_router.post("/generate_subsections", response_model=SubsectionOutput)
async def generate_subsections_for_section(
    input_data: SubsectionGenerationInput,
    x_gemini_api_key: Optional[str] = Header(None, alias="X-Gemini-Api-Key")
):
    """
    Endpoint for generating subsections for a specific section.
    """
    api_key_to_use = x_gemini_api_key if x_gemini_api_key else os.getenv("GEMINI_API_KEY")

    if not api_key_to_use:
        raise HTTPException(status_code=400, detail="Gemini API key is not provided. Please provide it via 'X-Gemini-Api-Key' header or set GEMINI_API_KEY in .env.")
    
    llm_to_use = ChatGoogleGenerativeAI(
        model=os.getenv("MODEL"),
        google_api_key=api_key_to_use,
    )

    sub_chain = generate_subsections_chain(llm_instance=llm_to_use)
    
    response: SubsectionOutput = sub_chain.invoke({
        "course_title": input_data.course_title,
        "course_introduction": input_data.course_introduction,
        "section_title": input_data.section_title,
        "section_description": input_data.section_description
    })
    
    return response