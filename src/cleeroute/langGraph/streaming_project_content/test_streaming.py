# main.py
import os
import json
from dotenv import load_dotenv
from typing import TypedDict, Dict, Any, Optional
from fastapi import FastAPI, APIRouter
from fastapi.responses import StreamingResponse

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

# Importe tes modèles et prompts
from src.cleeroute.langGraph.streaming_project_content.test_streaming_models import RequiredGenProjInput, Project, TitleDesc, ObjectivesPrereqs, Steps, Evaluation
from src.cleeroute.langGraph.streaming_project_content.test_streaming_prompt import (
    PROMPT_GENERATE_TITLE_DESC,
    PROMPT_GENERATE_OBJECTIVES,
    PROMPT_GENERATE_STEPS,
    PROMPT_GENERATE_EVALUATION
)

load_dotenv()

# --- Configuration du LLM ---
llm = ChatGoogleGenerativeAI(
    model=os.getenv("MODEL_2", "gemini-1.5-flash"), # Assure un fallback
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0.7 # Un peu de créativité pour le Game Master
)

# --- Définition de l'état du Graphe ---
class GraphState(TypedDict):
    requiredInput: RequiredGenProjInput
    partial_project: Dict[str, Any]
    project: Optional[Project]

# --- Définition des Noeuds du Graphe ---

def generate_title_desc_node(state: GraphState):
    print("---Génération Titre & Description---")
    prompt = ChatPromptTemplate.from_template(PROMPT_GENERATE_TITLE_DESC)
    chain = prompt | llm.with_structured_output(TitleDesc)
    
    response = chain.invoke(state["requiredInput"].model_dump())
    return {"partial_project": response.model_dump()}

def generate_objectives_node(state: GraphState):
    print("---Génération Objectifs & Prérequis---")
    prompt = ChatPromptTemplate.from_template(PROMPT_GENERATE_OBJECTIVES)
    chain = prompt | llm.with_structured_output(ObjectivesPrereqs)
    
    context = {**state["requiredInput"].model_dump(), **state["partial_project"]}
    response = chain.invoke(context)
    
    updated_project = {**state["partial_project"], **response.model_dump()}
    return {"partial_project": updated_project}

def generate_steps_node(state: GraphState):
    print("---Génération des Étapes---")
    prompt = ChatPromptTemplate.from_template(PROMPT_GENERATE_STEPS)
    chain = prompt | llm.with_structured_output(Steps)
    
    context = {**state["requiredInput"].model_dump(), **state["partial_project"]}
    response = chain.invoke(context)
    
    updated_project = {**state["partial_project"], **response.model_dump()}
    return {"partial_project": updated_project}

def generate_evaluation_node(state: GraphState):
    print("---Génération Évaluation---")
    prompt = ChatPromptTemplate.from_template(PROMPT_GENERATE_EVALUATION)
    chain = prompt | llm.with_structured_output(Evaluation)
    
    context = {**state["partial_project"]}
    response = chain.invoke(context)
    
    updated_project = {**state["partial_project"], **response.model_dump()}
    return {"partial_project": updated_project}

def finalize_project_node(state: GraphState):
    """Ce noeud final valide le dictionnaire complet et le convertit en objet Pydantic."""
    print("---Finalisation du Projet---")
    final_project = Project.model_validate(state['partial_project'])
    return {"project": final_project}

# --- Construction du Graphe ---
def get_streaming_project_graph():
    workflow = StateGraph(GraphState)
    
    # Ajout des noeuds
    workflow.add_node("gen_title_desc", generate_title_desc_node)
    workflow.add_node("gen_objectives", generate_objectives_node)
    workflow.add_node("gen_steps", generate_steps_node)
    workflow.add_node("gen_evaluation", generate_evaluation_node)
    workflow.add_node("finalize", finalize_project_node)
    
    # Définition du flux
    workflow.set_entry_point("gen_title_desc")
    workflow.add_edge("gen_title_desc", "gen_objectives")
    workflow.add_edge("gen_objectives", "gen_steps")
    workflow.add_edge("gen_steps", "gen_evaluation")
    workflow.add_edge("gen_evaluation", "finalize")
    workflow.add_edge("finalize", END)
    
    return workflow.compile()

# --- API Router ---
app = FastAPI(title="API de Génération de Projets Pédagogiques")
project_content_router_stream = APIRouter()
graph = get_streaming_project_graph()

@project_content_router_stream.post("/project_content/stream")
async def course_structure_stream(requiredInput: RequiredGenProjInput):
    """
    Endpoint for streaming project content generation.
    This endpoint uses Server-Sent Events (SSE) to stream the project content generation process.
    """
    async def event_stream():
        # astream_events nous donne un flux d'événements du graphe
        async for event in graph.astream_events(
            { "requiredInput": requiredInput, "partial_project": {} }, 
            version="v1"
        ):
            kind = event["event"]
            # Nous envoyons une mise à jour au frontend à la fin de chaque noeud
            if kind == "on_chain_end":
                node_name = event["name"]
                # On s'assure que le noeud a produit des données
                if "partial_project" in event["data"]["output"]:
                    print(f"Streaming de la sortie du noeud: {node_name}")
                    data_to_send = event["data"]["output"]["partial_project"]
                    # Format Server-Sent Events (SSE)
                    yield f"data: {json.dumps(data_to_send)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")