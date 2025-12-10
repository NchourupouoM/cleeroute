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

stream_syllabus_router = APIRouter()

#  same APIs with streaming integrate

async def stream_graph_execution(graph, input_state, config):
    thread_id = config["configurable"]["thread_id"]
    yield json.dumps({"event": "metadata", "data": {"thread_id": thread_id}}) + "\n"

    # CHANGEMENT ICI : Passez à version="v2"
    async for event in graph.astream_events(input_state, config, version="v2"):
        
        kind = event["event"]
        
        # Avec v2, on s'assure de ne prendre que les événements de streaming du modèle
        if kind == "on_chat_model_stream":
            # Dans v2, la structure peut être légèrement différente, mais généralement:
            chunk = event["data"]["chunk"]
            
            # Vérification de sécurité pour le contenu
            content = chunk.content if hasattr(chunk, "content") else str(chunk)
            
            if content:
                yield json.dumps({"event": "token", "data": content}) + "\n"


@stream_syllabus_router.post("/stream_gen_syllabus", status_code=201)
async def start_learning_journey(
    request: SyllabusRequest,
    x_youtube_api_key: Optional[str] = Header(None, alias="X-Youtube-Api-Key"),
    app_graph: Pregel = Depends(get_conversation_graph)
):
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    os.environ['YOUTUBE_API_KEY'] = x_youtube_api_key if x_youtube_api_key else os.getenv("YOUTUBE_API_KEY")

    # Préparation de l'état initial (comme avant)
    user_links_str = []
    if request.user_input_links:
        user_links_str = [str(link) for link in request.user_input_links]

    initial_values = {
        "user_input_text": request.user_input_text,
        "user_input_links": user_links_str,
        "metadata_str": PydanticSerializer.dumps(request.metadata)
    }

    # RETOURNER UNE STREAMING RESPONSE
    # Le frontend devra lire ce flux ligne par ligne
    return StreamingResponse(
        stream_graph_execution(app_graph, initial_values, config),
        media_type="application/x-ndjson" # Newline Delimited JSON
    )


@stream_syllabus_router.post("/stream_gen_syllabus/{thread_id}/continue")
async def continue_learning_journey(
    thread_id: str,
    request: ContinueJourneyRequest,
    app_graph: Pregel = Depends(get_conversation_graph)
):
    config = {"configurable": {"thread_id": thread_id}}

    # Vérification de l'existence (comme avant)
    current_snapshot = await app_graph.aget_state(config)
    if not current_snapshot:
        raise HTTPException(status_code=404, detail="Journey not found.")
    
    # Mise à jour de l'historique
    update_payload = {"conversation_history": [(request.user_answer, "")]}
    await app_graph.aupdate_state(config, update_payload)

    # Lancement du stream
    return StreamingResponse(
        stream_graph_execution(app_graph, None, config),
        media_type="application/x-ndjson"
    )