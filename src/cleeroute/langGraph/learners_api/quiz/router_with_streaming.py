# Fichier: src/cleeroute/langGraph/learners_api/quiz/routers.py
import json
from typing import  List
from fastapi import APIRouter, Depends, Header, HTTPException
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
from src.cleeroute.langGraph.learners_api.quiz.services.quiz_services import save_quiz_progress
from src.cleeroute.langGraph.learners_api.quiz.services.ingestion_services import STREAM_DOCS
import os

from dotenv import load_dotenv
load_dotenv()


from src.cleeroute.langGraph.learners_api.quiz.services.user_service import get_user_profile
from src.cleeroute.langGraph.learners_api.quiz.services.user_service import build_personalization_block

from ..chats.course_context_for_global_chat import get_student_quiz_context, extract_context_from_course, fetch_course_hierarchy

from src.cleeroute.langGraph.learners_api.quiz.services.ingestion_services import FileIngestionService
from src.cleeroute.langGraph.learners_api.utils import get_llm

qa_llm = get_llm(api_key=os.getenv("GEMINI_API_KEY"))



# async def generate_quiz_stream(graph, input_state, config):
#     """
#         Générateur qui exécute le graphe et streame les tokens du LLM 
#         ainsi que l'état final.
#     """
#     # 1. On lance le graphe en mode "astream_events" (version v2 recommandée)
#     async for event in graph.astream_events(input_state, config, version="v2"):
        
#         # On filtre pour ne garder que les tokens générés par le ChatModel
#         kind = event["event"]
        
#         if kind == "on_chat_model_stream":
#             # C'est un token du LLM
#             content = event["data"]["chunk"].content
#             if content:
#                 # On envoie un événement SSE de type 'token'
#                 data = json.dumps({"type": "token", "content": content})
#                 yield f"data: {data}\n\n"

#     # 2. Une fois le stream fini, on récupère l'état final pour les métadonnées
#     # (isCorrect, chatHistory complet mis à jour pour la synchro)
#     snapshot = await graph.aget_state(config)
#     final_values = snapshot.values
    
#     # On désérialise proprement l'historique et les réponses
#     try:
#         # Récupération de l'historique
#         chat_history_str = final_values.get("chat_history", "[]")
#         # Note: On envoie la string brute ou l'objet, ici on envoie l'objet pour faciliter le frontend
#         # Mais dans un stream JSON, on envoie souvent un résumé.
        
#         # Récupération de isCorrect pour la question courante
#         # On regarde la dernière interaction ou les user_answers
#         user_answers = final_values.get("user_answers", {})
        
#         # On envoie un événement final 'end' avec les métadonnées
#         final_payload = {
#             "type": "end",
#             "chatHistory": chat_history_str, # Le frontend pourra le parser pour mettre à jour son état local
#             "userAnswers": user_answers # Pour savoir si c'est correct
#         }
#         yield f"data: {json.dumps(final_payload)}\n\n"
        
#     except Exception as e:
#         print(f"Error extracting final state in stream: {e}")
#         yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

async def _generic_quiz_stream(attemptId: str, payload: dict, graph):
    """Fonction générique pour streamer et sauvegarder."""
    config = {"configurable": {"thread_id": attemptId}}
    
    try:
        pool = get_active_pool()
    except: 
        raise HTTPException(500, "DB Pool missing")

    async def generator():
        # 1. Stream LLM
        async for event in graph.astream_events(payload, config, version="v2"):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                content = chunk.content if hasattr(chunk, "content") else str(chunk)
                if content:
                    yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"

        # 2. Sync DB
        snapshot = await graph.aget_state(config)
        final_values = snapshot.values
        
        try:
            chat_history = PydanticSerializer.loads(final_values.get("chat_history", "[]"), List[ChatMessage])
            user_answers = final_values.get("user_answers", {})
            
            # Sauvegarde persistante pour le Resume
            async with pool.connection() as conn:
                await save_quiz_progress(attemptId, chat_history, user_answers, conn)

            final_payload = {
                "type": "end",
                "chatHistory": final_values.get("chat_history"), # String pour le front
                "userAnswers": user_answers
            }
            yield f"data: {json.dumps(final_payload)}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")




stream_quiz_router = APIRouter()

# @stream_quiz_router.post("/stream-quiz-attempts/{attemptId}/answer") 
# async def submit_answer(
#     attemptId: str,
#     request: AnswerRequest,
#     graph: Pregel = Depends(get_quiz_graph)
# ):
#     config = {"configurable": {"thread_id": attemptId}}

#     update_payload = {
#         "current_interaction": {
#             "type": "answer",
#             "payload": request.model_dump()
#         }
#     }

#     # On retourne la StreamingResponse qui utilise notre générateur
#     return StreamingResponse(
#         generate_quiz_stream(graph, update_payload, config),
#         media_type="text/event-stream"
#     )

@stream_quiz_router.post("/stream-quiz-attempts/{attemptId}/answer") 
async def submit_answer(attemptId: str, request: AnswerRequest, graph=Depends(get_quiz_graph)):
    f"""
    **Submits a user answer and streams the AI feedback.**
    
    The system verifies the answer, updates the state, and the AI generates an explanation.
    {STREAM_DOCS}
    """
    payload = {"current_interaction": {"type": "answer", "payload": request.model_dump()}}
    return await _generic_quiz_stream(attemptId, payload, graph)

# @stream_quiz_router.get("/stream-quiz-attempts/{attemptId}/questions/{questionId}/hint")
# async def get_hint(
#     attemptId: str, 
#     questionId: str, 
#     graph: Pregel = Depends(get_quiz_graph)
# ):
#     config = {"configurable": {"thread_id": attemptId}}
    
#     update_payload = {
#         "current_interaction": {
#             "type": "hint",
#             "payload": {"questionId": questionId}
#         }
#     }
    
#     return StreamingResponse(
#         generate_quiz_stream(graph, update_payload, config),
#         media_type="text/event-stream"
#     )

@stream_quiz_router.get("/stream-quiz-attempts/{attemptId}/questions/{questionId}/hint")
async def get_hint(attemptId: str, questionId: str, graph=Depends(get_quiz_graph)):
    f"""
    **Generates a pedagogical hint for a specific question.**
    
    Does not reveal the answer but guides the user.
    {STREAM_DOCS}
    """
    payload = {"current_interaction": {"type": "hint", "payload": {"questionId": questionId}}}
    return await _generic_quiz_stream(attemptId, payload, graph)

# @stream_quiz_router.post("/stream-quiz-attempts/{attemptId}/skip")
# async def skip_question(
#     attemptId: str,
#     request: SkipRequest,
#     graph: Pregel = Depends(get_quiz_graph)
# ):
#     config = {"configurable": {"thread_id": attemptId}}

#     update_payload = {
#         "current_interaction": {
#             "type": "skip",
#             "payload": {"questionId": request.questionId}
#         }
#     }

#     return StreamingResponse(
#         generate_quiz_stream(graph, update_payload, config),
#         media_type="text/event-stream"
#     )

@stream_quiz_router.post("/stream-quiz-attempts/{attemptId}/skip")
async def skip_question(attemptId: str, request: SkipRequest, graph=Depends(get_quiz_graph)):
    f"""
    **Skips the current question and streams the solution.**
    
    Marks the question as skipped in stats and provides the correct answer immediately.\n
    {STREAM_DOCS}
    """
    payload = {"current_interaction": {"type": "skip", "payload": {"questionId": request.questionId}}}
    return await _generic_quiz_stream(attemptId, payload, graph)

# @stream_quiz_router.post("/stream-quiz-attempts/{attemptId}/ask")
# async def ask_follow_up(
#     attemptId: str, 
#     request: AskRequest, 
#     graph: Pregel = Depends(get_quiz_graph)
# ):
#     config = {"configurable": {"thread_id": attemptId}}
    
#     update_payload = {
#         "current_interaction": {
#             "type": "ask",
#             "payload": request.model_dump()
#         }
#     }
    
#     return StreamingResponse(
#         generate_quiz_stream(graph, update_payload, config),
#         media_type="text/event-stream"
#     )

@stream_quiz_router.post("/stream-quiz-attempts/{attemptId}/ask")
async def ask_follow_up(attemptId: str, request: AskRequest, graph=Depends(get_quiz_graph)):
    f"""
    **Asks a free-text question about the quiz context.**
    
    Allows the learner to clarify doubts about a question or explanation.
    {STREAM_DOCS}
    """
    payload = {"current_interaction": {"type": "ask", "payload": request.model_dump()}}
    return await _generic_quiz_stream(attemptId, payload, graph)


# @stream_quiz_router.get("/stream-quiz-attempts/{attemptId}/summary")
# async def get_summary(
#     attemptId: str, 
#     graph: Pregel = Depends(get_quiz_graph),
#     db: AsyncConnection = Depends(get_app_db_connection)
# ):
#     """
#     Génère le résumé en streaming et clôture le quiz en base de données à la fin.
#     """
#     config = {"configurable": {"thread_id": attemptId}}
    
#     # Payload pour déclencher le résumé
#     update_payload = {
#         "current_interaction": {
#             "type": "finish",
#             "payload": {}
#         }
#     }

#     async def summary_stream_generator():
#         full_recap_text = ""
        
#         try:
#             # 1. Streaming via le Graphe LangGraph
#             # On stream les événements pour capter les tokens du LLM
#             async for event in graph.astream_events(update_payload, config, version="v2"):
#                 kind = event["event"]
#                 # On filtre pour avoir les tokens du ChatModel
#                 if kind == "on_chat_model_stream":
#                     content = event["data"]["chunk"].content
#                     if content:
#                         full_recap_text += content
#                         yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"

#             # 2. Post-traitement : Récupération de l'état final et Sauvegarde BDD
#             snapshot = await graph.aget_state(config)
#             final_values = snapshot.values
            
#             # Désérialisation
#             chat_history_str = final_values.get("chat_history", "[]")
#             chat_history_list = PydanticSerializer.loads(chat_history_str, List[ChatMessage])
            
#             # Extraction du dernier message (le résumé) pour récupérer les stats calculées par le noeud
#             if chat_history_list:
#                 summary_message = chat_history_list[-1]
                
#                 if summary_message.type == 'recap' and summary_message.stats:
#                     stats = summary_message.stats
                    
#                     # Logique de calcul du score
#                     total_questions = stats.get('total', 0)
#                     if total_questions == 0: # Fallback si pas dans stats
#                          total_questions = stats.get('pass', 0) + stats.get('fail', 0) + stats.get('skipped', 0)
                         
#                     pass_percentage = (stats.get('pass', 0) / total_questions) * 100 if total_questions > 0 else 0
                    
#                     # Sérialisation historique pour BDD
#                     history_json = [msg.model_dump() for msg in chat_history_list]

#                     # MISE À JOUR BDD (Clôture du quiz)
#                     await db.execute(
#                         """
#                         UPDATE quiz_attempts
#                         SET status = 'completed', 
#                             pass_percentage = %s,
#                             correct_count = %s,
#                             incorrect_count = %s,
#                             skipped_count = %s,
#                             completed_at = CURRENT_TIMESTAMP,
#                             summary_text = %s,
#                             interaction_json = %s
#                         WHERE attempt_id = %s
#                         """,
#                         (
#                             pass_percentage, 
#                             stats.get('pass'), stats.get('fail'), stats.get('skipped'), 
#                             full_recap_text, # On utilise le texte accumulé
#                             json.dumps(history_json), 
#                             attemptId
#                         )
#                     )
                    
#             # 3. Envoi événement final avec l'historique complet
#             final_payload = {
#                 "type": "end",
#                 "chatHistory": chat_history_str
#             }
#             yield f"data: {json.dumps(final_payload)}\n\n"

#         except Exception as e:
#             print(f"Summary Stream Error: {e}")
#             yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

#     return StreamingResponse(summary_stream_generator(), media_type="text/event-stream")

@stream_quiz_router.get("/stream-quiz-attempts/{attemptId}/summary")
async def get_summary(
    attemptId: str, 
    graph=Depends(get_quiz_graph)
):
    """
        **Calculates the score and streams a personalized recap.**

        **Behavior:**
        - If all questions are answered/skipped: Marks status as `completed`.
        - If questions remain: Generates a progress report but keeps status `in_progress`.
        
        **SSE Events:**
        - Streams the recap text tokens.
        - Sends `{"type": "end", "status": "completed"}` at the end.
    """
    config = {"configurable": {"thread_id": attemptId}}
    payload = {"current_interaction": {"type": "finish", "payload": {}}}
    
    try:
        pool = get_active_pool()
    except: raise HTTPException(500, "DB Pool missing")

    async def summary_generator():
        full_text = ""
        # 1. Stream LLM
        async for event in graph.astream_events(payload, config, version="v2"):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                content = chunk.content if hasattr(chunk, "content") else str(chunk)
                if content:
                    full_text += content
                    yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"

        # 2. Logic Fin
        snapshot = await graph.aget_state(config)
        final_values = snapshot.values
        
        user_answers = final_values.get("user_answers", {})
        # On doit savoir combien de questions il y avait
        questions_str = final_values.get("questions", "[]")
        questions = PydanticSerializer.loads(questions_str, list)
        
        total_q = len(questions)
        answered_q = len(user_answers)

        # Si tout est répondu (ou skippé), c'est fini. Sinon, c'est juste une pause.
        is_complete = (answered_q >= total_q)
        new_status = "completed" if is_complete else "in_progress"

        chat_history = PydanticSerializer.loads(final_values.get("chat_history"), List[ChatMessage])
        
        # Stats
        correct = sum(1 for a in user_answers.values() if a.get("isCorrect"))
        incorrect = sum(1 for a in user_answers.values() if not a.get("isCorrect") and not a.get("skipped"))
        skipped = sum(1 for a in user_answers.values() if a.get("skipped"))
        
        score_pct = (correct / total_q * 100) if total_q > 0 else 0

        # Sauvegarde DB
        async with pool.connection() as conn:
            # Sauvegarde Chat + Réponses
            await save_quiz_progress(attemptId, chat_history, user_answers, conn)
            
            # Mise à jour Statut & Score
            await conn.execute(
                """
                UPDATE quiz_attempts
                SET status = %s, 
                    pass_percentage = %s,
                    correct_count = %s, incorrect_count = %s, skipped_count = %s,
                    summary_text = %s,
                    completed_at = CASE WHEN %s = 'completed' THEN CURRENT_TIMESTAMP ELSE completed_at END
                WHERE attempt_id = %s
                """,
                (new_status, score_pct, correct, incorrect, skipped, full_text, new_status, attemptId)
            )

        yield f"data: {json.dumps({'type': 'end', 'status': new_status})}\n\n"

    return StreamingResponse(summary_generator(), media_type="text/event-stream")
