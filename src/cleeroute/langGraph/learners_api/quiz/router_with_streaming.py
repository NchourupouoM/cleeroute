# Fichier: src/cleeroute/langGraph/learners_api/quiz/routers.py
import json
from typing import  List
from fastapi import APIRouter, Depends, Header
from langgraph.pregel import Pregel
from psycopg.connection_async import AsyncConnection

import json
from fastapi.responses import StreamingResponse

# 1. Importations des modèles et du graphe
from .models import (AnswerRequest, AskRequest, ChatMessage,SkipRequest)
from .graph import get_quiz_graph

# Import du sérialiseur que nous utilisons de manière cohérente
from src.cleeroute.langGraph.learners_api.course_gen.state import PydanticSerializer
from src.cleeroute.db.app_db import get_app_db_connection, get_active_pool

import os

from dotenv import load_dotenv
load_dotenv()


from src.cleeroute.langGraph.learners_api.quiz.services.user_service import get_user_profile
from src.cleeroute.langGraph.learners_api.quiz.services.user_service import build_personalization_block

from ..chats.course_context_for_global_chat import get_student_quiz_context, extract_context_from_course, fetch_course_hierarchy

from src.cleeroute.langGraph.learners_api.quiz.services.ingestion_services import FileIngestionService
from src.cleeroute.langGraph.learners_api.utils import get_llm

qa_llm = get_llm(api_key=os.getenv("GEMINI_API_KEY"))



async def generate_quiz_stream(graph, input_state, config):
    """
        Générateur qui exécute le graphe et streame les tokens du LLM 
        ainsi que l'état final.
    """
    # 1. On lance le graphe en mode "astream_events" (version v2 recommandée)
    async for event in graph.astream_events(input_state, config, version="v2"):
        
        # On filtre pour ne garder que les tokens générés par le ChatModel
        kind = event["event"]
        
        if kind == "on_chat_model_stream":
            # C'est un token du LLM
            content = event["data"]["chunk"].content
            if content:
                # On envoie un événement SSE de type 'token'
                data = json.dumps({"type": "token", "content": content})
                yield f"data: {data}\n\n"

    # 2. Une fois le stream fini, on récupère l'état final pour les métadonnées
    # (isCorrect, chatHistory complet mis à jour pour la synchro)
    snapshot = await graph.aget_state(config)
    final_values = snapshot.values
    
    # On désérialise proprement l'historique et les réponses
    try:
        # Récupération de l'historique
        chat_history_str = final_values.get("chat_history", "[]")
        # Note: On envoie la string brute ou l'objet, ici on envoie l'objet pour faciliter le frontend
        # Mais dans un stream JSON, on envoie souvent un résumé.
        
        # Récupération de isCorrect pour la question courante
        # On regarde la dernière interaction ou les user_answers
        user_answers = final_values.get("user_answers", {})
        
        # On envoie un événement final 'end' avec les métadonnées
        final_payload = {
            "type": "end",
            "chatHistory": chat_history_str, # Le frontend pourra le parser pour mettre à jour son état local
            "userAnswers": user_answers # Pour savoir si c'est correct
        }
        yield f"data: {json.dumps(final_payload)}\n\n"
        
    except Exception as e:
        print(f"Error extracting final state in stream: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

stream_quiz_router = APIRouter()

@stream_quiz_router.post("/stream-quiz-attempts/{attemptId}/answer") 
async def submit_answer(
    attemptId: str,
    request: AnswerRequest,
    graph: Pregel = Depends(get_quiz_graph)
):
    config = {"configurable": {"thread_id": attemptId}}

    update_payload = {
        "current_interaction": {
            "type": "answer",
            "payload": request.model_dump()
        }
    }

    # On retourne la StreamingResponse qui utilise notre générateur
    return StreamingResponse(
        generate_quiz_stream(graph, update_payload, config),
        media_type="text/event-stream"
    )

@stream_quiz_router.get("/stream-quiz-attempts/{attemptId}/questions/{questionId}/hint")
async def get_hint(
    attemptId: str, 
    questionId: str, 
    graph: Pregel = Depends(get_quiz_graph)
):
    config = {"configurable": {"thread_id": attemptId}}
    
    update_payload = {
        "current_interaction": {
            "type": "hint",
            "payload": {"questionId": questionId}
        }
    }
    
    return StreamingResponse(
        generate_quiz_stream(graph, update_payload, config),
        media_type="text/event-stream"
    )

@stream_quiz_router.post("/stream-quiz-attempts/{attemptId}/skip")
async def skip_question(
    attemptId: str,
    request: SkipRequest,
    graph: Pregel = Depends(get_quiz_graph)
):
    config = {"configurable": {"thread_id": attemptId}}

    update_payload = {
        "current_interaction": {
            "type": "skip",
            "payload": {"questionId": request.questionId}
        }
    }

    return StreamingResponse(
        generate_quiz_stream(graph, update_payload, config),
        media_type="text/event-stream"
    )

@stream_quiz_router.post("/stream-quiz-attempts/{attemptId}/ask")
async def ask_follow_up(
    attemptId: str, 
    request: AskRequest, 
    graph: Pregel = Depends(get_quiz_graph)
):
    config = {"configurable": {"thread_id": attemptId}}
    
    update_payload = {
        "current_interaction": {
            "type": "ask",
            "payload": request.model_dump()
        }
    }
    
    return StreamingResponse(
        generate_quiz_stream(graph, update_payload, config),
        media_type="text/event-stream"
    )

@stream_quiz_router.get("/stream-quiz-attempts/{attemptId}/summary")
async def get_summary(
    attemptId: str, 
    graph: Pregel = Depends(get_quiz_graph),
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
    Génère le résumé en streaming et clôture le quiz en base de données à la fin.
    """
    config = {"configurable": {"thread_id": attemptId}}
    
    # Payload pour déclencher le résumé
    update_payload = {
        "current_interaction": {
            "type": "finish",
            "payload": {}
        }
    }

    async def summary_stream_generator():
        full_recap_text = ""
        
        try:
            # 1. Streaming via le Graphe LangGraph
            # On stream les événements pour capter les tokens du LLM
            async for event in graph.astream_events(update_payload, config, version="v2"):
                kind = event["event"]
                # On filtre pour avoir les tokens du ChatModel
                if kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if content:
                        full_recap_text += content
                        yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"

            # 2. Post-traitement : Récupération de l'état final et Sauvegarde BDD
            snapshot = await graph.aget_state(config)
            final_values = snapshot.values
            
            # Désérialisation
            chat_history_str = final_values.get("chat_history", "[]")
            chat_history_list = PydanticSerializer.loads(chat_history_str, List[ChatMessage])
            
            # Extraction du dernier message (le résumé) pour récupérer les stats calculées par le noeud
            if chat_history_list:
                summary_message = chat_history_list[-1]
                
                if summary_message.type == 'recap' and summary_message.stats:
                    stats = summary_message.stats
                    
                    # Logique de calcul du score
                    total_questions = stats.get('total', 0)
                    if total_questions == 0: # Fallback si pas dans stats
                         total_questions = stats.get('pass', 0) + stats.get('fail', 0) + stats.get('skipped', 0)
                         
                    pass_percentage = (stats.get('pass', 0) / total_questions) * 100 if total_questions > 0 else 0
                    
                    # Sérialisation historique pour BDD
                    history_json = [msg.model_dump() for msg in chat_history_list]

                    # MISE À JOUR BDD (Clôture du quiz)
                    await db.execute(
                        """
                        UPDATE quiz_attempts
                        SET status = 'completed', 
                            pass_percentage = %s,
                            correct_count = %s,
                            incorrect_count = %s,
                            skipped_count = %s,
                            completed_at = CURRENT_TIMESTAMP,
                            summary_text = %s,
                            interaction_json = %s
                        WHERE attempt_id = %s
                        """,
                        (
                            pass_percentage, 
                            stats.get('pass'), stats.get('fail'), stats.get('skipped'), 
                            full_recap_text, # On utilise le texte accumulé
                            json.dumps(history_json), 
                            attemptId
                        )
                    )
                    
            # 3. Envoi événement final avec l'historique complet
            final_payload = {
                "type": "end",
                "chatHistory": chat_history_str
            }
            yield f"data: {json.dumps(final_payload)}\n\n"

        except Exception as e:
            print(f"Summary Stream Error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(summary_stream_generator(), media_type="text/event-stream")