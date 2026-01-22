# Fichier: src/cleeroute/langGraph/learners_api/quiz/routers.py
import json
from typing import  List
from fastapi import APIRouter, HTTPException, Depends, Header, UploadFile, File
from langgraph.pregel import Pregel
from langchain_core.messages import HumanMessage, AIMessage
from psycopg.connection_async import AsyncConnection
from typing import Optional
import uuid
import json
from fastapi.responses import StreamingResponse
from datetime import datetime
# 1. Importations des modèles et du graphe
from .models import (DeleteResponse, SessionActionResponse, MessageResponse, ChatAskRequest, ChatSessionResponse, CreateSessionRequest, EditMessageRequest, RenameSessionRequest, FileUploadResponse, FileMetadataResponse, FileContentResponse, DeleteUploadedFile)
# from .graph import get_quiz_graph

# Import du sérialiseur que nous utilisons de manière cohérente
from src.cleeroute.langGraph.learners_api.course_gen.state import PydanticSerializer
from src.cleeroute.db.app_db import get_app_db_connection, get_active_pool
from src.cleeroute.langGraph.learners_api.chats.services.tasks import ingest_transcript_by_id_task
from src.cleeroute.langGraph.learners_api.chats.services.ytbe_transcripts import TranscriptService
import os

from dotenv import load_dotenv
load_dotenv()

from .prompts import GLOBAL_CHAT_PROMPT, GENERATE_SESSION_TITLE_PROMPT


from src.cleeroute.langGraph.learners_api.quiz.services.user_service import get_user_profile
from src.cleeroute.langGraph.learners_api.quiz.services.user_service import build_personalization_block

from .course_context_for_global_chat import get_student_quiz_context, extract_context_from_course, fetch_course_hierarchy

from src.cleeroute.langGraph.learners_api.chats.services.ingestion import FileIngestionService
from src.cleeroute.langGraph.learners_api.utils import get_llm

qa_llm = get_llm(api_key=os.getenv("GEMINI_API_KEY"))


global_chat_router = APIRouter()

# Create a new session for a course with a scope define by the user
@global_chat_router.post("/courses/{courseId}/sessions", response_model=ChatSessionResponse)
async def create_global_chat_session(
    courseId: str,
    request: CreateSessionRequest,
    x_gemini_api_key: Optional[str] = Header(None, alias="X-gemini-Api-Key"),
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
    os.environ['GEMINI_API_KEY'] = x_gemini_api_key if x_gemini_api_key else os.getenv("GEMINI_API_KEY")

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
    x_gemini_api_key: Optional[str] = Header(None, alias="X-gemini-Api-Key"),
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
    # Configuration API Key dynamique si fournie
    if x_gemini_api_key:
        os.environ['GEMINI_API_KEY'] = x_gemini_api_key
        
    # 1. Personnalisation
    profile = await get_user_profile(db=db,user_id=userId)
    persona_block = build_personalization_block(profile)

    # 2. Récupération Session & Check Historique
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

    # Historique pour savoir si c'est la première interaction
    msgs_cursor = await db.execute(
        "SELECT sender, content FROM chat_messages WHERE session_id = %s ORDER BY created_at ASC",
        (sessionId,)
    )
    history_rows = await msgs_cursor.fetchall()
    is_first_interaction = (len(history_rows) == 0)

    # 3. Construction du Contexte (Cours + Quiz + Fichiers)
    try:
        course_obj = await fetch_course_hierarchy(db, str(course_id))
    except Exception as e:
        print(f"Error fetching course: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve course structure")

    context_text = extract_context_from_course(course_obj, scope, sec_idx, sub_idx, vid_id)
    student_quiz_context = await get_student_quiz_context(db, str(course_id))

    # RAG (Fichiers Uploadés)
    try:
        uploaded_docs_context = await ingestion_service.retrieve_relevant_context(
            session_id=sessionId,
            db=db
        )
    except Exception as e:
        print(f"RAG Error: {e}")
        uploaded_docs_context = ""

    # 4. Formatage Historique LangChain
    langchain_history = []
    for row in history_rows:
        sender, content = (row[0], row[1]) if isinstance(row, tuple) else (row['sender'], row['content'])
        if sender == 'user':
            langchain_history.append(HumanMessage(content=content))
        else:
            langchain_history.append(AIMessage(content=content))

    # 5. Génération LLM
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

    # 6. Sauvegarde & Renommage
    ai_message_id = str(uuid.uuid4()) # ID par défaut de sécurité

    try:
        # Insertion avec RETURNING id pour récupérer l'ID généré
        cursor = await db.execute(
            """
            INSERT INTO chat_messages (session_id, sender, content) 
            VALUES (%s, 'user', %s), (%s, 'ai', %s)
            RETURNING id
            """,
            (sessionId, request.userQuery, sessionId, answer_text)
        )
        
        # On récupère les IDs. Le 2ème est celui de l'IA (ordre d'insertion)
        inserted_ids = await cursor.fetchall()
        if inserted_ids and len(inserted_ids) >= 2:
            ai_message_id = str(inserted_ids[1][0])

        # Auto-Titling (Si première question)
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
                print(f"Title Gen Warning: {e}")
                # Fallback update date
                await db.execute("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = %s", (sessionId,))
        else:
            await db.execute("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = %s", (sessionId,))

    except Exception as e:
        print(f"DB Save Error: {e}")
        
    return MessageResponse(
        messageId=ai_message_id, # Champ corrigé
        sender="ai", 
        content=answer_text, 
        createdAt=datetime.now()
    )

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
    x_gemini_api_key: Optional[str] = Header(None, alias="X-Gemini-Api-Key"),
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
    **Edits a specific message and deletes all subsequent messages.**
    
    This allows the user to "branch" the conversation. By changing a past question,
    the old AI response and following conversation become invalid and are removed.
    
    The frontend should typically trigger a new `/ask` or `/stream` call immediately 
    after this returns, to generate the new AI response.
    """
    os.environ['GEMINI_API_KEY'] = x_gemini_api_key if x_gemini_api_key else os.getenv("GEMINI_API_KEY")
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

 # Streaming Version of the Global Chat
ingestion_service = FileIngestionService()
stream_global_chat_router = APIRouter()
@stream_global_chat_router.post("/stream-sessions/{sessionId}/ask")
async def ask_in_session_stream(
    sessionId: str,
    request: ChatAskRequest,
    userId: str = Header(..., alias="userId"),
):
    """
    Version STREAMING du chat global.
    Utilise get_active_pool() pour garantir l'accès à la DB.
    """
    transcript_service = TranscriptService()
    # 1. Récupération du Pool Global (Assurez-vous que l'app a démarré)
    try:
        pool = get_active_pool()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail="Database pool not initialized")

    # --- PHASE 1 : PRÉPARATION (Lecture avec connexion temporaire) ---
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            
            # Profil: Vérification Session & Profil
            profile = await get_user_profile(db=conn, user_id = userId)
            persona_block = build_personalization_block(profile)

            # Session Info
            await cur.execute(
                "SELECT course_id, scope, section_index, subsection_index, video_id FROM chat_sessions WHERE session_id = %s",
                (sessionId,)
            )
            session_rec = await cur.fetchone()
            if not session_rec:
                raise HTTPException(status_code=404, detail="Session not found")
            
            if isinstance(session_rec, tuple):
                course_id, scope, sec_idx, sub_idx, vid_id = session_rec
            else:
                course_id, scope, sec_idx, sub_idx, vid_id = session_rec["course_id"], session_rec["scope"], session_rec["section_index"], session_rec["subsection_index"], session_rec["video_id"]

            # Historique
            await cur.execute("SELECT sender, content FROM chat_messages WHERE session_id = %s ORDER BY created_at ASC", (sessionId,))
            history_rows = await cur.fetchall()
            is_first_interaction = (len(history_rows) == 0)
            
            langchain_history = []
            for row in history_rows:
                sender, content = (row[0], row[1]) if isinstance(row, tuple) else (row['sender'], row['content'])
                if sender == 'user': 
                    langchain_history.append(HumanMessage(content=content))
                else: 
                    langchain_history.append(AIMessage(content=content))

            # On insère le message utilisateur MAINTENANT. 
            # Il aura un timestamp T. Le message AI aura T + temps_de_generation.
            await cur.execute(
                """
                INSERT INTO chat_messages (session_id, sender, content) 
                VALUES (%s, 'user', %s)
                """,
                (sessionId, request.userQuery)
            )

            # Contextes
            try:
                course_obj = await fetch_course_hierarchy(conn, str(course_id))
                context_text = extract_context_from_course(course_obj, scope, sec_idx, sub_idx, vid_id)
                student_quiz_context = await get_student_quiz_context(conn, str(course_id))
                uploaded_docs_context = await ingestion_service.retrieve_hybrid_context(
                    session_id=sessionId, 
                    query=request.userQuery,
                    db=conn,
                    limit=5
                )
                transcript_context = ""
                # Si le frontend nous indique sur quelle vidéo l'utilisateur se trouve
                if request.currentSubsectionId:
                    try:
                        # A. Sécurité / Fallback
                        # Si le préchauffage n'a pas fini, on force l'attente ici (Fast-fail)
                        # C'est rapide si c'est déjà fait grâce au cache SQL interne du service
                        await transcript_service.ingest_transcript_if_needed(conn, request.currentSubsectionId)
                        
                        # B. Récupération sémantique (RAG)
                        # On récupère le résumé + les passages liés à la question
                        transcript_context = await transcript_service.retrieve_context(
                            db=conn,
                            subsection_id=request.currentSubsectionId,
                            user_query=request.userQuery,
                            limit=3
                        )
                        print(f"--- [Chat] Injected context for video {request.currentSubsectionId} ---")
                        
                    except Exception as e:
                        print(f"Transcript Dynamic Retrieval Error: {e}")

            except Exception as e:
                print(f"Context Warning: {e}")
                context_text = ""
                student_quiz_context = ""
                uploaded_docs_context = ""

    # --- PHASE 2 : INPUTS LLM ---
    chain = GLOBAL_CHAT_PROMPT | qa_llm
    
    chain_inputs = {
        "student_quiz_context": student_quiz_context,
        "scope": scope,
        "context_text": context_text,
        "history": langchain_history,
        "user_query": request.userQuery,
        "personalization_block": persona_block,
        "uploaded_docs_context": uploaded_docs_context,
        "transcript_context": transcript_context
    }

    # --- PHASE 3 : GÉNÉRATEUR (Streaming + Écriture) ---
    async def global_chat_generator():
        full_answer_text = ""
        try:
            # A. Streaming
            async for chunk in chain.astream(chain_inputs):
                content = chunk.content
                if content:
                    full_answer_text += content
                    yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
            
            # B. Sauvegarde (On réutilise le pool capturé au début)
            async with pool.connection() as conn_save:
                async with conn_save.cursor() as cur_save:
                    # Insert AI Messages after generation
                    await cur_save.execute(
                        "INSERT INTO chat_messages (session_id, sender, content) VALUES (%s, 'ai', %s)",
                        (sessionId, full_answer_text)
                    )
                    
                    # Auto Title
                    if is_first_interaction:
                        try:
                            title_chain = GENERATE_SESSION_TITLE_PROMPT | qa_llm
                            title_resp = await title_chain.ainvoke({"user_query": request.userQuery})
                            new_title = title_resp.content.strip().replace('"', '')
                            await cur_save.execute("UPDATE chat_sessions SET title = %s WHERE session_id = %s", (new_title, sessionId))
                        except Exception as e:
                            print(f"Title Gen Error: {e}")
                    
                    # Update Timestamp
                    await cur_save.execute("UPDATE chat_sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = %s", (sessionId,))
            
            # C. Fin
            yield f"data: {json.dumps({'type': 'end', 'status': 'completed'})}\n\n"

        except Exception as e:
            print(f"Stream Error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(global_chat_generator(), media_type="text/event-stream")

@global_chat_router.post("/subsections/{subsectionId}/prepare_transcripts", status_code=202, summary="Pre-heat Video Context")
async def prepare_video_context(
    subsectionId: str,
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
        Prepare the context for a specific video section.
        it must be execute when the video is uploaded or when the learner clicks on the video to start watching.

        args:
            subsectionId (str): The unique UUID of the current video subsession.
    """
    try:
        # 1. Vérification ultra-rapide (Index Scan)
        cursor = await db.execute("SELECT 1 FROM transcript_summaries WHERE subsection_id = %s", (subsectionId,))
        exists = await cursor.fetchone()
        
        if exists:
            return {"status": "ready", "message": "Context already available"}
        
        # 2. Si pas prêt, on lance Celery (Non-bloquant)
        ingest_transcript_by_id_task.delay(subsectionId)
        
        return {"status": "ingestion_started", "message": "Background processing started"}
        
    except Exception as e:
        # On ne veut pas casser la navigation frontend si ça échoue, on log juste
        print(f"Pre-heat Error: {e}")
        return {"status": "error", "message": str(e)}
    

# Upload files on a session chat
ingestion_service = FileIngestionService()
upload_file_router = APIRouter()

@upload_file_router.post("/sessions/{sessionId}/upload", response_model=FileUploadResponse)
async def upload_file_to_session_chat(
    sessionId: str,
    file: UploadFile = File(...),
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
        Ingest a document into the session context using Hybrid RAG strategy. \n
        1. Extracts text & Generates Summary (for UI & Context). \n
        2. Chunks & Vectorizes content (for semantic search). \n
        args: \n
            sessionId (str): The UUID of the chat session. \n
            file (UploadFile): The file to upload (PDF, Docx, Image).\n
        returns: \n
            FileUploadResponse: Metadata about the uploaded file and processing status.
    """
    # Check Session
    cursor = await db.execute("SELECT 1 FROM chat_sessions WHERE session_id = %s", (sessionId,))
    if not await cursor.fetchone():
        raise HTTPException(status_code=404, detail="Session not found")

    file_bytes = await file.read()
    
    # Limite 10MB pour éviter crash mémoire (à adapter selon infra)
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (Max 10MB)")

    try:
        result = await ingestion_service.process_file(
            session_id=sessionId,
            filename=file.filename,
            file_bytes=file_bytes,
            file_type=file.content_type,
            db=db
        )
        
        # Notification système dans le chat
        sys_msg = f"Uploaded '{file.filename}'.\nSummary: {result['summary']}"
        await db.execute(
            "INSERT INTO chat_messages (session_id, sender, content) VALUES (%s, 'system', %s)",
            (sessionId, sys_msg)
        )
        
        return FileUploadResponse(
            fileId=result["file_id"],
            filename=result["filename"],
            summary=result["summary"],
            status="processed"
        )
    except Exception as e:
        print(f"Upload Error: {e}")# ... imports (DeleteResponse) ...

        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

# --- 2. LIST (GET) ---
@upload_file_router.get("/sessions/{sessionId}/files", response_model=List[FileMetadataResponse])
async def get_session_files(
    sessionId: str,
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
        List all files for a specific chat session.
        args:
            sessionId (str): The UUID of the chat session.
        returns:
            List[FileMetadataResponse]: Metadata of all uploaded files.
    """
    cursor = await db.execute(
        """
        SELECT id, filename, file_type, summary, file_size, uploaded_at 
        FROM knowledge_files WHERE session_id = %s ORDER BY uploaded_at DESC
        """,
        (sessionId,)
    )
    rows = await cursor.fetchall()
    
    files = []
    for row in rows:
        # Mapping Tuple -> Objet
        if isinstance(row, tuple):
             f_id, f_name, f_type, f_sum, f_size, f_date = row
        else:
             f_id, f_name, f_type, f_sum, f_size, f_date = row['id'], row['filename'], row['file_type'], row['summary'], row['file_size'], row['uploaded_at']
             
        files.append(FileMetadataResponse(
            fileId=str(f_id), filename=f_name, fileType=f_type,
            summary=f_sum or "No summary", fileSize=f_size or 0, uploadedAt=f_date
        ))
    return files


# --- 3. VIEW CONTENT (GET) ---
@upload_file_router.get("/files/{fileId}", response_model=FileContentResponse)
async def get_file_content(
    fileId: str,
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
        Get the full extracted content of a specific uploaded file.
        args:
            fileId (str): The UUID of the uploaded file.
        returns:
            FileContentResponse: The filename and full extracted text.
    """
    cursor = await db.execute("SELECT filename, extracted_text FROM knowledge_files WHERE id = %s", (fileId,))
    row = await cursor.fetchone()
    
    if not row: raise HTTPException(status_code=404, detail="File not found")
    
    fname = row[0] if isinstance(row, tuple) else row['filename']
    content = row[1] if isinstance(row, tuple) else row['extracted_text']
    
    return FileContentResponse(
        fileId=fileId,
        filename=fname,
        content=content or ""
    )


# --- 4. DELETE (DELETE) ---
@upload_file_router.delete("/sessions/{sessionId}/files/{fileId}", response_model=DeleteResponse)
async def delete_file_from_session(
    sessionId: str,
    fileId: str,
    db: AsyncConnection = Depends(get_app_db_connection)
):
    """
        **Deletes an uploaded file from the session context.**

        Removes the file content and summary from the database. 
        args:
            sessionId (str): The UUID of the chat session.
            fileId (str): The UUID of the uploaded file.
        returns:
            DeleteResponse: Status of the deletion operation.
    """
    try:
        # 1. Suppression avec RETURNING pour récupérer le nom du fichier supprimé
        # Cela sert aussi de vérification d'existence
        cursor = await db.execute(
            """
            DELETE FROM knowledge_files 
            WHERE id = %s AND session_id = %s
            RETURNING filename
            """,
            (fileId, sessionId)
        )
        row = await cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="File not found or does not belong to this session.")
            
        filename = row[0] if isinstance(row, tuple) else row['filename']

        # 2. Ajout d'une notification système dans le chat (Optionnel mais recommandé pour l'UX)
        # Cela permet à l'utilisateur de voir dans l'historique quand le contexte a changé.
        await db.execute(
            """
            INSERT INTO chat_messages (session_id, sender, content) 
            VALUES (%s, 'system', %s)
            """,
            (sessionId, f"File '{filename}' removed successfully.")
        )

        return DeleteResponse(
            status="success",
            deletedCount=1,
            message=f"File '{filename}' successfully deleted."
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Delete File Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete file.")