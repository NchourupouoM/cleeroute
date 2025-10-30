# In app/routers/journeys.py

import uuid
from typing import Dict, Optional
import os
from fastapi import APIRouter, HTTPException, Body, Depends, BackgroundTasks, Header
from langgraph.pregel import Pregel

from .models import (
    SyllabusRequest, 
    SyllabusOptions, 
    StartJourneyResponse, 
    ContinueJourneyRequest, 
    JourneyStatusResponse
)

from .state import GraphState, PydanticSerializer
from .dependencies import get_conversation_graph, get_syllabus_graph  # We will create this dependency injector

# Create a new router instance
# This allows us to group all related endpoints under a common prefix and tag
syllabus_router = APIRouter()

@syllabus_router.post(
    "/gen_syllabus", 
    response_model=StartJourneyResponse,
    summary="Start a new learning journey",
    status_code=201  # Use 201 Created for new resource creation
)
async def start_learning_journey(
    request: SyllabusRequest,
    x_youtube_api_key: Optional[str] = Header(None, alias="X-Youtube-Api-Key"),
    app_graph: Pregel = Depends(get_conversation_graph)  # Dependency injection for the graph
):
    """
    Starts a new syllabus generation journey. This initializes the stateful graph
    and returns the first question for the human-in-the-loop process.
    """
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    os.environ['YOUTUBE_API_KEY'] = x_youtube_api_key if x_youtube_api_key else os.getenv("YOUTUBE_API_KEY")

    user_links_str = []
    if request.user_input_links:
        # On convertit la liste de HttpUrl en une liste de chaînes de caractères
        user_links_str = [str(link) for link in request.user_input_links]

    initial_state = GraphState(
        user_input_text=request.user_input_text,
        user_input_links=user_links_str,
        metadata_str=PydanticSerializer.dumps(request.metadata)
    )

    # Stream the graph. It will run until the first interruption (the first question).
    last_state = None
    async for state_update in app_graph.astream(initial_state, config, stream_mode="values"):
        last_state = state_update

    if last_state and last_state.get('current_question'):
        return StartJourneyResponse(
            thread_id=thread_id,
            next_question=last_state['current_question']
        )
    else:
        # Ce cas se produit si le graphe se termine immédiatement sans poser de question.
        # C'est un état d'erreur ou un cas non prévu.
        raise HTTPException(
            status_code=500, 
            detail="Graph finished unexpectedly without asking a question."
        )

@syllabus_router.post(
    "/gen_syllabus/{thread_id}/continue", 
    response_model=JourneyStatusResponse,
    summary="Continue an existing journey"
)
async def continue_learning_journey(
    thread_id: str,
    request: ContinueJourneyRequest,
    app_graph: Pregel = Depends(get_conversation_graph)
):
    config = {"configurable": {"thread_id": thread_id}}

    current_snapshot = await app_graph.aget_state(config)

    if not current_snapshot:
        raise HTTPException(status_code=404, detail="Journey not found.")
    
    current_values = current_snapshot.values
    current_history = current_values.get('conversation_history', [])

    # 2. PRÉPARER la mise à jour
    # updates_to_save = {}
    # if current_history:
    #     # On prend le dernier tour (qui contient la question de l'IA)
    #     last_human, last_ai = current_history[-1]
        
    #     # On crée une NOUVELLE liste d'historique avec le dernier tour mis à jour.
    #     # On prend tout sauf le dernier élément, et on ajoute le dernier élément corrigé.
    #     updated_history = current_history[:-1] + [(request.user_answer, last_ai)]
    #     updates_to_save["conversation_history"] = updated_history
    
    update_payload = {"conversation_history": [(request.user_answer, "")]}

    await app_graph.aupdate_state(config, update_payload)

    # 4. Resume the graph execution
    # Étape 2: Reprendre le graphe SANS nouvelle entrée.
    # CHANGEMENT CRUCIAL: Remplacer 'update_payload' par 'None'.
    # Cela force le graphe à charger l'état que nous venons de sauvegarder
    # et à continuer son chemin, au lieu de redémarrer.
    async for final_state in app_graph.astream(None, config, stream_mode="values"):
        pass

    # Le reste de la fonction est déjà correct.
    if final_state and final_state.get('is_conversation_finished'):
        # On a changé ce statut dans une version précédente. Assurons-nous qu'il est cohérent.
        return JourneyStatusResponse(
            status="conversation_finished",
            thread_id=thread_id,
            next_question="Thank you for the details. You can now proceed to generate the course."
        )
    elif final_state and final_state.get('current_question'):
         return JourneyStatusResponse(
            status="in_progress",
            thread_id=thread_id,
            next_question=final_state.get('current_question')
         )
    else:
        # Cas d'erreur si le graphe se termine de manière inattendue
        raise HTTPException(status_code=500, detail="Graph stopped in an unexpected state after continuation.")


# --- NOUVEL ENDPOINT 3 ---
@syllabus_router.post("/gen_syllabus/{thread_id}/course", response_model=JourneyStatusResponse, status_code=202)
async def generate_syllabus(
    thread_id: str,
    background_tasks: BackgroundTasks,# Injection de dépendance pour les tâches de fond
    x_youtube_api_key: Optional[str] = Header(None, alias="X-Youtube-Api-Key"),
    app_graph: Pregel = Depends(get_syllabus_graph) # Utilise le graphe de génération
):
    """
    Triggers the syllabus generation as a background task and returns immediately.
    The client must then poll the status endpoint to get the result.
    """
    config = {"configurable": {"thread_id": thread_id}}

    os.environ['YOUTUBE_API_KEY'] = x_youtube_api_key if x_youtube_api_key else os.getenv("YOUTUBE_API_KEY")

    async def run_generation_task():
        """
        Runs the generation graph and explicitly saves the final state.
        """
        try:
            print(f"--- [BACKGROUND] Starting syllabus generation for thread: {thread_id} ---")

            # ÉTAPE 1: EXÉCUTER le graphe et CAPTURER le résultat en mémoire.
            final_state_from_invoke = await app_graph.ainvoke({}, config)

            # --- AJOUT DE LOGS DE DÉBOGAGE CRUCIAUX ---
            # if final_state_from_invoke and final_state_from_invoke.get('final_syllabus_options_str'):
            #     print(f"--- [BACKGROUND] ainvoke successful. Syllabus found in memory. Preparing to save...")
            # else:
            #     print(f"--- [BACKGROUND] WARNING: ainvoke finished but 'final_syllabus_options_str' is missing from the result.")
            #     print(f"--- [BACKGROUND] Full result from ainvoke: {final_state_from_invoke}")
            # La sauvegarde explicite reste une bonne pratique
            # ÉTAPE 2: SAUVEGARDER EXPLICITEMENT le résultat dans la base de données.
            # aupdate_state va charger le checkpoint, fusionner notre résultat final,
            # et sauvegarder le tout. C'est l'étape qui manquait.
            if final_state_from_invoke:
                await app_graph.aupdate_state(config, final_state_from_invoke)
                print(f"--- [BACKGROUND] Successfully saved final state to checkpoint for thread: {thread_id} ---")

        except Exception as e:
            # C'est une bonne pratique de logger les erreurs dans les tâches de fond
            print(f"--- [BACKGROUND] ERROR during syllabus generation for thread {thread_id}: {e}")
            # Ici, vous pourriez aussi mettre à jour l'état avec un message d'erreur

    # On ajoute notre fonction à la liste des tâches à exécuter en arrière-plan.
    # FastAPI s'en occupera après avoir envoyé la réponse 202.
    background_tasks.add_task(run_generation_task)

    # On répond IMMÉDIATEMENT au client pour ne pas le faire attendre.
    return JourneyStatusResponse(
        status="generation_started",
        thread_id=thread_id,
        next_question="Syllabus generation has started. Please check the status endpoint in a few moments to retrieve the result."
    )


@syllabus_router.get("/gen_syllabus/{thread_id}/status", response_model=JourneyStatusResponse, summary="Get the status of a journey")
async def get_journey_status(
    thread_id: str,
    # On peut utiliser n'importe quel graphe qui partage le même checkpointer
    app_graph: Pregel = Depends(get_syllabus_graph)
):
    config = {"configurable": {"thread_id": thread_id}}

    try:
        # aget_state peut lever une exception si le thread n'existe pas
        snapshot = await app_graph.aget_state(config)
    except Exception:
        snapshot = None

    if not snapshot:
        raise HTTPException(status_code=404, detail="Journey not found.")

    state = snapshot.values

    final_syllabus_str = state.get('final_syllabus_options_str')

    if final_syllabus_str and final_syllabus_str != 'null':
        try:
            # --- CORRECTION FINALE ---
            # On désérialise la chaîne JSON en un objet Pydantic
            syllabus_obj = PydanticSerializer.loads(final_syllabus_str, SyllabusOptions)
            
            if syllabus_obj and syllabus_obj.syllabi:
                output_dict = syllabus_obj.model_dump()
                return JourneyStatusResponse(
                    status="completed", 
                    thread_id=thread_id,
                    output=output_dict 
                )
            else:
                # Le LLM a retourné un syllabus vide, on le traite comme "en cours" ou "échec".
                # "generation_failed" est peut-être un meilleur statut.
                return JourneyStatusResponse(
                    status="generation_failed_empty", 
                    thread_id=thread_id,
                    output={"syllabi": []}, # On peut retourner le résultat vide
                    next_question="The syllabus generation resulted in an empty course. You may try again."
                )
        except Exception as e:
            # Si le JSON est corrompu, on renvoie une erreur claire
            print(f"--- ERROR: Failed to parse final syllabus JSON for thread {thread_id}: {e} ---")
            print(f"--- Corrupted JSON string: {final_syllabus_str} ---")
            raise HTTPException(status_code=500, detail="Failed to parse the generated syllabus.")
    else:
        print(f"--- Syllabus: {final_syllabus_str} ---")
        return JourneyStatusResponse(
            status="generation_in_progress",
            thread_id=thread_id
        )