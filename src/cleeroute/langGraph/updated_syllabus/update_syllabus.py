import os
import json
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from src.cleeroute.models import (CompleteCourse, ModificationInstruction, InstructionSet
)
from src.cleeroute.langGraph.updated_syllabus.updated_nodes import call_gemini_for_parsing, human_intervention_node, apply_modification_to_course, reflect_and_summarize,check_intervention_needed ,CourseState,generate_gemini_structured_output_response
from langchain_google_genai import ChatGoogleGenerativeAI
from src.cleeroute.langGraph.updated_syllabus.prompts import SPECIFIC_INSTRUCTIONS_PROMPT
from typing import Literal, Optional
from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import JSONResponse
from uuid import uuid4
import threading
import traceback
from dotenv import load_dotenv
load_dotenv()

def graph_buider(llm_instance: ChatGoogleGenerativeAI):
    # --- 5. Construction du Graphe Langgraph ---
    builder = StateGraph(CourseState)

    builder.add_node("parse_request", lambda state: call_gemini_for_parsing(state, llm_instance=llm_instance))
    builder.add_node("human_intervention_wait", human_intervention_node)
    builder.add_node("apply_changes", apply_modification_to_course)
    builder.add_node("summarize_changes", lambda state: reflect_and_summarize(state, llm_instance=llm_instance))

    builder.set_entry_point("parse_request")

    builder.add_conditional_edges(
        "parse_request",
        check_intervention_needed,
        {
            "human_intervention": "human_intervention_wait",
            "apply_changes": "apply_changes"
        }
    )

    # Ajout de l'arête pour la reprise après intervention humaine
    # Le endpoint /intervene va mettre à jour l'état, puis le graphe
    # reprendra à partir d'ici et suivra cette arête.
    builder.add_edge("human_intervention_wait", "apply_changes")

    builder.add_edge("apply_changes", "summarize_changes")
    builder.add_edge("summarize_changes", END)


    return builder

llm_to_use = ChatGoogleGenerativeAI(
        model=os.getenv("MODEL_2"),
        google_api_key= os.getenv("GEMINI_API_KEY"),
)

memory = MemorySaver()
graph = graph_buider(llm_instance=llm_to_use).compile(checkpointer=memory)

course_modification_router = APIRouter()
course_human_intervention_router = APIRouter()


# class UserRequest(BaseModel):
#     user_input: str# Modèles de requête pour les API

class ModifyCourseRequest(BaseModel):
    course: CompleteCourse
    user_input: str

class InterveneCourseRequest(BaseModel):
    correction_input: str

# Modèle de réponse pour les API de modification/intervention
# Modèles de requête pour les API
class ModifyCourseRequest(BaseModel):
    course: CompleteCourse
    user_input: str

class InterveneCourseRequest(BaseModel):
    correction_input: str

# Modèle de réponse pour les API de modification/intervention
class ModificationResponse(BaseModel):
    status: Literal["completed", "pending_human_intervention"]
    run_id: Optional[str] = None
    message: str
    course: Optional[CompleteCourse] = None # Le cours modifié, si l'opération est 'completed'

    
@course_modification_router.post("/course/modify", response_model=ModificationResponse, summary="Launch a course modification")
async def modify_course(
    request: ModifyCourseRequest,
    x_gemini_api_key: Optional[str] = Header(None, alias="X-Gemini-Api-Key")
):
    thread_id = str(uuid4())
    print(f"Démarrage d'une nouvelle exécution de modification avec l'ID: {thread_id}")

    initial_state = CourseState(
        course=request.course,
        user_input=request.user_input,
        requires_human_intervention=False, # Initialement supposé pas d'intervention
        current_run_id=thread_id,
        response_message="Traitement de votre requête..."
    )

    try:
        config = {"configurable": {"thread_id": thread_id}}
        
        interrupted_at_human_intervention = False
        # Le stream s'interrompra si human_intervention_wait est atteint.
        # Si non, il continuera jusqu'à END.
        api_key_to_use = x_gemini_api_key if x_gemini_api_key else os.getenv("GEMINI_API_KEY")

        if not api_key_to_use:
            raise HTTPException(status_code=400, detail="Gemini API key is not provided. Please provide it via 'X-Gemini-Api-Key' header or set GEMINI_API_KEY in .env.")
        
        llm_to_use = ChatGoogleGenerativeAI(
            model=os.getenv("MODEL_2"),
            google_api_key=api_key_to_use,
        )

        for s in graph.stream(initial_state, config=config, interrupt_after=["human_intervention_wait"]):
            if "human_intervention_wait" in s:
                interrupted_at_human_intervention = True
                print(f"Exécution {thread_id} interrompue au nœud human_intervention_wait.")
                # Retourner immédiatement la réponse d'attente
                return ModificationResponse(
                    status="pending_human_intervention",
                    run_id=thread_id, # **IMPORTANT : Toujours renvoyer le thread_id**
                    message=s["human_intervention_wait"]["response_message"]
                )
        
        # Si le stream s'est terminé sans interruption explicite par human_intervention_wait
        # Nous devons récupérer l'état final et vérifier `requires_human_intervention`
        if not interrupted_at_human_intervention:
            final_retrieved_state = graph.get_state(config)
            if final_retrieved_state and final_retrieved_state.values:
                final_course_state: CourseState = final_retrieved_state.values
                
                if final_course_state.get("requires_human_intervention"):
                    # L'opération a échoué et nécessite une intervention, même si le stream est allé jusqu'au bout
                    print(f"Exécution {thread_id} terminée mais nécessite une intervention (état final: {final_course_state.get('response_message')}).")
                    return ModificationResponse(
                        status="pending_human_intervention",
                        run_id=thread_id, # **IMPORTANT : Toujours renvoyer le thread_id**
                        message=final_course_state.get("response_message", "Intervention humaine requise suite à une erreur non bloquante.")
                    )
                else:
                    # Opération réussie et complétée
                    print(f"Exécution {thread_id} terminée avec succès (état récupéré du checkpointer).")
                    return ModificationResponse(
                        status="completed",
                        course=final_course_state["course"],
                        message=final_course_state["response_message"]
                    )
            else:
                raise Exception("Le flux Langgraph s'est terminé mais l'état final n'a pas pu être récupéré du checkpointer.")
        # Cette ligne est un fallback si la logique d'interruption n'est pas cohérente
        raise Exception("Erreur logique inattendue dans le traitement du stream Langgraph.")

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur lors de la modification: {e}")


@course_human_intervention_router.post("/course/intervene/{run_id}", response_model=ModificationResponse, summary="provide more information for a course modification using the run_id from the first endpoint")
async def intervene_course(
    run_id: str, 
    correction_request: InterveneCourseRequest,
    x_gemini_api_key: Optional[str] = Header(None, alias="X-Gemini-Api-Key")
):
    print(f"Reprise de l'exécution {run_id} avec la correction humaine: {correction_request.correction_input}")


    api_key_to_use = x_gemini_api_key if x_gemini_api_key else os.getenv("GEMINI_API_KEY")

    if not api_key_to_use:
        raise HTTPException(status_code=400, detail="Gemini API key is not provided. Please provide it via 'X-Gemini-Api-Key' header or set GEMINI_API_KEY in .env.")
    
    llm_to_use = ChatGoogleGenerativeAI(
        model=os.getenv("MODEL_2"),
        google_api_key=api_key_to_use,
    )

    try:
        config = {"configurable": {"thread_id": run_id}}
        
        # 1. Récupérer l'état actuel en pause
        current_graph_state_from_checkpointer = graph.get_state(config)
        if not current_graph_state_from_checkpointer:
            raise HTTPException(status_code=404, detail=f"ID d'exécution '{run_id}' introuvable ou déjà terminé.")
        
        state_values: CourseState = current_graph_state_from_checkpointer.values
        
        # 2. Construire le prompt pour re-parser en un `InstructionSet`
        reparse_prompt = f"""
                The user's original request was ambiguous. A human has provided a correction.
                **Your task is to IGNORE the original request and the previous error.**
                Base your response ENTIRELY on the "Human clarification" provided below.

                Decompose the human's clarification into a complete and valid `InstructionSet` JSON object.
                
                Human clarification: "{correction_request.correction_input}"

                {SPECIFIC_INSTRUCTIONS_PROMPT}

                --- Course Context ---
                ```json
                {state_values["course"].model_dump_json(indent=2)}
                ```

                Generate the `InstructionSet`. Set "requires_human_intervention": false.
        """

        # 3. Générer le set d'instructions corrigé
        human_corrected_instructions = generate_gemini_structured_output_response(reparse_prompt, InstructionSet, llm_to_use)

        if not isinstance(human_corrected_instructions, InstructionSet):
            raise ValueError("L'IA n'a pas pu produire un set d'instructions valide après la correction humaine.")

        # 4. Gérer le cas où la clarification de l'humain n'est TOUJOURS pas suffisante
        if human_corrected_instructions.requires_human_intervention:
            print(f"La correction humaine n'était pas suffisante pour l'exécution {run_id}. Nouvelle demande de clarification.")
            graph.update_state(
                config,
                {"error_message": human_corrected_instructions.error_message, "response_message": human_corrected_instructions.error_message}
            )
            return ModificationResponse(
                status="pending_human_intervention",
                run_id=run_id,
                message=human_corrected_instructions.error_message
            )

        # 5. Mettre à jour l'état du graphe avec les instructions corrigées pour la reprise
        updates_for_resume = {
        "instructions_to_apply": human_corrected_instructions,
        "requires_human_intervention": False,
        "error_message": None,
        }

        graph.update_state(config, updates_for_resume)

        # 6. Reprendre le graphe et le laisser s'exécuter jusqu'à la fin
        print("Reprise du stream du graphe...")
        for _ in graph.stream(None, config=config):
            pass # On consomme le stream pour qu'il s'exécute entièrement
        print("Stream du graphe terminé.")

        # 7. Récupérer l'état final et définitif depuis le checkpointer
        final_state_snapshot = graph.get_state(config)
        if not final_state_snapshot:
             raise Exception("Impossible de récupérer l'état final après l'exécution de la reprise.")
        
        final_state: CourseState = final_state_snapshot.values

        # 8. Construire la réponse finale basée sur l'état terminal du graphe
        if final_state.get("requires_human_intervention"):
            # L'opération a échoué pendant le noeud `apply_changes`
            print(f"L'exécution {run_id} a de nouveau échoué après intervention.")
            return ModificationResponse(
                status="pending_human_intervention",
                run_id=run_id,
                message=final_state.get("error_message", "Une erreur est survenue lors de l'application des changements.")
            )
        else:
            # L'opération a réussi et s'est terminée
            print(f"L'exécution {run_id} s'est terminée avec succès après intervention.")
            return ModificationResponse(
                status="completed",
                course=final_state["course"],
                message=final_state["response_message"]
            )

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erreur interne du serveur lors de l'intervention humaine: {str(e)}")