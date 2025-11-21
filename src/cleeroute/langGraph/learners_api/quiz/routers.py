# Fichier: src/cleeroute/langGraph/learners_api/quiz/routers.py

import uuid
import json
import asyncio
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from langgraph.pregel import Pregel
from psycopg.connection_async import AsyncConnection

# 1. Importations des modèles et du graphe
from .models import (
    StartQuizRequest, AnswerRequest, AskRequest,
    QuizAttemptResponse, ChatHistoryResponse, QuizzesForCourseResponse,
    QuizQuestion, ChatMessage, QuizContent
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

from .prompts import COURSE_QA_PROMPT

qa_llm = ChatGoogleGenerativeAI(model=os.getenv("MODEL_2"), google_api_key=os.getenv("GEMINI_API_KEY"))


quiz_router = APIRouter()

# ==============================================================================
# ENDPOINT 1: Démarrer une Nouvelle Tentative de Quiz
# ==============================================================================
@quiz_router.post("/quiz-attempts", response_model=QuizAttemptResponse, status_code=201)
async def start_quiz_attempt(
    request: StartQuizRequest, 
    graph: Pregel = Depends(get_quiz_graph),
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
    Initialise une session de quiz :
    1. Prépare l'état initial pour le graphe LangGraph.
    2. Exécute le graphe pour générer le titre et les questions.
    3. Enregistre la nouvelle tentative de quiz dans la base de données applicative.
    4. Retourne l'identifiant de la tentative et les questions à l'utilisateur.
    """
    attempt_id = f"attempt_{uuid.uuid4()}"
    config = {"configurable": {"thread_id": attempt_id}}
    course_thread_id = request.threadId

    # --- ÉTAPE 1: Préparer l'état initial pour le graphe ---
    # Le graphe a besoin de toutes ces informations pour générer le contenu.
    context_data = {
        "scope": request.scope, "threadId": request.threadId, "sectionId": request.sectionId,
        "subsectionId": request.subsectionId, "videoId": request.videoId,
        "content_for_quiz": request.content_for_quiz
    }
    initial_state = {
        "attemptId": attempt_id,
        "context": context_data,
        "preferences": request.preferences,
        "user_answers": {}, # S'assurer que ce champ est initialisé
    }
    
    print(f"--- [API] Invoking quiz graph for attempt '{attempt_id}'... ---")
    await graph.ainvoke(initial_state, config)

    print(f"--- [API] Fetching final state for attempt '{attempt_id}'... ---")
    snapshot = await graph.aget_state(config)
    # print("snapshot", snapshot)
    if not snapshot or not snapshot.values:
        raise HTTPException(status_code=500, detail="Graph executed but failed to save state.")
    
    # Récupérer directement les valeurs depuis snapshot.values
    final_values = snapshot.values


    quiz_title = final_values.get("title")
    if not quiz_title or "Failed" in quiz_title:
        # Mesure de sécurité si la génération du titre a échoué
        quiz_title = f"Quiz on {context_data.get('scope')} '{context_data.get('sectionId', course_thread_id)}'"

    try:
        await db.execute(
            """
            INSERT INTO quiz_attempts (attempt_id, course_thread_id, title, status)
            VALUES (%s, %s, %s, 'started')
            """,
            (attempt_id, course_thread_id, quiz_title)
        )
        print(f"--- [APP DB] Successfully logged new quiz attempt with title: '{quiz_title}' ---")
    except Exception as e:
        print(f"--- [APP DB] FATAL ERROR: Could not save quiz attempt to application DB: {e} ---")
        # Il est crucial de lever une erreur ici car sans enregistrement, le quiz est invalide.
        raise HTTPException(status_code=500, detail="Failed to initiate and save the quiz session.")
        
    questions = final_values.get("questions") # On récupère la chaîne sérialisée

    if not questions:
        questions_list = []
    else:
       # Désérialiser les questions et l'historique de chat
        questions_str = final_values.get("questions", "[]")
        questions_list = PydanticSerializer.loads(questions_str, List[QuizQuestion])
        chat_history_str = final_values.get("chat_history", "[]")
        chat_history_list = PydanticSerializer.loads(chat_history_str, List[ChatMessage])

    return QuizAttemptResponse(
        attemptId=attempt_id,
        title=quiz_title,
        questions=questions_list,
        chatHistory=chat_history_list
    )


@quiz_router.post("/quiz-attempts/{attemptId}/answer", response_model=ChatHistoryResponse)
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

    try:
        # Exécuter le graphe avec la nouvelle interaction
        await graph.ainvoke(update_payload, config)
    except Exception as e:
        print(f"--- ERROR: Failed to invoke graph: {e} ---")
        raise HTTPException(status_code=500, detail=f"Failed to invoke graph: {e}")

    # Récupérer l'état mis à jour
    try:
        snapshot = await graph.aget_state(config)
    except Exception as e:
        print(f"--- ERROR: Failed to get state: {e} ---")
        raise HTTPException(status_code=500, detail=f"Failed to get state: {e}")

    if not snapshot or not snapshot.values:
        raise HTTPException(status_code=500, detail="Graph executed but failed to return state. Check logs.")

    # Récupérer les valeurs de l'état
    try:
        raw_state = snapshot.values
    except Exception as e:
        print(f"--- ERROR: Failed to get raw state: {e} ---")
        raise HTTPException(status_code=500, detail=f"Failed to get raw state: {e}")

    # Vérifier si raw_state est une chaîne JSON ou un dictionnaire
    if isinstance(raw_state, str):
        try:
            final_values = json.loads(raw_state)
        except json.JSONDecodeError as e:
            print(f"--- ERROR: Failed to parse JSON: {e} ---")
            raise HTTPException(status_code=500, detail=f"Failed to parse graph state (Invalid JSON): {e}")
    else:
        final_values = raw_state

    # Désérialiser chat_history
    try:
        chat_history_str = final_values.get("chat_history", "[]")
        chat_history_list = PydanticSerializer.loads(chat_history_str, List[ChatMessage])
    except Exception as e:
        print(f"--- ERROR: Failed to deserialize chat history: {e} ---")
        raise HTTPException(status_code=500, detail=f"Failed to deserialize chat history: {e}")

    return ChatHistoryResponse(chatHistory=chat_history_list)


@quiz_router.get("/quiz-attempts/{attemptId}/questions/{questionId}/hint", response_model=ChatHistoryResponse)
async def get_hint(
    attemptId: str, 
    questionId: str, 
    graph: Pregel = Depends(get_quiz_graph)
):
    """
    Demande un indice pour une question, et retourne l'historique du chat mis à jour.
    """
    config = {"configurable": {"thread_id": attemptId}}
    
    update_payload = {
        "current_interaction": {
            "type": "hint",
            "payload": {"questionId": questionId}
        }
    }
    
    # final_state_dict = await graph.ainvoke(update_payload, config)

    await graph.ainvoke(update_payload, config)

    snapshot = await graph.aget_state(config)

    if not snapshot or not snapshot.values:
        raise HTTPException(status_code=500, detail="Graph executed but failed to save state.")
        
    raw_state = snapshot.values

    # Sécurité : si raw_state est une string JSON (parfois le cas selon le checkpointer), on la parse
    if isinstance(raw_state, str):
        final_values = json.loads(raw_state)
    else:
        final_values = raw_state
    
    # Maintenant final_values est bien un dict, on peut faire .get()
    chat_history_str = final_values.get("chat_history")
    
    if not chat_history_str:
        chat_history_list = []
    else:
        chat_history_list = PydanticSerializer.loads(chat_history_str, List[ChatMessage])

    return ChatHistoryResponse(chatHistory=chat_history_list)

# ==============================================================================
# ENDPOINT 4: Poser une Question de Suivi
# ==============================================================================
@quiz_router.post("/quiz-attempts/{attemptId}/ask", response_model=ChatHistoryResponse)
async def ask_follow_up(
    attemptId: str, 
    request: AskRequest, 
    graph: Pregel = Depends(get_quiz_graph)
):
    """
    Pose une question ouverte à l'IA et retourne l'historique du chat mis à jour.
    """
    config = {"configurable": {"thread_id": attemptId}}
    
    update_payload = {
        "current_interaction": {
            "type": "ask",
            "payload": request.model_dump()
        }
    }
    
    # ainvoke retourne directement l'état final (dictionnaire)
    final_values = await graph.ainvoke(update_payload, config)
    
    # Pas besoin de list(final_values.values())[0] ici car ainvoke retourne l'état complet
    chat_history_str = final_values.get("chat_history", "[]")
    
    chat_history_list = PydanticSerializer.loads(chat_history_str, List[ChatMessage])

    return ChatHistoryResponse(chatHistory=chat_history_list)

# ==============================================================================
# ENDPOINT 5: Obtenir le Résumé Final du Quiz
# ==============================================================================
@quiz_router.get("/quiz-attempts/{attemptId}/summary", response_model=ChatHistoryResponse)
async def get_summary(
    attemptId: str, 
    graph: Pregel = Depends(get_quiz_graph),
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
    Calcule le score final, génère un résumé, et retourne l'historique du chat complété.
    """
    config = {"configurable": {"thread_id": attemptId}}

    # 1. On prépare le payload pour déclencher le routeur vers 'generate_summary'
    update_payload = {
        "current_interaction": {
            "type": "finish", # Ce type sera capté par route_quiz_entry
            "payload": {}
        }
    }
    
    # 2. On invoque le graphe normalement (sans run_nodes qui n'existe pas)
    # ainvoke retourne l'état final directement (dictionnaire)
    final_values = await graph.ainvoke(update_payload, config)

    # 3. Gestion sécurisée de la désérialisation (correction AttributeError)
    chat_history_str = final_values.get("chat_history")
    
    if not chat_history_str:
        chat_history_list = []
    else:
        chat_history_list = PydanticSerializer.loads(chat_history_str, List[ChatMessage])

    try:
        if chat_history_list:
            summary_message = chat_history_list[-1]
            
            if summary_message.type == 'recap' and summary_message.stats:
                stats = summary_message.stats
                total_questions = stats.get('pass', 0) + stats.get('fail', 0) + stats.get('skipped', 0)
                pass_percentage = (stats.get('pass', 0) / total_questions) * 100 if total_questions > 0 else 0

                await db.execute(
                    """
                    UPDATE quiz_attempts
                    SET status = 'completed', 
                        pass_percentage = %s,
                        correct_count = %s,
                        incorrect_count = %s,
                        skipped_count = %s,
                        completed_at = CURRENT_TIMESTAMP
                    WHERE attempt_id = %s
                    """,
                    (pass_percentage, stats.get('pass'), stats.get('fail'), stats.get('skipped'), attemptId)
                )
                print(f"--- [APP DB] Successfully updated quiz attempt '{attemptId}' with final score. ---")

    except Exception as e:
        print(f"--- [APP DB] WARNING: Could not update final score for quiz attempt '{attemptId}': {e} ---")
    
    return ChatHistoryResponse(chatHistory=chat_history_list)

# ==============================================================================
# ENDPOINT 6: Obtenir la Liste des Quiz pour un Cours
# ==============================================================================
@quiz_router.get("/courses/{threadId}/quizzes", response_model=List[QuizzesForCourseResponse])
async def get_quizzes_for_course(
    threadId: str,
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
    Récupère un résumé de toutes les tentatives de quiz pour un cours donné
    en interrogeant la base de données applicative.
    """
    try:
        # 1. On exécute la requête pour obtenir un curseur
        cursor = await db.execute(
            "SELECT attempt_id, title, pass_percentage FROM quiz_attempts WHERE course_thread_id = %s ORDER BY created_at DESC",
            (threadId,)
        )
        # 2. On attend le résultat du fetchall (qui est aussi async en psycopg 3)
        records = await cursor.fetchall()

    except Exception as e:
        print(f"--- [APP DB] FATAL ERROR: Could not fetch quizzes for course '{threadId}': {e} ---")
        raise HTTPException(status_code=500, detail="Failed to fetch quiz history.")

    response_list = []
    for rec in records:
        # Si rec est un tuple (cas par défaut de psycopg), on accède par index
        if isinstance(rec, tuple):
             response_list.append(QuizzesForCourseResponse(
                attemptId=rec[0],         # attempt_id
                title=rec[1],             # title
                passPercentage=rec[2] or 0.0 # pass_percentage
            ))
        # Si rec est un dict (si vous avez configuré row_factory)
        else:
            response_list.append(QuizzesForCourseResponse(
                attemptId=rec["attempt_id"],
                title=rec["title"],
                passPercentage=rec.get("pass_percentage") or 0.0
            ))

    return response_list


# @quiz_router.post("/courses/{threadId}/ask-free", response_model=CourseAskResponse)
# async def ask_course_free_question(
#     threadId: str,
#     request: CourseAskRequest,
#     db: AsyncConnection = Depends(get_app_db_connection)
# ):
#     """
#     Permet de poser une question libre sur le contenu d'un cours généré.
#     """
    
#     # 1. Récupérer le JSON complet du cours depuis la BDD
#     # On suppose que vous stockez le 'CompleteCourse' sérialisé dans une table 'generated_courses' ou similaire
#     try:
#         # Exemple de requête : adaptez le nom de la table et de la colonne
#         cursor = await db.execute(
#             "SELECT course_data FROM generated_courses WHERE thread_id = %s",
#             (threadId,)
#         )
#         result = await cursor.fetchone()
        
#         if not result:
#             raise HTTPException(status_code=404, detail="Course not found")
            
#         # Si 'course_data' est stocké en JSONB (dict) ou Text (str)
#         course_data_raw = result[0] # ou result["course_data"] selon row_factory
        
#         # Désérialisation en objet Pydantic
#         if isinstance(course_data_raw, str):
#              course_obj = PydanticSerializer.loads(course_data_raw, CompleteCourse)
#         else:
#              # Si c'est déjà un dict (JSONB via psycopg)
#              course_obj = CompleteCourse(**course_data_raw)
             
#     except Exception as e:
#         print(f"--- [DB ERROR] Failed to fetch course data: {e} ---")
#         raise HTTPException(status_code=500, detail="Internal server error fetching course content")

#     # 2. Construire le contexte textuel
#     try:
#         context_text, context_title = extract_context_from_course(
#             course=course_obj,
#             scope=request.scope,
#             section_idx=request.sectionIndex,
#             subsection_idx=request.subsectionIndex
#         )
#     except Exception as e:
#          raise HTTPException(status_code=400, detail=f"Error extracting context: {str(e)}")

#     # 3. Appeler le LLM
#     formatted_prompt = COURSE_QA_PROMPT.format(
#         context_text=context_text,
#         user_query=request.userQuery
#     )
    
#     try:
#         response = await qa_llm.ainvoke(formatted_prompt)
#         answer_text = response.content
#     except Exception as e:
#         print(f"--- [LLM ERROR] Failed to generate answer: {e} ---")
#         raise HTTPException(status_code=500, detail="Failed to generate answer from AI")

#     # 4. Sauvegarde dans la BDD ---
#     try:
#         await db.execute(
#             """
#             INSERT INTO course_qa_history 
#             (course_thread_id, scope, section_index, subsection_index, question, answer, context_title)
#             VALUES (%s, %s, %s, %s, %s, %s, %s)
#             """,
#             (
#                 threadId, 
#                 request.scope, 
#                 request.sectionIndex, 
#                 request.subsectionIndex, 
#                 request.userQuery, 
#                 answer_text, 
#                 context_title
#             )
#         )
#         # Pas besoin de commit explicite si votre configuration DB est en autocommit,
#         # sinon ajoutez await db.commit() ici selon votre config psycopg.
#         print(f"--- [DB] Saved Q&A to history for course {threadId} ---")
        
#     except Exception as e:
#         # On log l'erreur mais on ne bloque pas la réponse à l'utilisateur
#         print(f"--- [DB ERROR] Failed to save history: {e} ---")

#     return CourseAskResponse(
#         answer=answer_text,
#         contextUsed=context_title
#     )


# @quiz_router.get("/courses/{threadId}/qa-history", response_model=List[QAHistoryItem])
# async def get_course_qa_history(
#     threadId: str,
#     db: AsyncConnection = Depends(get_app_db_connection)
# ):
#     """
#     Récupère tout l'historique des questions/réponses libres pour un cours donné.
#     """
#     try:
#         cursor = await db.execute(
#             """
#             SELECT id, scope, question, answer, context_title, created_at 
#             FROM course_qa_history 
#             WHERE course_thread_id = %s 
#             ORDER BY created_at DESC
#             """,
#             (threadId,)
#         )
        
#         records = await cursor.fetchall()
        
#         history = []
#         for rec in records:
#             # Gestion tuple vs dict (pour être robuste comme vu précédemment)
#             if isinstance(rec, tuple):
#                 history.append(QAHistoryItem(
#                     id=str(rec[0]),
#                     scope=rec[1],
#                     question=rec[2],
#                     answer=rec[3],
#                     contextTitle=rec[4],
#                     createdAt=rec[5]
#                 ))
#             else:
#                 # Si row_factory est configuré
#                 history.append(QAHistoryItem(
#                     id=str(rec["id"]),
#                     scope=rec["scope"],
#                     question=rec["question"],
#                     answer=rec["answer"],
#                     contextTitle=rec["context_title"],
#                     createdAt=rec["created_at"]
#                 ))
                
#         return history

#     except Exception as e:
#         print(f"--- [DB ERROR] Failed to fetch Q&A history: {e} ---")
#         raise HTTPException(status_code=500, detail="Failed to load history")