# Fichier: src/cleeroute/langGraph/learners_api/quiz/routers.py

import uuid
import json
import asyncio
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Header
from langgraph.pregel import Pregel
from langchain_core.messages import HumanMessage, AIMessage
from psycopg.connection_async import AsyncConnection
from datetime import datetime

import json
from fastapi.responses import StreamingResponse

# 1. Importations des modèles et du graphe
from .models import (
    StartQuizRequest, AnswerRequest, AskRequest,
    QuizAttemptResponse, ChatHistoryResponse, QuizzesForCourseResponse,
    QuizQuestion, ChatMessage, QuizContent,QuizStats,
    SkipRequest, ChatAskRequest, ChatSessionResponse, CreateSessionRequest, MessageResponse
)
from src.cleeroute.langGraph.learners_api.course_gen.models import CompleteCourse
# from .util_qa import extract_context_from_course

from .graph import get_quiz_graph
# Import du sérialiseur que nous utilisons de manière cohérente
from src.cleeroute.langGraph.learners_api.course_gen.state import PydanticSerializer
from src.cleeroute.db.app_db import get_app_db_connection
from langchain_google_genai import ChatGoogleGenerativeAI
import os

from dotenv import load_dotenv
load_dotenv()

from .prompts import GLOBAL_CHAT_PROMPT, GENERATE_SESSION_TITLE_PROMPT


from src.cleeroute.langGraph.learners_api.quiz.user_service import get_user_profile
from src.cleeroute.langGraph.learners_api.quiz.user_service import build_personalization_block

from .course_context_for_global_chat import get_student_quiz_context, extract_context_from_course, fetch_course_hierarchy

qa_llm = ChatGoogleGenerativeAI(model=os.getenv("MODEL_2"), google_api_key=os.getenv("GEMINI_API_KEY"))



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


stream_global_chat_router = APIRouter()
@stream_global_chat_router.post("/stream-sessions/{sessionId}/ask")
async def ask_in_session(
    sessionId: str,
    request: ChatAskRequest,
    userId: str = Header(..., alias="userId"),
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
    Version STREAMING du chat global.
    Envoie des événements SSE: 'token' (contenu) et 'end' (fin + métadonnées).
    """
    profile = await get_user_profile(userId, db)
    persona_block = build_personalization_block(profile)

    # 1. Préparation des données (Identique à avant)
    cursor = await db.execute(
        "SELECT course_id, scope, section_index, subsection_index, video_id FROM chat_sessions WHERE session_id = %s",
        (sessionId,)
    )
    session_rec = await cursor.fetchone()
    if not session_rec:
        raise HTTPException(status_code=404, detail="Session not found")
        
    if isinstance(session_rec, tuple):
        course_id, scope, sec_idx, sub_idx, vid_id = session_rec
    else:
        course_id, scope, sec_idx, sub_idx, vid_id = session_rec["course_id"], session_rec["scope"], session_rec["section_index"], session_rec["subsection_index"], session_rec["video_id"]

    # Reconstruction des contextes
    try:
        course_obj = await fetch_course_hierarchy(db, str(course_id))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to retrieve course structure")

    context_text = extract_context_from_course(course_obj, scope, sec_idx, sub_idx, vid_id)
    student_quiz_context = await get_student_quiz_context(db, str(course_id))

    # Récupération historique
    msgs_cursor = await db.execute(
        "SELECT sender, content FROM chat_messages WHERE session_id = %s ORDER BY created_at ASC",
        (sessionId,)
    )
    history_rows = await msgs_cursor.fetchall()
    is_first_interaction = (len(history_rows) == 0)
    
    langchain_history = []
    for row in history_rows:
        sender, content = (row[0], row[1]) if isinstance(row, tuple) else (row['sender'], row['content'])
        if sender == 'user':
            langchain_history.append(HumanMessage(content=content))
        else:
            langchain_history.append(AIMessage(content=content))

    # Préparation de la chaîne
    chain = GLOBAL_CHAT_PROMPT | qa_llm
    
    # Inputs pour le LLM
    chain_inputs = {
        "student_quiz_context": student_quiz_context,
        "scope": scope,
        "context_text": context_text,
        "history": langchain_history,
        "user_query": request.userQuery,
        "personalization_block": persona_block
    }

    # --- LE GÉNÉRATEUR ASYNCHRONE ---
    async def global_chat_generator():
        full_answer_text = ""
        
        try:
            # A. Streaming des tokens
            async for chunk in chain.astream(chain_inputs):
                content = chunk.content
                if content:
                    full_answer_text += content
                    # Envoi du token au client
                    yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
            
            # B. Post-traitement (Une fois le LLM fini)
            # Sauvegarde User + AI
            await db.execute(
                """
                INSERT INTO chat_messages (session_id, sender, content) 
                VALUES (%s, 'user', %s), (%s, 'ai', %s)
                """,
                (sessionId, request.userQuery, sessionId, full_answer_text)
            )

            # Gestion du Titre (Si premier message)
            if is_first_interaction:
                try:
                    title_chain = GENERATE_SESSION_TITLE_PROMPT | qa_llm
                    title_response = await title_chain.ainvoke({"user_query": request.userQuery})
                    new_title = title_response.content.strip().replace('"', '')
                    await db.execute(
                        "UPDATE chat_sessions SET title = %s, updated_at = CURRENT_TIMESTAMP WHERE session_id = %s",
                        (new_title, sessionId)
                    )
                except Exception as e:
                    print(f"Title Gen Error: {e}")
                    await db.execute("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = %s", (sessionId,))
            else:
                await db.execute("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = %s", (sessionId,))

            # C. Envoi de l'événement de fin
            yield f"data: {json.dumps({'type': 'end', 'status': 'completed'})}\n\n"

        except Exception as e:
            print(f"Stream Error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    # Retour de la réponse streamée
    return StreamingResponse(global_chat_generator(), media_type="text/event-stream")