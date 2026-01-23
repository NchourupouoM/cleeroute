# Fichier: src/cleeroute/langGraph/learners_api/quiz/routers.py

import uuid
import json
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Header
from langgraph.pregel import Pregel
from psycopg.connection_async import AsyncConnection

# 1. Importations des modèles et du graphe
from .models import (
    StartQuizRequest, AnswerRequest, AskRequest,
    QuizAttemptResponse, ChatHistoryResponse, QuizzesForCourseResponse,
    QuizQuestion, ChatMessage, QuizContent,QuizStats,
    SkipRequest, QuizQuestionInternal, QuizStateResponse
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

from src.cleeroute.langGraph.learners_api.quiz.services.user_service import get_user_profile
from src.cleeroute.langGraph.learners_api.quiz.services.user_service import build_personalization_block

from ..chats.course_context_for_global_chat import get_student_quiz_context, extract_context_from_course, fetch_course_hierarchy

from src.cleeroute.langGraph.learners_api.quiz.services.ingestion_services import FileIngestionService
from src.cleeroute.langGraph.learners_api.quiz.services.quiz_context_extractor import build_quiz_context_from_db
from src.cleeroute.langGraph.learners_api.quiz.services.quiz_services import get_quiz_state_from_db

qa_llm = ChatGoogleGenerativeAI(model=os.getenv("MODEL_2"), google_api_key=os.getenv("GEMINI_API_KEY"))


quiz_router = APIRouter()

# # create a quiz attempt
# @quiz_router.post("/quiz-attempts", response_model=QuizAttemptResponse, status_code=201, summary="Initiate a New Quiz Session",responses={
#         201: {"description": "Quiz successfully created and questions generated."},
#         500: {"description": "Failed to generate questions via AI or save to database."}
#     })
# async def start_quiz_attempt(
#     request: StartQuizRequest,
#     graph: Pregel = Depends(get_quiz_graph),
#     userId: str = Header(..., alias="userId"),
#     x_gemini_api_key: Optional[str] = Header(None, alias="X-gemini-Api-Key"),
#     db: AsyncConnection = Depends(get_app_db_connection)
# ):
#     """
#         **Starts a new interactive quiz session.**\\
        
#         This endpoint orchestrates the creation of a personalized quiz based on the provided context (course, section, or video).\\
        
#         **Process:**\\
#         1.  **AI Generation:** Invokes the LangGraph workflow to generate a unique title and a set of questions using Gemini, tailored to the learner's preferences (difficulty, count).
#         2.  **Persistence:** Saves the new quiz attempt in the application database with a status of `started`.
#         3.  **State Initialization:** Initializes a persistent LangGraph thread (`attemptId`) to manage the quiz state and chat history.
        
#         **Returns:**\\
#         - A unique `attemptId` (used for all subsequent interactions).
#         - The full list of generated questions (without answers).
#         - An empty initial chat history.
#     """
#     os.environ["GEMINI_API_KEY"] = x_gemini_api_key if x_gemini_api_key else os.getenv("GEMINI_API_KEY")

#     attempt_id = f"attempt_{uuid.uuid4()}"
#     config = {"configurable": {"thread_id": attempt_id}}
#     courseId = request.courseId

#     profile = await get_user_profile(userId, db)

#     # RECUPERATION DU CONTEXTE DEPUIS LA BDD 
#     print(f"--- [API] Fetching context for scope '{request.scope}' ---")
    
#     db_content = await build_quiz_context_from_db(
#         db=db,
#         scope=request.scope,
#         course_id=courseId,
#         section_id=request.sectionId,
#         subsection_id=request.subsectionId
#     )

#     # Le graphe a besoin de toutes ces informations pour générer le contenu.
#     context_data = {
#         "db_context": db_content,
#         "content_for_quiz": request.content_for_quiz
#     }
#     initial_state = {
#         "attemptId": attempt_id,
#         "context": context_data,
#         "preferences": request.preferences,
#         "user_answers": {},
#         "user_profile": profile.model_dump_json()
#     }
    
#     print(f"--- [API] Invoking quiz graph for attempt '{attempt_id}'... ---")
#     await graph.ainvoke(initial_state, config)

#     print(f"--- [API] Fetching final state for attempt '{attempt_id}'... ---")
#     snapshot = await graph.aget_state(config)
#     # print("snapshot", snapshot)
#     if not snapshot or not snapshot.values:
#         raise HTTPException(status_code=500, detail="Graph executed but failed to save state.")
    
#     # Récupérer directement les valeurs depuis snapshot.values
#     final_values = snapshot.values


#     quiz_title = final_values.get("title")
#     if not quiz_title or "Failed" in quiz_title:
#         # Mesure de sécurité si la génération du titre a échoué
#         quiz_title = f"Quiz on {context_data.get('scope')} '{context_data.get('sectionId', courseId)}'"

#     try:
#         await db.execute(
#             """
#             INSERT INTO quiz_attempts (attempt_id, course_id, title, status)
#             VALUES (%s, %s, %s, 'started')
#             """,
#             (attempt_id, courseId, quiz_title)
#         )
#         print(f"--- [APP DB] Successfully logged new quiz attempt with title: '{quiz_title}' ---")
#     except Exception as e:
#         print(f"--- [APP DB] FATAL ERROR: Could not save quiz attempt to application DB: {e} ---")
#         # Il est crucial de lever une erreur ici car sans enregistrement, le quiz est invalide.
#         raise HTTPException(status_code=500, detail="Failed to initiate and save the quiz session.")
        
#     questions = final_values.get("questions") # On récupère la chaîne sérialisée

#     if not questions:
#         questions_list = []
#     else:
#        # Désérialiser les questions et l'historique de chat
#         questions_str = final_values.get("questions", "[]")
#         questions_list = PydanticSerializer.loads(questions_str, List[QuizQuestion])
#         chat_history_str = final_values.get("chat_history", "[]")
#         chat_history_list = PydanticSerializer.loads(chat_history_str, List[ChatMessage])

#     return QuizAttemptResponse(
#         attemptId=attempt_id,
#         title=quiz_title,
#         questions=questions_list,
#         chatHistory=chat_history_list
#     )

@quiz_router.post("/quiz-attempts", response_model=QuizAttemptResponse, status_code=201)
async def start_quiz_attempt(
    request: StartQuizRequest,
    graph=Depends(get_quiz_graph),
    userId: str = Header(..., alias="userId"),
    x_gemini_api_key: Optional[str] = Header(None, alias="X-gemini-Api-Key"),
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
    **Initializes a new adaptive quiz session.**

    This endpoint orchestrates the creation of a personalized quiz based on the course context.
    It generates questions via AI, saves the quiz structure in the database, and initializes the chat history.

    **Headers:**
    - `userId` (required): The unique identifier of the user (for personalization).
    - `X-gemini-Api-Key` (optional): Override the default LLM API key.

    **Args:**
    - `courseId`: The UUID of the course.
    - `scope`: The context scope ('course', 'section', 'subsection', 'video').
    - `content_for_quiz`: User intent or specific topic focus.
    - `preferences`: Difficulty, question count, etc.

    **Returns (JSON):**
    - `attemptId`: UUID to be used for all subsequent interactions.
    - `questions`: List of questions (without correct answers).
    - `chatHistory`: Initial context message.
    """

    if x_gemini_api_key: os.environ["GEMINI_API_KEY"] = x_gemini_api_key

    attempt_id = f"attempt_{uuid.uuid4()}"
    config = {"configurable": {"thread_id": attempt_id}}
    
    # 1. Profil & Contexte
    profile = await get_user_profile(userId, db)
    db_content = await build_quiz_context_from_db(
        db=db, scope=request.scope, course_id=request.courseId,
        section_id=request.sectionId, subsection_id=request.subsectionId
    )
    
    initial_state = {
        "attemptId": attempt_id,
        "context": {"db_context": db_content, "content_for_quiz": request.content_for_quiz, "scope": request.scope},
        "preferences": request.preferences,
        "user_answers": {},
        "user_profile": profile.model_dump_json()
    }

    # 2. Génération via LangGraph
    print(f"--- [API] Starting Quiz '{attempt_id}' ---")
    await graph.ainvoke(initial_state, config)
    snapshot = await graph.aget_state(config)
    
    if not snapshot or not snapshot.values:
        raise HTTPException(500, "Graph execution failed")

    final_values = snapshot.values
    questions_str = final_values.get("questions", "[]")
    
    # 3. Parsing Questions & Création Historique Initial
    try:
        questions_internal = PydanticSerializer.loads(questions_str, List[QuizQuestionInternal])
        questions_json = [q.model_dump() for q in questions_internal]
    except:
        questions_json = []
        questions_internal = []

    # Le premier message de l'historique est l'intention de l'utilisateur
    intro_msg = ChatMessage(
        id=f"sys_{uuid.uuid4()}",
        sender="user", # Type spécial pour l'affichage UI
        content=request.content_for_quiz,
        type="context"
    )
    initial_chat = [intro_msg]

    # 4. Sauvegarde DB (Source of Truth)
    quiz_title = final_values.get("title", "New Quiz")
    
    try:
        await db.execute(
            """
            INSERT INTO quiz_attempts (
                attempt_id, course_id, title, status, 
                questions_json, interaction_json, user_answers_json, original_content
            )
            VALUES (%s, %s, %s, 'started', %s, %s, '{}', %s)
            """,
            (
                attempt_id, request.courseId, quiz_title, 
                json.dumps(questions_json), 
                json.dumps([intro_msg.model_dump()]), 
                request.content_for_quiz
            )
        )
        
        # Mise à jour du state LangGraph avec ce message initial
        await graph.aupdate_state(config, {"chat_history": PydanticSerializer.dumps(initial_chat)})

    except Exception as e:
        print(f"DB Error: {e}")
        raise HTTPException(500, "Failed to save quiz")

    # Retour Public (Sans les réponses)
    questions_public = [QuizQuestion(**q.model_dump()) for q in questions_internal]
    
    return QuizAttemptResponse(
        attemptId=attempt_id,
        title=quiz_title,
        questions=questions_public,
        chatHistory=initial_chat
    )

@quiz_router.get("/quiz-attempts/{attemptId}", response_model=QuizStateResponse)
async def get_quiz_attempt_state(
    attemptId: str,
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
    **Retrieves the full state of a quiz to resume a session.**

    Used when a user returns to a quiz they haven't finished, or wants to review a completed quiz.
    It restores the UI exactly as it was.

    **Args:**
    - `attemptId`: The UUID of the quiz session.

    **Returns (JSON):**
    - `questions`: The list of questions.
    - `userAnswers`: A dictionary mapping `questionId` to the user's selected index and correctness.
    - `chatHistory`: The full conversation log (hints, feedback).
    - `status`: 'started', 'in_progress', or 'completed'.
    """
    state_data = await get_quiz_state_from_db(attemptId, db)
    if not state_data:
        raise HTTPException(404, "Quiz not found")
        
    return QuizStateResponse(**state_data)




@quiz_router.post("/quiz-attempts/{attemptId}/answer", response_model=ChatHistoryResponse, summary="Submit an Answer to a Question",responses={
        200: {"description": "Answer processed and feedback returned."},
        404: {"description": "Quiz session not found (invalid attemptId)."},
        500: {"description": "Internal processing error."}
    })
async def submit_an_answer(
    attemptId: str,
    request: AnswerRequest,
    x_gemini_api_key: Optional[str] = Header(None, alias="X-gemini-Api-Key"),
    graph: Pregel = Depends(get_quiz_graph)
):
    
    """
        **Submits a user's answer for evaluation.** \\
        
        This endpoint is part of the interactive loop. It sends the user's selected option to the AI tutor.\\
        
        **Process:**\\
        1.  **Evaluation:** The AI compares the user's answer with the correct option.
        2.  **Feedback Generation:** The AI generates personalized feedback (reinforcing concepts if correct, explaining mistakes if incorrect).
        3.  **State Update:** Updates the persistent chat history and records the user's performance for this question.
        
        **Returns:**\\
        - The updated `chatHistory` containing the user's action and the AI's immediate feedback.
    """
    os.environ["GEMINI_API_KEY"] = x_gemini_api_key if x_gemini_api_key else os.getenv("GEMINI_API_KEY")

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

# Get a hint for a question
@quiz_router.get("/quiz-attempts/{attemptId}/questions/{questionId}/hint", response_model=ChatHistoryResponse,     summary="Request a Hint for a Question",responses={
        200: {"description": "Hint generated and added to chat."},
        404: {"description": "Quiz session or question not found."},
    }
)
async def get_a_hint(
    attemptId: str, 
    questionId: str,
    x_gemini_api_key: Optional[str] = Header(None, alias="X-gemini-Api-Key"),
    graph: Pregel = Depends(get_quiz_graph)
):
    """
        **Asks the AI Tutor for a hint regarding a specific question.** \\
        
        Use this when the learner is stuck. The AI provides a nudge in the right direction without revealing the full answer.\\
        
        **Process:**\\
        1.  **Context Retrieval:** Retrieves the question context from the graph state.
        2.  **AI Generation:** Generates a helpful hint based on the question's explanation.
        3.  **State Update:** Appends the hint interaction to the persistent chat history.
        
        **Returns:**\\
        - The updated `chatHistory` including the newly generated hint.
    """
    os.environ["GEMINI_API_KEY"] = x_gemini_api_key if x_gemini_api_key else os.getenv("GEMINI_API_KEY")

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

# Skip a question
@quiz_router.post("/quiz-attempts/{attemptId}/skip", response_model=ChatHistoryResponse)
async def skip_a_question(
    attemptId: str,
    request: SkipRequest,
    x_gemini_api_key: Optional[str] = Header(None, alias="X-gemini-Api-Key"),
    graph: Pregel = Depends(get_quiz_graph)
):
    """
    Allows the user to skip a question.
    This counts as a "skipped" answer and triggers AI feedback with the solution.
    """
    os.environ["GEMINI_API_KEY"] = x_gemini_api_key if x_gemini_api_key else os.getenv("GEMINI_API_KEY")

    config = {"configurable": {"thread_id": attemptId}}

    update_payload = {
        "current_interaction": {
            "type": "skip",
            "payload": {"questionId": request.questionId}
        }
    }

    try:
        final_values = await graph.ainvoke(update_payload, config)
        chat_history_str = final_values.get("chat_history", "[]")
        chat_history_list = PydanticSerializer.loads(chat_history_str, List[ChatMessage])
        return ChatHistoryResponse(chatHistory=chat_history_list)
        
    except Exception as e:
        print(f"--- ERROR in SKIP: {e} ---")
        raise HTTPException(status_code=500, detail="Failed to skip question.")

# ask a follow-up question
@quiz_router.post("/quiz-attempts/{attemptId}/ask", response_model=ChatHistoryResponse, summary="Ask a Free-form Follow-up Question",responses={
        200: {"description": "AI response generated and added to chat."},
        404: {"description": "Quiz session not found."},
    })
async def ask_follow_up_questions(
    attemptId: str, 
    request: AskRequest,
    x_gemini_api_key: Optional[str] = Header(None, alias="X-gemini-Api-Key"),
    graph: Pregel = Depends(get_quiz_graph)
):
    """
        **Allows the learner to ask a free-text question to the AI Tutor.**\\
        
        This turns the quiz into a conversational learning experience. The learner can ask for clarification on a specific question or a general concept related to the quiz.\\
        
        **Process:**\\
        1.  **Contextual Analysis:** The AI analyzes the user's query in the context of the current quiz and previous chat history.
        2.  **Response Generation:** Generates a detailed explanation or answer.
        3.  **State Update:** Appends the Q&A exchange to the chat history.
        
        **Returns:**\\
        - The updated `chatHistory` with the user's query and the AI's response.
    """
    os.environ["GEMINI_API_KEY"] = x_gemini_api_key if x_gemini_api_key else os.getenv("GEMINI_API_KEY")

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

# Get a summary of the quiz after an attempt
@quiz_router.get("/quiz-attempts/{attemptId}/summary", response_model=ChatHistoryResponse, summary="Finish Quiz and Get Summary",responses={
        200: {"description": "Quiz completed, score calculated, and summary generated."},
        404: {"description": "Quiz session not found."},
        500: {"description": "Failed to update score in database."}
    })
async def get_quiz_summary(
    attemptId: str, 
    graph: Pregel = Depends(get_quiz_graph),
    x_gemini_api_key: Optional[str] = Header(None, alias="X-gemini-Api-Key"),
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
        **Finalizes the quiz attempt and provides a performance recap.**\\
        
        This endpoint should be called when the user finishes all questions or decides to stop the quiz.\\
        
        **Process:**\\
        1.  **Scoring:** Calculates the final score (pass/fail/skipped counts) based on the session state.
        2.  **AI Recap:** Generates a personalized encouraging message and summary based on performance.
        3.  **DB Update:** Updates the `quiz_attempts` table in the application database, marking the status as `completed` and saving the score.
        4.  **Chat Finalization:** Appends a special `recap` message to the chat history.
        
        **Returns:**\\
        - The final `chatHistory` containing the summary card data.
    """
    os.environ["GEMINI_API_KEY"] = x_gemini_api_key if x_gemini_api_key else os.getenv("GEMINI_API_KEY")

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

            # 1. Extraction du texte du résumé
            recap_text = summary_message.content if summary_message.type == 'recap' else "No summary available."
            
            # 2. Sérialisation propre de l'historique pour la BDD (en liste de dicts)
            # On utilise .model_dump() pour convertir les objets Pydantic en JSON pur
            history_json = [msg.model_dump() for msg in chat_history_list]

            
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
                        completed_at = CURRENT_TIMESTAMP,
                        summary_text = %s, 
                        interaction_json = %s
                    WHERE attempt_id = %s
                    """,
                    (pass_percentage, stats.get('pass'), stats.get('fail'), stats.get('skipped'),recap_text,json.dumps(history_json), attemptId)
                )
                print(f"--- [APP DB] Successfully updated quiz attempt '{attemptId}' with final score. ---")

    except Exception as e:
        print(f"--- [APP DB] WARNING: Could not update final score for quiz attempt '{attemptId}': {e} ---")
    
    return ChatHistoryResponse(chatHistory=chat_history_list)

# # Get all messages of a specifique course
# @quiz_router.get("/courses/{courseId}/quizzes", response_model=List[QuizzesForCourseResponse], summary="Get Quiz History for a Course",responses={
#         200: {"description": "List of quizzes retrieved successfully."},
#         500: {"description": "Database error."}
#     })
# async def get_all_quizzes_for_course(
#     courseId: str,
#     db: AsyncConnection = Depends(get_app_db_connection)
# ):
#     """
#         **Retrieves the history of all quiz attempts associated with a specific course.**\\
        
#         This is a read-only endpoint used to display a list of past quizzes to the user (e.g., on a dashboard or course sidebar).\\
        
#         **Process:**\\
#         - Queries the application database (`quiz_attempts` table) filtering by the Course's `courseId`.\\
#         - Orders results by creation date (newest first).\\
        
#         **Returns:**\\
#         - A list of quiz summaries (Attempt ID, Title, Pass Percentage).
#     """
#     try:
#         # 1. On exécute la requête pour obtenir un curseur
#         cursor = await db.execute(
#             """
#                 SELECT attempt_id, title, correct_count, incorrect_count, skipped_count  \
#                 FROM quiz_attempts WHERE course_id = %s 
#                 ORDER BY created_at DESC
#             """,
#             (courseId,)
#         )
#         # 2. On attend le résultat du fetchall (qui est aussi async en psycopg 3)
#         records = await cursor.fetchall()

#     except Exception as e:
#         print(f"--- [APP DB] FATAL ERROR: Could not fetch quizzes for course '{courseId}': {e} ---")
#         raise HTTPException(status_code=500, detail="Failed to fetch quiz history.")

#     response_list = []
#     for rec in records:
#         # Gestion Tuple (par défaut psycopg) vs Dict
#         if isinstance(rec, tuple):
#             a_id, title, pass_c, fail_c, skip_c = rec[0], rec[1], rec[2] or 0, rec[3] or 0, rec[4] or 0
#         else:
#             a_id = rec["attempt_id"]
#             title = rec["title"]
#             pass_c = rec.get("correct_count", 0) or 0
#             fail_c = rec.get("incorrect_count", 0) or 0
#             skip_c = rec.get("skipped_count", 0) or 0
        
#         # Calcul du total
#         total_q = pass_c + fail_c + skip_c
        
#         # Si le total est 0 (quiz juste démarré), on peut renvoyer 0 ou essayer de deviner, 
#         # mais ici on se base sur l'historique enregistré.
        
#         response_list.append(QuizzesForCourseResponse(
#             id=a_id,
#             title=title,
#             stats=QuizStats(
#                 total=total_q,
#                 passed=pass_c,
#                 missed=fail_c,
#                 skipped=skip_c
#             )
#         ))

#     return response_list

@quiz_router.get("/courses/{courseId}/quizzes", response_model=List[QuizzesForCourseResponse])
async def get_all_quizzes_for_course(
    courseId: str,
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
    **Fetches the history of all quiz attempts for a specific course.**

    Read-only endpoint for the dashboard/sidebar to show past performance.

    **Args:**
    - `courseId`: The UUID of the course.

    **Returns (JSON List):**
    - List of quiz summaries including score statistics (passed, missed, skipped) and status.
    """
    cursor = await db.execute(
        """
        SELECT attempt_id, title, correct_count, incorrect_count, skipped_count, status, created_at
        FROM quiz_attempts WHERE course_id = %s 
        ORDER BY created_at DESC
        """,
        (courseId,)
    )
    records = await cursor.fetchall()

    response_list = []
    for rec in records:
        if isinstance(rec, tuple):
            a_id, title, pass_c, fail_c, skip_c, status, date = rec
        else:
            a_id = rec["attempt_id"]; title = rec["title"]; status = rec["status"]; date = rec["created_at"]
            pass_c = rec.get("correct_count", 0); fail_c = rec.get("incorrect_count", 0); skip_c = rec.get("skipped_count", 0)
        
        total_q = (pass_c or 0) + (fail_c or 0) + (skip_c or 0)
        
        response_list.append(QuizzesForCourseResponse(
            id=a_id, title=title, status=status, createdAt=date,
            stats=QuizStats(total=total_q, passed=pass_c or 0, missed=fail_c or 0, skipped=skip_c or 0)
        ))

    return response_list
