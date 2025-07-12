import os
from typing import List,AsyncIterator, Optional
import time

from fastapi import HTTPException, Query, FastAPI, status
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse
from fastapi import APIRouter

from langchain_groq import ChatGroq

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from dotenv import load_dotenv
from src.cleeroute.langGraph.prompt_tamplate import CONTEXTE
from src.cleeroute.models import Course_meta_datas, Course_meta_datas_input
from src.cleeroute.langGraph.prompt_tamplate import SUMMARY_PROMPT, DETAILS_PROMPT

load_dotenv()


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


# Initialisation de l'LLM
google_api_key = os.getenv("GEMINI_API_KEY")
if not google_api_key:
    raise ValueError("GEMINI_API_KEY environment variable is not set. Please set it to your Google API key.")

llm = ChatGoogleGenerativeAI(
    model= os.getenv("MODEL_2"),
    temperature=0.1,
    google_api_key=google_api_key,
)


# Chaîne LangChain pour la génération du résumé
summary_prompt_template = ChatPromptTemplate.from_messages(SUMMARY_PROMPT)
summary_llm_chain = summary_prompt_template | llm.with_structured_output(Course_summary)

# Chaîne LangChain pour la génération des détails
details_prompt_template = ChatPromptTemplate.from_messages(DETAILS_PROMPT)
details_llm_chain = details_prompt_template | llm.with_structured_output(Course_details)


# --- DÉFINITION DE L'APPLICATION FASTAPI ---
router_metadata_1 = APIRouter()
router_metadata_2 = APIRouter()


app = FastAPI(
    title="Course Proposal Generator API",
    description="API for generating structured course proposals with separate endpoints, each taking only user_prompt as direct input.",
    version="1.0.0",
)

# Modèle de requête commun pour les deux endpoints (seulement user_prompt)
class SinglePromptRequest(BaseModel):
    user_prompt: str = Field(..., example="Learning langgraph and langchain for AI applications in education.")

contexte_data = CONTEXTE

@router_metadata_1.post("/first-generate", response_model=Course_summary, summary="Generate Course Summary")
async def generate_summary_endpoint(request: SinglePromptRequest):
    """
    This endpoint generates the first part of meta data course based on a user prompt.
    """
    print(f"[{time.time():.2f}] Requête reçue pour /generate-summary: prompt='{request.user_prompt}'")
    
    start_time = time.perf_counter()
    try:
        # Utilise le contexte global par défaut, car 'additional_context' n'est plus une entrée.
        context_for_llm = contexte_data 
        
        summary_proposal = summary_llm_chain.invoke({
            "prompt": request.user_prompt,
            "context": context_for_llm
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
async def generate_details_endpoint(request: SinglePromptRequest):
    """
    This endpoint generates the second part of meta data course based on a user prompt.

    """
    print(f"[{time.time():.2f}] Requête reçue pour /generate-details: prompt='{request.user_prompt}'")

    # --- ÉTAPE INTERNE: RE-GÉNÉRATION DU RÉSUMÉ POUR COHÉRENCE ---
    print(f"[{time.time():.2f}] [Interne] Re-génération du résumé pour les détails...")
    internal_summary_start_time = time.perf_counter()
    summary_proposal: Optional[Course_summary] = None
    try:
        # Utilise le contexte global par défaut
        context_for_llm = contexte_data
        summary_proposal = summary_llm_chain.invoke({
            "prompt": request.user_prompt,
            "context": context_for_llm
        })
        internal_summary_end_time = time.perf_counter()
        internal_summary_gen_time = internal_summary_end_time - internal_summary_start_time
        print(f"[{time.time():.2f}] [Interne] Résumé re-généré en {internal_summary_gen_time:.2f} secondes.")
    except Exception as e:
        print(f"[{time.time():.2f}] [Interne] Erreur lors de la re-génération du résumé: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to internally re-generate summary for details: {str(e)}"
        )
    
    if not summary_proposal:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal summary generation failed."
        )
    # --- FIN ÉTAPE INTERNE ---

    start_time = time.perf_counter() # Temps pour la génération des détails elle-même
    try:        
        # Utilise le contexte global par défaut

        details_proposal = details_llm_chain.invoke({
            "prompt": request.user_prompt,
            "context": request.user_prompt
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






# from langchain_google_genai import ChatGoogleGenerativeAI
# from langchain_core.prompts import ChatPromptTemplate
# from pydantic import Field
# from typing import Dict, Any, TypedDict
# from fastapi.responses import StreamingResponse

# from langgraph.graph import StateGraph, END
# from fastapi import APIRouter

# import src.cleeroute.langGraph.prompt_tamplate as prompts
# from src.cleeroute.models import Course_meta_datas, Course_meta_datas_input
# from langchain_groq import ChatGroq
# import os
# import json
# from dotenv import load_dotenv
# load_dotenv()

# # --- Définitions (inchangées) ---
# llm = ChatGoogleGenerativeAI(model=os.getenv("MODEL"), google_api_key=os.getenv("GEMINI_API_KEY"))

# # llm = ChatGroq(model="llama-3.1-8b-instant", api_key=os.getenv("GROQ_API_KEY"))

# class GraphState(TypedDict):
#     initial_request: Course_meta_datas_input
#     course_meta_data: Dict 

# def meta_data_gen_agent():
#     structured_llm = llm.with_structured_output(Course_meta_datas)
#     prompt = ChatPromptTemplate.from_template(prompts.COURSE_META_DATA_PROMPT)
#     return prompt | structured_llm

# def meta_data_gen_node(state: GraphState) -> Dict[str, Any]:
#     print("--- Execution ---")
#     agent = meta_data_gen_agent()
#     result: Course_meta_datas = agent.invoke(state["initial_request"].model_dump())
#     print(f"--- INFO: Meta-data generated for '{result.title}' course ---")
#     return {"course_meta_data": result.model_dump()}

# def get_meta_data_graph():
#     workflow = StateGraph(GraphState)
#     workflow.add_node("meta_data_gen", meta_data_gen_node)
#     workflow.set_entry_point("meta_data_gen")
#     workflow.add_edge("meta_data_gen", END)
#     return workflow.compile()

# router_metadata = APIRouter()

# @router_metadata.post("/generate-stream", response_model=Course_meta_datas)
# async def generate_metadata_stream(request: Course_meta_datas_input):
#     """
#     Takes a simple user request and STREAMS the result of the metadata generation.
#     """
#     graph = get_meta_data_graph()
    
#     async def stream_generator():
#         inputs = {"initial_request": request}
        
#         async for output in graph.astream(inputs):

#             if "meta_data_gen" in output:
#                 response_chunk = {
#                     "event": "metadata_ready",
#                     "data": output["meta_data_gen"]["course_meta_data"]
#                 }
                
#                 yield f"data: {json.dumps(response_chunk)}\n\n"
        
#         yield f"data: {json.dumps({'event': 'end'})}\n\n"

#     return StreamingResponse(stream_generator(), media_type="text/event-stream")