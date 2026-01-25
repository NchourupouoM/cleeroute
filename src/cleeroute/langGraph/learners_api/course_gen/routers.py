# In routers.py

import uuid
from typing import Dict, Optional
from .tasks import generate_syllabus_task

import os
from fastapi import APIRouter, HTTPException, Body, Depends, BackgroundTasks, Header
from langgraph.pregel import Pregel

from .config import PROGRESS_MAPPING, TOTAL_STEPS

from .models import (
    SyllabusRequest, 
    SyllabusOptions, 
    StartJourneyResponse, 
    ContinueJourneyRequest, 
    JourneyStatusResponse
)

from .state import GraphState, PydanticSerializer
from .dependencies import get_conversation_graph, get_syllabus_graph
from .tasks import generate_syllabus_task
from .models import JourneyProgress, JourneyStatusResponse

# for treamings APIs 
from fastapi.responses import StreamingResponse
import json


syllabus_router = APIRouter()

@syllabus_router.post(
    "/gen_syllabus", 
    response_model=StartJourneyResponse,
    summary="Start a new learning journey",
    responses={
        201: {"description": "Session created and first AI question generated."},
        500: {"description": "Internal server error during graph initialization."}
    }
)

async def start_learning_journey(
    request: SyllabusRequest,
    x_youtube_api_key: Optional[str] = Header(None, alias="X-Youtube-Api-Key"),
    app_graph: Pregel = Depends(get_conversation_graph)  # Dependency injection for the graph
):
    """
        **Initializes the Learning Journey and starts the Human-in-the-Loop (HITL) conversation.**

        This is the entry point of the system. It takes the user's initial intent and resources, sets up the execution environment, and triggers the AI consultant to ask the first clarifying question.

        **Process:**
        1.  **Initialization:** Generates a unique `thread_id` for this session.
        2.  **Data Processing:** Parses provided YouTube links (playlists/videos) and metadata.
        3.  **Graph Execution:** Starts the `ConversationGraph`. The AI analyzes the input and formulates a strategy.
        4.  **Interruption:** The graph runs until the AI needs more information from the user.

        **Returns:**
        - `thread_id`: The session identifier (CRITICAL: save this for subsequent calls).
        - `next_question`: The first question the AI asks the learner to refine their needs.
    """
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    os.environ['YOUTUBE_API_KEY'] = x_youtube_api_key if x_youtube_api_key else os.getenv("YOUTUBE_API_KEY")

    user_links_str = []
    if request.user_input_links:
        # On convertit la liste de HttpUrl en une liste de chaînes de caractères
        user_links_str = [str(link) for link in request.user_input_links]


    initial_state = {
        "user_input_text": request.user_input_text,
        "user_input_links": user_links_str,
        "metadata_str": PydanticSerializer.dumps(request.metadata),
        "language": request.language,
    }


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
        raise HTTPException(
            status_code=500, 
            detail="Graph finished unexpectedly without asking a question."
        )

@syllabus_router.post(
    "/gen_syllabus/{thread_id}/continue", 
    response_model=JourneyStatusResponse,
    summary="Continue the Conversation (Answer AI)",
    responses={
        200: {"description": "Answer processed. Returns next question or finish status."},
        404: {"description": "Session thread not found."},
        500: {"description": "Graph execution error."}
    }
)
async def continue_learning_journey(
    thread_id: str,
    request: ContinueJourneyRequest,
    app_graph: Pregel = Depends(get_conversation_graph)
):
    """
        **Submits the user's answer to the AI and advances the conversation.**

        Use this endpoint to reply to the `next_question` received from the previous step. The AI will analyze the answer and decide whether to ask another question or finalize the profile.

        **Process:**
        1.  **State Retrieval:** Loads the conversation history using `thread_id`.
        2.  **Update:** Appends the user's answer to the history.
        3.  **Reasoning:** The AI evaluates if it has enough information.
            *   *If NO:* It generates a new follow-up question.
            *   *If YES:* It marks the conversation as finished.

        **Returns:**
        - `status`: 
            - `"in_progress"`: The AI has another question for you.
            - `"conversation_finished"`: The AI has gathered enough info. You should now call the `/course` endpoint to generate the syllabus.
        - `next_question`: The text of the next question (if in_progress).
    """
    
    config = {"configurable": {"thread_id": thread_id}}

    current_snapshot = await app_graph.aget_state(config)

    if not current_snapshot:
        raise HTTPException(status_code=404, detail="Journey not found.")
    
    current_values = current_snapshot.values
    current_history = current_values.get('conversation_history', [])

    update_payload = {"conversation_history": [(request.user_answer, "")]}

    await app_graph.aupdate_state(config, update_payload)

    async for final_state in app_graph.astream(None, config, stream_mode="values"):
        pass

    if final_state and final_state.get('is_conversation_finished'):

        # On récupère le message personnalisé généré par l'IA (stocké dans current_question par le nœud)
        final_message = final_state.get('current_question')

        # Fallback ultime
        if not final_message:
            final_message = "Course generation started."

        return JourneyStatusResponse(
            status="conversation_finished",
            thread_id=thread_id,
            next_question=final_message
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


@syllabus_router.post("/gen_syllabus/{thread_id}/course", response_model=JourneyStatusResponse, status_code=202, summary="Trigger Asynchronous Syllabus Generation",responses={
        202: {"description": "Generation task accepted and queued in background."},
        404: {"description": "Conversation thread not found."},
})
async def generate_syllabus(
    thread_id: str,
    x_youtube_api_key: Optional[str] = Header(None, alias="X-Youtube-Api-Key"),
):
    
    """
        **Triggers the heavy background process to generate the full course syllabus.**

        This endpoint should ONLY be called after the conversation status is `"conversation_finished"`.
        
        **Mechanism:**
        - This is an **asynchronous** operation.
        - It does NOT return the syllabus immediately.
        - It dispatches a task to a **Celery Worker** via Redis.
        - The worker will perform YouTube searches, analysis, and syllabus structuring (taking 1-2 minutes).

        **Process:**
        1.  **State Handover:** Retrieves the final learner profile from the `ConversationGraph` state.
        2.  **Task Dispatch:** Sends all necessary data to the Celery worker queue.
        3.  **Immediate Return:** Returns a 202 Accepted status to unblock the UI.

        **Next Steps:**
        - The client must poll the **GET /gen_syllabus/{thread_id}/status** endpoint every few seconds to check progress and retrieve the final JSON result.
    """

    # Lancement de la tâche Celery
    task = generate_syllabus_task.delay(thread_id, x_youtube_api_key)
    print(f"Tâche envoyée à Celery avec l'ID: {task.id}")  # Log pour confirmer l'envoi
    return JourneyStatusResponse(
        status="generation_started",
        thread_id=thread_id,
        next_question="Syllabus generation has started. Please check the status endpoint in a few moments."
    )


@syllabus_router.get("/gen_syllabus/{thread_id}/status", response_model=JourneyStatusResponse, summary="Get the status of a journey")
async def get_journey_status(
    thread_id: str,
    # On peut utiliser n'importe quel graphe qui partage le même checkpointer
    app_graph: Pregel = Depends(get_syllabus_graph)
):
    """
        **Checks the progress of the background syllabus generation task.**

        Since generation is asynchronous, the frontend must poll this endpoint every few seconds (e.g., every 3-5s) after calling `/course`.

        **Capabilities:**
        1.  **Real-time Tracking:** It looks into the graph's memory to tell you exactly what the AI is doing right now (e.g., "Searching YouTube", "Drafting Blueprint").
        2.  **Result Retrieval:** Once finished, it delivers the final JSON syllabus.

        **Return Values (Status):**
        - `in_progress`: The worker is still busy. The `next_question` field will contain a user-friendly status message (e.g., "Analyzing your request...").
        - `completed`: Success! The `output` field contains the full `SyllabusOptions` JSON object. Stop polling.
        - `completed_empty`: The process finished but found no content. The `output` field is empty.

        **return values (progress)**:
        - `current_step`: The current step in the generation process.
        - `total_steps`: The total number of steps.
        - `percentage`: The completion percentage.
        - `label`: A user-friendly status message (e.g., "Analyzing your request...").
        - `description`: A more detailed description of the current step.

        **Client Logic:**
        - IF `status` == `in_progress`: Display `next_question` as a loading toast/spinner text. Wait 3s. Call again.
        - IF `status` == `completed`: Display the course selection UI using `output`.
    """

    config = {"configurable": {"thread_id": thread_id}}

    try:
        # aget_state peut lever une exception si le thread n'existe pas
        snapshot = await app_graph.aget_state(config)
    except Exception:
        snapshot = None

    if not snapshot:
        raise HTTPException(status_code=404, detail="Journey not found.")

    state = snapshot.values

    graph_status = state.get('status', 'starting')
    
    final_syllabus_str = state.get('final_syllabus_options_str')

    # Cas : TERMINE (Succès ou Échec géré)
    if graph_status in ["completed", "generation_failed_empty"]:
        
        # Préparer les stats de fin
        progress = JourneyProgress(
            current_step=TOTAL_STEPS,
            total_steps=TOTAL_STEPS,
            percentage=100,
            label="Process Finished",
            description="Generation complete."
        )

        output_dict = {"syllabi": []}
        
        # Tentative de chargement du résultat
        if final_syllabus_str and final_syllabus_str != 'null':
            try:
                syllabus_obj = PydanticSerializer.loads(final_syllabus_str, SyllabusOptions)
                if syllabus_obj.syllabi:
                    output_dict = syllabus_obj.model_dump()
            except:
                pass

        if output_dict["syllabi"]:
            return JourneyStatusResponse(
                status="completed",
                thread_id=thread_id,
                output=output_dict,
                progress=progress
            )
        else:
            return JourneyStatusResponse(
                status="generation_failed_empty",
                thread_id=thread_id,
                output={"syllabi": []},
                next_question="Sorry, we couldn't generate a valid course from the available resources.",
                progress=progress
            )

    # Cas : EN COURS
    mapping = PROGRESS_MAPPING.get(graph_status, PROGRESS_MAPPING["starting"])
    percent = int((mapping["step"] / TOTAL_STEPS) * 100)

    progress_data = JourneyProgress(
        current_step=mapping["step"],
        total_steps=TOTAL_STEPS,
        percentage=percent,
        label=mapping["label"],
        description=mapping["desc"]
    )

    return JourneyStatusResponse(
        status="in_progress",
        thread_id=thread_id,
        progress=progress_data
    )