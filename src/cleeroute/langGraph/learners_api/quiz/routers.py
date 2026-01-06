# Fichier: src/cleeroute/langGraph/learners_api/quiz/routers.py

import uuid
import json
import asyncio
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Header, UploadFile, File, BackgroundTasks
from langgraph.pregel import Pregel
from langchain_core.messages import HumanMessage, AIMessage
from psycopg.connection_async import AsyncConnection
from datetime import datetime

# 1. Importations des modèles et du graphe
from .models import (
    StartQuizRequest, AnswerRequest, AskRequest,
    QuizAttemptResponse, ChatHistoryResponse, QuizzesForCourseResponse,
    QuizQuestion, ChatMessage, QuizContent,QuizStats,
    SkipRequest, ChatAskRequest, ChatSessionResponse, CreateSessionRequest, MessageResponse, EditMessageRequest, DeleteResponse, RenameSessionRequest, SessionActionResponse
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

from src.cleeroute.langGraph.learners_api.quiz.services.user_service import get_user_profile
from src.cleeroute.langGraph.learners_api.quiz.services.user_service import build_personalization_block

from .course_context_for_global_chat import get_student_quiz_context, extract_context_from_course, fetch_course_hierarchy

from src.cleeroute.langGraph.learners_api.quiz.services.ingestion_services import FileIngestionService
from src.cleeroute.langGraph.learners_api.quiz.services.quiz_context_extractor import build_quiz_context_from_db

qa_llm = ChatGoogleGenerativeAI(model=os.getenv("MODEL_2"), google_api_key=os.getenv("GEMINI_API_KEY"))


quiz_router = APIRouter()

# create a quiz attempt
@quiz_router.post("/quiz-attempts", response_model=QuizAttemptResponse, status_code=201, summary="Initiate a New Quiz Session",responses={
        201: {"description": "Quiz successfully created and questions generated."},
        500: {"description": "Failed to generate questions via AI or save to database."}
    })
async def start_quiz_attempt(
    request: StartQuizRequest,
    graph: Pregel = Depends(get_quiz_graph),
    userId: str = Header(..., alias="userId"),
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
        **Starts a new interactive quiz session.**\\
        
        This endpoint orchestrates the creation of a personalized quiz based on the provided context (course, section, or video).\\
        
        **Process:**\\
        1.  **AI Generation:** Invokes the LangGraph workflow to generate a unique title and a set of questions using Gemini, tailored to the learner's preferences (difficulty, count).
        2.  **Persistence:** Saves the new quiz attempt in the application database with a status of `started`.
        3.  **State Initialization:** Initializes a persistent LangGraph thread (`attemptId`) to manage the quiz state and chat history.
        
        **Returns:**\\
        - A unique `attemptId` (used for all subsequent interactions).
        - The full list of generated questions (without answers).
        - An empty initial chat history.
    """
    attempt_id = f"attempt_{uuid.uuid4()}"
    config = {"configurable": {"thread_id": attempt_id}}
    courseId = request.courseId

    profile = await get_user_profile(userId, db)

    # RECUPERATION DU CONTEXTE DEPUIS LA BDD 
    print(f"--- [API] Fetching context for scope '{request.scope}' ---")
    
    db_content = await build_quiz_context_from_db(
        db=db,
        scope=request.scope,
        course_id=courseId,
        section_id=request.sectionId,
        subsection_id=request.subsectionId
    )

    # Le graphe a besoin de toutes ces informations pour générer le contenu.
    context_data = {
        "db_context": db_content,
        "content_for_quiz": request.content_for_quiz
    }
    initial_state = {
        "attemptId": attempt_id,
        "context": context_data,
        "preferences": request.preferences,
        "user_answers": {},
        "user_profile": profile.model_dump_json()
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
        quiz_title = f"Quiz on {context_data.get('scope')} '{context_data.get('sectionId', courseId)}'"

    try:
        await db.execute(
            """
            INSERT INTO quiz_attempts (attempt_id, course_id, title, status)
            VALUES (%s, %s, %s, 'started')
            """,
            (attempt_id, courseId, quiz_title)
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


@quiz_router.post("/quiz-attempts/{attemptId}/answer", response_model=ChatHistoryResponse, summary="Submit an Answer to a Question",responses={
        200: {"description": "Answer processed and feedback returned."},
        404: {"description": "Quiz session not found (invalid attemptId)."},
        500: {"description": "Internal processing error."}
    })
async def submit_an_answer(
    attemptId: str,
    request: AnswerRequest,
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
    graph: Pregel = Depends(get_quiz_graph)
):
    """
    Allows the user to skip a question.
    This counts as a "skipped" answer and triggers AI feedback with the solution.
    """
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

# Get all messages of a specifique course
@quiz_router.get("/courses/{courseId}/quizzes", response_model=List[QuizzesForCourseResponse], summary="Get Quiz History for a Course",responses={
        200: {"description": "List of quizzes retrieved successfully."},
        500: {"description": "Database error."}
    })
async def get_all_quizzes_for_course(
    courseId: str,
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
        **Retrieves the history of all quiz attempts associated with a specific course.**\\
        
        This is a read-only endpoint used to display a list of past quizzes to the user (e.g., on a dashboard or course sidebar).\\
        
        **Process:**\\
        - Queries the application database (`quiz_attempts` table) filtering by the Course's `courseId`.\\
        - Orders results by creation date (newest first).\\
        
        **Returns:**\\
        - A list of quiz summaries (Attempt ID, Title, Pass Percentage).
    """
    try:
        # 1. On exécute la requête pour obtenir un curseur
        cursor = await db.execute(
            """
                SELECT attempt_id, title, correct_count, incorrect_count, skipped_count  \
                FROM quiz_attempts WHERE course_id = %s 
                ORDER BY created_at DESC
            """,
            (courseId,)
        )
        # 2. On attend le résultat du fetchall (qui est aussi async en psycopg 3)
        records = await cursor.fetchall()

    except Exception as e:
        print(f"--- [APP DB] FATAL ERROR: Could not fetch quizzes for course '{courseId}': {e} ---")
        raise HTTPException(status_code=500, detail="Failed to fetch quiz history.")

    response_list = []
    for rec in records:
        # Gestion Tuple (par défaut psycopg) vs Dict
        if isinstance(rec, tuple):
            a_id, title, pass_c, fail_c, skip_c = rec[0], rec[1], rec[2] or 0, rec[3] or 0, rec[4] or 0
        else:
            a_id = rec["attempt_id"]
            title = rec["title"]
            pass_c = rec.get("correct_count", 0) or 0
            fail_c = rec.get("incorrect_count", 0) or 0
            skip_c = rec.get("skipped_count", 0) or 0
        
        # Calcul du total
        total_q = pass_c + fail_c + skip_c
        
        # Si le total est 0 (quiz juste démarré), on peut renvoyer 0 ou essayer de deviner, 
        # mais ici on se base sur l'historique enregistré.
        
        response_list.append(QuizzesForCourseResponse(
            id=a_id,
            title=title,
            stats=QuizStats(
                total=total_q,
                passed=pass_c,
                missed=fail_c,
                skipped=skip_c
            )
        ))

    return response_list


global_chat_router = APIRouter()

# Create a new session for a course with a scope define by the user
@global_chat_router.post("/courses/{courseId}/sessions", response_model=ChatSessionResponse)
async def create_global_chat_session(
    courseId: str,
    request: CreateSessionRequest,
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
        Creates a new persistent chat session for a specific course.\\

        The user can define the 'scope' of the conversation (Entire Course, Specific Section, 
        Subsection, or Video). The session starts with a default title (e.g., "New Chat") 
        which is auto-updated after the first interaction.\\

        Args:\\
            courseId (str): The unique UUID of the generated course.\\
            request (CreateSessionRequest): Includes the `scope`, optional indexes (section/subsection), 
                                            and an optional initial title.\\
                                                \\
        Returns:\\
            ChatSessionResponse: The metadata of the newly created session (ID, title, scope).
    """

    session_id = str(uuid.uuid4())
    try:
        await db.execute(
            """
            INSERT INTO chat_sessions 
            (session_id, course_id, title, scope, section_index, subsection_index, video_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session_id, courseId, request.title, request.scope, 
                request.sectionIndex, request.subsectionIndex, request.videoId
            )
        )
    except Exception as e:
        print(f"DB Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create session")

    return ChatSessionResponse(
        sessionId=session_id, 
        title=request.title, 
        scope=request.scope,
        updatedAt=datetime.now()
    )

# recuperer les sessions
@global_chat_router.get("/courses/{courseId}/sessions", response_model=List[ChatSessionResponse])
async def get_all_chat_sessions_of_a_course(
    courseId: str,
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
        Retrieves all chat sessions associated with a specific course.\\

        This allows the frontend to display a "History" sidebar of previous conversations, 
        ordered by the last update time.\\

        Args:\\
            courseId (str): The unique UUID of the course.\\

        Returns:\\
            List[ChatSessionResponse]: A list of sessions with their titles and scopes.
    """
    cursor = await db.execute(
        "SELECT session_id, title, scope, updated_at FROM chat_sessions WHERE course_id = %s ORDER BY updated_at DESC",
        (courseId,)
    )
    records = await cursor.fetchall()
    
    sessions = []
    for r in records:
        # Gestion tuple/dict
        val = r if isinstance(r, tuple) else (r['session_id'], r['title'], r['scope'], r['updated_at'])
        sessions.append(ChatSessionResponse(sessionId=str(val[0]), title=val[1], scope=val[2], updatedAt=val[3]))
        
    return sessions

# Get all messages of a specifique section
@global_chat_router.get("/sessions/{sessionId}/messages", response_model=List[MessageResponse])
async def get_all_messages_of_a_session(
    sessionId: str,
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
        Loads the full message history for a specific chat session.\\

        Used to repopulate the chat window when the user clicks on an existing conversation.\\

        Args:\\
            sessionId (str): The unique UUID of the chat session.\\

        Returns:\\
            List[MessageResponse]: A chronological list of messages exchanged between 'user' and 'ai'.
    """
    cursor = await db.execute(
        "SELECT id,sender, content, created_at FROM chat_messages WHERE session_id = %s ORDER BY created_at ASC",
        (sessionId,)
    )
    records = await cursor.fetchall()
    
    msgs = []
    for r in records:
        val = r if isinstance(r, tuple) else (r['sender'], r['content'], r['created_at'])
        msgs.append(MessageResponse(messageId=str(val[0]), sender=val[1], content=val[2], createdAt=val[3]))
    
    return msgs


# Chat for the entire course sessions.
@global_chat_router.post("/sessions/{sessionId}/ask", response_model=MessageResponse)
async def ask_question_in_the_global_chat_for_a_session(
    sessionId: str,
    request: ChatAskRequest,
    userId: str = Header(..., alias="userId"),
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
        Sends a user message to the AI Assistant and receives a response.\\
            \\
        This is the core logic of the Global Chat. It performs the following steps:
        1. **Context Retrieval:** Reconstructs the relevant course material (RAG) based on the session scope.
        2. **Student Profiling:** Fetches the student's recent quiz performance and struggles.
        3. **Memory Retrieval:** Loads previous messages from this session.
        4. **Generation:** Generates an answer using the LLM.
        5. **Auto-Titling:** If this is the first message, generates a relevant title for the session.
        6. **Persistence:** Saves the new user/AI message pair to the database.

        Args: \\
            sessionId (str): The unique UUID of the chat session.\\
            request (ChatAskRequest): The user's text query.

        Returns:\\
            MessageResponse: The AI's response and the creation timestamp.
    """
    profile = await get_user_profile(userId, db)
    persona_block = build_personalization_block(profile)

    # A. Récupérer les infos de la session (Scope & course_id)
    cursor = await db.execute(
        "SELECT course_id, scope, section_index, subsection_index, video_id FROM chat_sessions WHERE session_id = %s",
        (sessionId,)
    )

    # Récupérer l'historique des messages ( pour la mise a jour du titre de la session)
    msgs_cursor = await db.execute(
        "SELECT sender, content FROM chat_messages WHERE session_id = %s ORDER BY created_at ASC",
        (sessionId,)
    )
    history_rows = await msgs_cursor.fetchall()
     # --- DETECTION DU PREMIER MESSAGE ---
    # Si history_rows est vide, c'est que c'est la toute première interaction
    is_first_interaction = (len(history_rows) == 0)
    # Invocation du LLM pour la RÉPONSE 

    session_rec = await cursor.fetchone()
    if not session_rec:
        raise HTTPException(status_code=404, detail="Session not found")
        
    # Mapping des données session
    if isinstance(session_rec, tuple):
        course_id, scope, sec_idx, sub_idx, vid_id = session_rec
    else:
        course_id = session_rec["course_id"]
        scope = session_rec["scope"]
        sec_idx = session_rec["section_index"]
        sub_idx = session_rec["subsection_index"]
        vid_id = session_rec["video_id"]

    # B. Récupérer le contenu du cours (JSON complet)
    # Au lieu de SELECT course_data, on reconstruit l'objet
    try:
        course_obj = await fetch_course_hierarchy(db, str(course_id))
    except Exception as e:
        print(f"Error fetching course hierarchy: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve course structure")

    # C. Le reste du code reste identique
    context_text = extract_context_from_course(course_obj, scope, sec_idx, sub_idx, vid_id)
    student_quiz_context = await get_student_quiz_context(db, str(course_id))

    # D. Récupérer l'historique des messages pour LangChain
    msgs_cursor = await db.execute(
        "SELECT sender, content FROM chat_messages WHERE session_id = %s ORDER BY created_at ASC",
        (sessionId,)
    )
    history_rows = await msgs_cursor.fetchall()
    
    langchain_history = []
    for row in history_rows:
        sender, content = (row[0], row[1]) if isinstance(row, tuple) else (row['sender'], row['content'])
        if sender == 'user':
            langchain_history.append(HumanMessage(content=content))
        else:
            langchain_history.append(AIMessage(content=content))

    # E. Récupérer le contexte RAG des documents uploadés
    try:
        uploaded_docs_context = await ingestion_service.retrieve_relevant_context(
            session_id=sessionId,
            db=db,
        )
    except Exception as e:
        print(f"Context Retrieval Error: {e}")
        uploaded_docs_context = ""
    

    # F. Invocation du LLM
    chain = GLOBAL_CHAT_PROMPT | qa_llm
    
    try:
        ai_response = await chain.ainvoke({
            "student_quiz_context": student_quiz_context,
            "scope": scope,
            "context_text": context_text,
            "history": langchain_history,
            "user_query": request.userQuery,
            "personalization_block": persona_block,
            "uploaded_docs_context": uploaded_docs_context,
        })
        answer_text = ai_response.content
    except Exception as e:
        print(f"LLM Error: {e}")
        raise HTTPException(status_code=500, detail="AI generation failed")

    # G. Sauvegarde des messages et mise à jour de la session
    try:
        await db.execute(
            """
            INSERT INTO chat_messages (session_id, sender, content) 
            VALUES (%s, 'user', %s), (%s, 'ai', %s)
            """,
            (sessionId, request.userQuery, sessionId, answer_text)
        )

        if is_first_interaction:
            print(f"--- First interaction detected for session {sessionId}. Generating title... ---")
            try:
                # Appel LLM léger pour le titre
                title_chain = GENERATE_SESSION_TITLE_PROMPT | qa_llm
                title_response = await title_chain.ainvoke({"user_query": request.userQuery})
                new_title = title_response.content.strip().replace('"', '') # Nettoyage basique
                
                # Mise à jour du titre en BDD
                await db.execute(
                    "UPDATE chat_sessions SET title = %s, updated_at = CURRENT_TIMESTAMP WHERE session_id = %s",
                    (new_title, sessionId)
                )
            except Exception as e:
                print(f"--- WARNING: Failed to auto-generate title: {e} ---")
                # En cas d'erreur de titre, on met juste à jour la date
                await db.execute("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = %s", (sessionId,))
        else:
            # Ce n'est pas le premier message, on met juste à jour la date
            await db.execute("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = %s", (sessionId,))
    except Exception as e:
        print(f"DB Save Error: {e}")

    return MessageResponse(sender="ai", content=answer_text, createdAt=datetime.now())


# Delete a chat session
@global_chat_router.delete("/sessions/{sessionId}", response_model=SessionActionResponse, summary="Delete a Chat Session")
async def delete_a_chat_session(
    sessionId: str,
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
    **Deletes a specific chat session and all its messages.**

    This action is irreversible. Thanks to the database schema (ON DELETE CASCADE),
    all associated messages and file references (RAG) will be automatically cleaned up.

    Args:
        sessionId (str): The UUID of the session to delete.
    """
    try:
        # On utilise RETURNING pour vérifier si la ligne existait vraiment
        cursor = await db.execute(
            "DELETE FROM chat_sessions WHERE session_id = %s RETURNING session_id",
            (sessionId,)
        )
        deleted_row = await cursor.fetchone()

        if not deleted_row:
            raise HTTPException(status_code=404, detail="Session not found.")

        return SessionActionResponse(
            status="success",
            sessionId=sessionId,
            message="Session and related history deleted successfully."
        )

    except Exception as e:
        print(f"Delete Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete session.")


# Deleting all the chat sessions of a specifique course
@global_chat_router.delete("/courses/{courseId}/sessions", response_model=DeleteResponse)
async def delete_all_course_chat_sessions(
    courseId: str,
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
    **Deletes ALL chat sessions associated with a specific course.**
    
    This is a destructive action used to "reset" the chat history for a course.
    All messages and file references to the course are also removed.
    """
    try:
        # On supprime toutes les sessions liées au cours
        cursor = await db.execute(
            """
            WITH deleted_rows AS (
                DELETE FROM chat_sessions 
                WHERE course_id = %s 
                RETURNING session_id
            )
            SELECT COUNT(*) FROM deleted_rows;
            """,
            (courseId,)
        )

        count_row = await cursor.fetchone()
        count = count_row[0] if count_row else 0

        return DeleteResponse(
            status="success",
            deletedCount=count,
            message=f"Successfully deleted {count} sessions for course {courseId}."
        )

    except Exception as e:
        print(f"Delete All Sessions Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete sessions.")

#delete a message in an existing chat session.
@global_chat_router.delete("/sessions/{sessionId}/messages/{messageId}", response_model=DeleteResponse)
async def delete_a_message_in_a_session(
    sessionId: str,
    messageId: str,
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
    **Deletes a message and all subsequent messages in the thread.**
    
    This is equivalent to "Rewinding" the conversation to the point just before this message.
    """
    try:
        # 1. Récupérer le timestamp
        cursor = await db.execute(
            "SELECT created_at FROM chat_messages WHERE id = %s AND session_id = %s",
            (messageId, sessionId)
        )
        target_msg = await cursor.fetchone()
        
        if not target_msg:
            raise HTTPException(status_code=404, detail="Message not found.")
            
        target_created_at = target_msg[0] if isinstance(target_msg, tuple) else target_msg['created_at']

        # 2. Supprimer le message ET les suivants ( >= )
        cursor = await db.execute(
            """
            WITH deleted AS (
                DELETE FROM chat_messages 
                WHERE session_id = %s AND created_at >= %s
                RETURNING id
            )
            SELECT COUNT(*) FROM deleted;
            """,
            (sessionId, target_created_at)
        )
        
        count_row = await cursor.fetchone()
        count = count_row[0] if count_row else 0

        return DeleteResponse(
            status="success",
            deletedCount=count,
            message=f"Rewound conversation. Deleted {count} messages."
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Delete Message Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete message branch.")

# Edit a specific message
@global_chat_router.patch("/sessions/{sessionId}/messages/{messageId}", response_model=MessageResponse)
async def edit_message_and_truncate(
    sessionId: str,
    messageId: str,
    request: EditMessageRequest,
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
    **Edits a specific message and deletes all subsequent messages.**
    
    This allows the user to "branch" the conversation. By changing a past question,
    the old AI response and following conversation become invalid and are removed.
    
    The frontend should typically trigger a new `/ask` or `/stream` call immediately 
    after this returns, to generate the new AI response.
    """
    try:
        # 1. Récupérer le timestamp du message cible pour savoir où couper
        cursor = await db.execute(
            "SELECT created_at FROM chat_messages WHERE id = %s AND session_id = %s",
            (messageId, sessionId)
        )
        target_msg = await cursor.fetchone()
        
        if not target_msg:
            raise HTTPException(status_code=404, detail="Message not found in this session.")
            
        target_created_at = target_msg[0] if isinstance(target_msg, tuple) else target_msg['created_at']

        # 2. Supprimer tous les messages SUIVANTS (créés strictement APRÈS)
        await db.execute(
            """
            DELETE FROM chat_messages 
            WHERE session_id = %s AND created_at > %s
            """,
            (sessionId, target_created_at)
        )

        # 3. Mettre à jour le contenu du message
        cursor = await db.execute(
            """
            UPDATE chat_messages 
            SET content = %s 
            WHERE id = %s 
            RETURNING id, sender, content, created_at
            """,
            (request.newContent, messageId)
        )
        updated_row = await cursor.fetchone()
        
        # Mapping retour
        val = updated_row if isinstance(updated_row, tuple) else (updated_row['id'], updated_row['sender'], updated_row['content'], updated_row['created_at'])
        
        return MessageResponse(
            messageId=str(val[0]),
            sender=val[1],
            content=val[2],
            createdAt=val[3]
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Edit Message Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to edit message.")


# renomme the chat session title
@global_chat_router.patch("/sessions/{sessionId}/title", response_model=ChatSessionResponse, summary="Rename a Chat Session")
async def rename_chat_session_title(
    sessionId: str,
    request: RenameSessionRequest,
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
    **Updates the title of a specific chat session.**

    Useful if the user wants to organize their chats or if the auto-generated title
    was not accurate enough.

    Args:
        sessionId (str): The UUID of the session.
        request (RenameSessionRequest): Contains the new title.
    """
    try:
        # Mise à jour du titre et de la date de modification
        cursor = await db.execute(
            """
            UPDATE chat_sessions 
            SET title = %s, updated_at = CURRENT_TIMESTAMP 
            WHERE session_id = %s 
            RETURNING session_id, title, scope, updated_at
            """,
            (request.newTitle, sessionId)
        )
        updated_row = await cursor.fetchone()

        if not updated_row:
            raise HTTPException(status_code=404, detail="Session not found.")

        # Mapping du résultat (Tuple vs Dict selon la config driver)
        if isinstance(updated_row, tuple):
            s_id, s_title, s_scope, s_updated = updated_row
        else:
            s_id = updated_row["session_id"]
            s_title = updated_row["title"]
            s_scope = updated_row["scope"]
            s_updated = updated_row["updated_at"]

        return ChatSessionResponse(
            sessionId=str(s_id),
            title=s_title,
            scope=s_scope,
            updatedAt=s_updated
        )

    except Exception as e:
        print(f"Rename Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to rename session.")


ingestion_service = FileIngestionService()

# Upload a files (PDF, Docx, Image) to a session and add it to the global context
@global_chat_router.post("/sessions/{sessionId}/upload")
async def upload_file_to_session_chat(
    sessionId: str,
    file: UploadFile = File(...),
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
    Uploads a PDF, Docx, or Image, analyzes it, and stores it in the vector DB for context.
    """
    # Vérification Session (Sécurité)
    cursor = await db.execute("SELECT 1 FROM chat_sessions WHERE session_id = %s", (sessionId,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Session not found")

    # Lecture du fichier en mémoire (Attention aux gros fichiers, limite recommandée côté Nginx/FastAPI)
    file_bytes = await file.read()
    
    try:
        # Traitement
        # Note: Dans un vrai système prod, on mettrait ça dans une BackgroundTask Celery
        # pour ne pas bloquer, mais ici on attend pour confirmer le succès.
        chunk_count = await ingestion_service.process_file(
            session_id=sessionId,
            filename=file.filename,
            file_bytes=file_bytes,
            file_type=file.content_type,
            db=db
        )
        
        # Ajout d'un message système dans le chat pour dire que le fichier est prêt
        await db.execute(
            "INSERT INTO chat_messages (session_id, sender, content) VALUES (%s, 'system', %s)",
            (sessionId, f"File '{file.filename}' processed and added to context ({chunk_count} segments).")
        )
        
        return {"status": "success", "chunks_added": chunk_count, "filename": file.filename}
        
    except Exception as e:
        print(f"Upload Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")