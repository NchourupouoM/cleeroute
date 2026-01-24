import json
from typing import List, Dict, Any, Optional
from psycopg.connection_async import AsyncConnection
from src.cleeroute.langGraph.learners_api.quiz.models import QuizQuestionInternal, QuizQuestion, ChatMessage

async def get_quiz_state_from_db(attempt_id: str, db: AsyncConnection) -> Optional[Dict[str, Any]]:
    """
    Récupère l'état complet du quiz pour le 'Resume'.
    """
    cursor = await db.execute(
        """
        SELECT title, status, questions_json, interaction_json, user_answers_json, original_content, 
               correct_count, incorrect_count, skipped_count
        FROM quiz_attempts 
        WHERE attempt_id = %s
        """,
        (attempt_id,)
    )
    row = await cursor.fetchone()
    if not row:
        return None
        
    # Mapping dynamique (Tuple vs Dict selon row_factory)
    if isinstance(row, tuple):
        title, status, q_json, chat_json, ans_json, intent, c_count, i_count, s_count = row
    else:
        title = row['title']
        status = row['status']
        q_json = row['questions_json']
        chat_json = row['interaction_json']
        ans_json = row['user_answers_json']
        intent = row['original_content']
        c_count = row['correct_count']
        i_count = row['incorrect_count']
        s_count = row['skipped_count']

    # 1. Reconstitution des questions
    questions_public = []
    if q_json:
        # q_json est déjà une liste de dicts grâce au driver JSONB
        questions_data = q_json if isinstance(q_json, list) else json.loads(q_json)
        # On nettoie pour le frontend (pas de réponse)
        questions_public = [
            QuizQuestion(
                questionId=q.get("questionId"),
                questionText=q.get("questionText"),
                responseIndex=q.get("responseIndex"),
                correctAnswerIndex=q.get("correctAnswerIndex"),
                options=q.get("options")
            ) for q in questions_data
        ]

    # 2. Reconstitution du Chat
    chat_history = []
    if chat_json:
        chat_data = chat_json if isinstance(chat_json, list) else json.loads(chat_json)
        chat_history = [ChatMessage(**m) for m in chat_data]

    # 3. Stats
    stats = None
    if c_count is not None:
        stats = {
            "total": len(questions_public),
            "passed": c_count,
            "missed": i_count,
            "skipped": s_count
        }

    return {
        "attemptId": attempt_id,
        "title": title,
        "status": status,
        "originalIntent": intent,
        "questions": questions_public,
        "userAnswers": ans_json if ans_json else {},
        "chatHistory": chat_history,
        "stats": stats
    }

async def save_quiz_progress(attempt_id: str, chat_history: list, user_answers: dict, db: AsyncConnection):
    """
    Sauvegarde incrémentale de l'état (Chat + Réponses).
    Appelé après chaque interaction.
    """
    # Conversion Pydantic -> Dict
    chat_dump = [c.model_dump() for c in chat_history]
    
    await db.execute(
        """
        UPDATE quiz_attempts 
        SET interaction_json = %s, 
            user_answers_json = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE attempt_id = %s
        """,
        (json.dumps(chat_dump), json.dumps(user_answers), attempt_id)
    )