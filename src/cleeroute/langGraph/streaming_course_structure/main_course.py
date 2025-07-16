# main_course.py
import os
import json
from dotenv import load_dotenv
from typing import TypedDict, Dict, Any, Optional, List

from fastapi import FastAPI, APIRouter
from fastapi.responses import StreamingResponse

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

# Importe tes modèles et prompts
from src.cleeroute.langGraph.streaming_course_structure.models_course import CourseInput, Course, CourseHeader, SectionSkeletonList, SubsectionsList
from src.cleeroute.langGraph.streaming_course_structure.prompts_course import (
    PROMPT_GENERATE_COURSE_HEADER,
    PROMPT_GENERATE_SECTION_SKELETONS,
    PROMPT_GENERATE_SUBSECTIONS,
)

load_dotenv()

# --- Configuration du LLM ---
llm = ChatGoogleGenerativeAI(
    model=os.getenv("MODEL_2"),
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0.3 # Plus factuel pour la structure
)

# --- Définition de l'état du Graphe ---
class GraphState(TypedDict):
    metadata: CourseInput
    partial_course: Dict[str, Any]
    section_index: int
    course: Optional[Course]

# --- Définition des Noeuds du Graphe ---

def generate_header_node(state: GraphState):
    print("--- Couse title generation ---")
    prompt = ChatPromptTemplate.from_template(PROMPT_GENERATE_COURSE_HEADER)
    chain = prompt | llm.with_structured_output(CourseHeader)
    response = chain.invoke(state["metadata"].model_dump())
    return {"partial_course": response.model_dump()}

def generate_sections_node(state: GraphState):
    print("--- Squelleton's sections generation ---")
    prompt = ChatPromptTemplate.from_template(PROMPT_GENERATE_SECTION_SKELETONS)
    chain = prompt | llm.with_structured_output(SectionSkeletonList)
    response = chain.invoke(state["metadata"].model_dump())
    
    # Fusionne avec l'état existant et initialise l'index pour la boucle
    updated_course = {**state["partial_course"], "sections": [s.model_dump() for s in response.sections]}
    return {"partial_course": updated_course, "section_index": 0}

def generate_subsections_node(state: GraphState):
    """
        This node generates subsections for a specific section in the course using loop strategie.
    """
    index = state["section_index"]
    section_to_process = state["partial_course"]["sections"][index]
    print(f"--- 3.{index+1} Génération des sous-sections pour: '{section_to_process['title']}' ---")
    
    prompt = ChatPromptTemplate.from_template(PROMPT_GENERATE_SUBSECTIONS)
    chain = prompt | llm.with_structured_output(SubsectionsList)
    
    context = {
        "course_title": state["partial_course"]["title"],
        "course_objectives": state["metadata"].objectives,
        "section_title": section_to_process["title"],
        "section_description": section_to_process["description"],
    }
    response = chain.invoke(context)
    
    # update the current course with the new subsections
    current_course = state["partial_course"]
    current_course["sections"][index]["subsections"] = [s.model_dump() for s in response.subsections]
    
    # Increment the index for the next iteration
    return {"partial_course": current_course, "section_index": index + 1}

def finalize_course_node(state: GraphState):
    """Valide l'objet complet à la toute fin."""
    print("--- 4. Finalisation de la structure du cours ---")
    final_course = Course.model_validate(state['partial_course'])
    return {"course": final_course}

# --- Defining conditional edges ---

def should_continue(state: GraphState):
    """Décide s'il faut continuer la boucle de génération des sous-sections."""
    if state["section_index"] < len(state["partial_course"]["sections"]):
        return "continue"
    else:
        return "end"

# --- Construction du Graphe ---
def get_course_structure_graph():
    workflow = StateGraph(GraphState)
    
    workflow.add_node("gen_header", generate_header_node)
    workflow.add_node("gen_sections", generate_sections_node)
    workflow.add_node("gen_subsections", generate_subsections_node)
    workflow.add_node("finalize", finalize_course_node)
    
    workflow.set_entry_point("gen_header")
    workflow.add_edge("gen_header", "gen_sections")
    workflow.add_edge("gen_sections", "gen_subsections")
    
    # La boucle est ici !
    workflow.add_conditional_edges(
        "gen_subsections",
        should_continue,
        {
            "continue": "gen_subsections", # Boucle sur lui-même
            "end": "finalize"              # Sort de la boucle
        }
    )
    workflow.add_edge("finalize", END)
    
    return workflow.compile()

# --- API Router ---
app = FastAPI(title="API de Génération de Cours")
course_structure_router_stream = APIRouter()
graph = get_course_structure_graph()

@course_structure_router_stream.post("/course_structure/stream")
async def course_structure_stream(metadata: CourseInput):
    """
    Endpoint for streaming course structure generation.
    This endpoint uses Server-Sent Events (SSE) to stream the course structure generation process.
    """
    async def event_stream():
        config = {"recursion_limit": 50}
        async for event in graph.astream_events(
            {"metadata": metadata}, 
            config=config,
            version="v1"
        ):
            kind = event["event"]
            if kind == "on_chain_end":
                node_name = event["name"]
                if "partial_course" in event["data"]["output"]:
                    print(f"Streaming de la sortie du noeud: {node_name}")
                    data_to_send = event["data"]["output"]["partial_course"]
                    yield f"data: {json.dumps(data_to_send)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")