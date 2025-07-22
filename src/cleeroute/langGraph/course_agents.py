from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Optional
from fastapi import APIRouter, FastAPI 
import os
from dotenv import load_dotenv

# Importer les modèles mis à jour
from src.cleeroute.langGraph.models import (
    CourseInput,
    CourseOutline,
    SubsectionGenerationInput,
    Subsection,
)

# Importer le prompt unifié
from src.cleeroute.langGraph.streaming_course_structure.prompts_course import (
    PROMPT_GENERATE_SECTION, # Utilisez le nouveau prompt
    PROMPT_GENERATE_SUBSECTIONS
)

load_dotenv()

# Configuration LLM
llm_gemini = ChatGoogleGenerativeAI( # Renommé pour plus de clarté
    model=os.getenv("MODEL_2"), 
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0.2, # Un peu plus de créativité pour les descriptions
)

# --- API 1: Génération de l'esquisse du cours (Header + Sections Skeletons) ---
class CourseOutlineGraphState(TypedDict):
    metadata: CourseInput
    course_outline: Optional[CourseOutline]


# Node unique: Générer l'esquisse complète du cours
def generate_course_outline_node(state: CourseOutlineGraphState) -> CourseOutlineGraphState:
    """
    Génère le titre, l'introduction et la liste des sections principales du cours en une seule étape.
    """
    metadata = state["metadata"]
    
    # La chaîne combinée
    # Utilise le prompt unifié et le modèle CourseOutline comme sortie structurée
    combined_chain = ChatPromptTemplate.from_template(PROMPT_GENERATE_SECTION) | llm_gemini.with_structured_output(CourseOutline)
    
    response: CourseOutline = combined_chain.invoke({
        "title": metadata.title,
        "domains": metadata.domains,
        "categories": metadata.categories,
        "topics": metadata.topics,
        "objectives": metadata.objectives,
        "expectations": metadata.expectations,
        "prerequisites": metadata.prerequisites,
        "desired_level": metadata.desired_level
    })
    
    # Pour le débogage, imprimez la sortie du LLM    
    return {"course_outline": response}


def get_course_outline_graph():
    """
    Crée un graphe d'état pour générer l'esquisse complète du cours.
    """
    workflow = StateGraph(CourseOutlineGraphState)
    # Un seul nœud suffit maintenant
    workflow.add_node("generate_outline", generate_course_outline_node)
    
    workflow.set_entry_point("generate_outline")
    workflow.add_edge("generate_outline", END) # Le nœud mène directement à la fin
    
    return workflow.compile()

# API Router pour la première API
course_sections_router = APIRouter() # Renommé pour correspondre à la fonction de sortie

@course_sections_router.post("/generate_course_sections", response_model=CourseOutline)
async def get_course_outline(metadata: CourseInput):
    """
    Endpoint pour générer l'esquisse complète du cours (en-tête et sections principales).
    """
    graph = get_course_outline_graph()
    result = graph.invoke({
        "metadata": metadata,
        "course_outline": None # Initialiser l'état avec None pour la sortie
    })
    
    # Le résultat contient directement l'objet CourseOutline
    return result["course_outline"]


# --- API 2: Génération des sous-sections pour une section donnée (inchangée) ---

# Chaîne pour générer les sous-sections
def generate_subsections_chain():
    prompt = ChatPromptTemplate.from_template(PROMPT_GENERATE_SUBSECTIONS)
    return prompt | llm_gemini.with_structured_output(List[Subsection]) # Utilisation de llm_gemini pour la cohérence

# API Router pour la deuxième API
course_subsections_router = APIRouter()

@course_subsections_router.post("/generate_subsections_for_section", response_model=List[Subsection])
async def generate_subsections_for_section(input_data: SubsectionGenerationInput):
    """
    Endpoint pour générer les sous-sections d'une section spécifique du cours.
    Nécessite le contexte du cours et les détails de la section.
    """
    print("--- Génération des sous-sections pour une section ---")
    sub_chain = generate_subsections_chain()
    
    response: List[Subsection] = sub_chain.invoke({
        "course_title": input_data.course_title,
        "course_objectives": input_data.course_objectives,
        "section_title": input_data.section_title,
        "section_description": input_data.section_description
    })
    
    return response