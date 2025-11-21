import os
import uuid
from typing import Literal, Optional, List
from langgraph.graph import StateGraph, END
from langgraph.pregel import Pregel
import asyncio

from src.cleeroute.db.checkpointer import get_checkpointer # Votre checkpointer existant
from .models import QuizGraphState, ChatMessage,QuizContent, QuizQuestionInternal # Les modèles que nous venons de créer

from .prompts import * # Importer tous les nouveaux prompts
from langchain_google_genai import ChatGoogleGenerativeAI

from src.cleeroute.langGraph.learners_api.course_gen.state import PydanticSerializer

# Initialisation du LLM
llm = ChatGoogleGenerativeAI(model=os.getenv("MODEL_2"), google_api_key=os.getenv("GEMINI_API_KEY"))

async def generate_questions_node(state: QuizGraphState) -> dict:
    """
    Nœud d'initialisation. Génère un titre pour le quiz ET la liste complète des questions.
    """
    print(f"--- [QUIZ GRAPH] NODE: Generating Title and Questions for attempt {state['attemptId']} ---")
    context = state['context']
    prefs = state['preferences']
    content_summary = context.get('content_for_quiz')

    if not content_summary:
        print("--- FATAL ERROR: No content provided to generate quiz questions. ---")
        return {"title": "Quiz Generation Failed","questions": PydanticSerializer.dumps([])}
    
    try:
        print("--- Generating quiz content in a single LLM call... ---")
        # Prépare le prompt
        prompt = GENERATE_QUIZ_CONTENT_PROMPT.format(
            scope=context.get('scope'),
            course_title=context.get('threadId'),
            section_title=context.get('sectionId'),
            subsection_title=context.get('subsectionId'),
            content_summary=content_summary,
            difficulty=prefs.get('difficulty', 'Intermediate'),
            question_count=prefs.get('questionCount', 5)
        )
        
        # Configure le LLM pour qu'il retourne notre nouvel objet conteneur
        print("--- Configuring structured output for QuizContent... ---")
        structured_llm = llm.with_structured_output(QuizContent)
        
        # Fait l'appel unique
        print("--- Invoking LLM for quiz content generation... ---")
        quiz_content = await structured_llm.ainvoke(prompt)
        
        # Extrait les données de l'objet résultant
        quiz_title = quiz_content.title
        questions_list = quiz_content.questions
        
        print(f"--- Generated Title: '{quiz_title}' ---")
        print(f"--- Generated {len(questions_list)} questions via LLM. ---")
        
        # Retourne les données sérialisées, en utilisant les bonnes clés de l'état
        print("--- Serializing final values for graph state... ---")
        return {
            "title": quiz_title,
            "questions": PydanticSerializer.dumps(questions_list),
            "chat_history": PydanticSerializer.dumps([])
        }
        
    except Exception as e:
        print(f"--- FATAL ERROR: Could not generate quiz content in single call: {e} ---")
        return {
            "title": "Quiz Generation Failed",
            "questions": PydanticSerializer.dumps([]),
            "chat_history": PydanticSerializer.dumps([])
        }


async def process_interaction_node(state: QuizGraphState) -> dict:

    interaction = state.get("current_interaction")
    if not interaction:
        return state
    
    interaction_type = interaction["type"]
    payload = interaction["payload"]
    question_id = payload.get("questionId")

    print(f"--- [QUIZ GRAPH] NODE: Processing Interaction of type '{interaction_type}' for Q: {question_id} ---")

    try:
        questions = PydanticSerializer.loads(state["questions"], List[QuizQuestionInternal])
        chat_history = PydanticSerializer.loads(state["chat_history"], List[ChatMessage])
    except Exception as e:
        print(f"--- FATAL ERROR: Could not deserialize state: {e} ---")
        return state
    
    user_answers = state.get("user_answers", {})
    target_question = next((q for q in questions if q.questionId == question_id), None)
    if not target_question and interaction_type != 'ask':
        return state
    user_message_content = ""

    if interaction_type == "answer":
        user_answer_index = payload["answerIndex"]
        is_correct = (user_answer_index == target_question.correctAnswerIndex)
        user_answers[question_id] = {"answerIndex": user_answer_index, "isCorrect": is_correct}

        prompt = EVALUATE_ANSWER_PROMPT.format(
            question_text=target_question.questionText,
            options_str=str(target_question.options),
            correct_answer_text=target_question.options[target_question.correctAnswerIndex],
            explanation=target_question.explanation,
            student_answer_text=target_question.options[user_answer_index]
        )
        user_message_content = f"Answered question '{target_question.questionText}' with: '{target_question.options[user_answer_index]}'"

        try:
            response = await llm.ainvoke(prompt)
            ai_feedback = response.content
        except Exception as e:
            print(f"--- ERROR: Failed to get AI feedback: {e} ---")
            return state

        ai_message = ChatMessage(
            id=f"chat_{uuid.uuid4()}",
            sender="ai",
            content=ai_feedback,
            isCorrect=is_correct
        )
        chat_history.append(ai_message)
        # print(f"--- [DEBUG] chat_history length: {len(chat_history)} ---")
        # print(f"--- [DEBUG] chat_history: {chat_history} ---")

    elif interaction_type == "hint":
        prompt = GENERATE_HINT_PROMPT.format(
            question_text=target_question.questionText,
            options_str=str(target_question.options),
            explanation=target_question.explanation
        )
        user_message_content = f"Requested a hint."
        
        response = await llm.ainvoke(prompt)

        ai_message = ChatMessage(
            id=f"chat_{uuid.uuid4()}",
            sender="ai",
            content=response.content,
            type="hint"
        )
        chat_history.append(ai_message)

    elif interaction_type == "ask":
        user_query = payload["userQuery"]
        
        # On formate l'historique pour le contexte
        history_text = "\n".join([f"{msg.sender}: {msg.content}" for msg in chat_history])
        
        prompt = ANSWER_FOLLOW_UP_PROMPT.format(
            chat_history=history_text,
            question_text=target_question.questionText if target_question else "General Context",
            explanation=target_question.explanation if target_question else "N/A",
            user_query=user_query
        )
        user_message_content = user_query
        
        response = await llm.ainvoke(prompt)

        ai_message = ChatMessage(
            id=f"chat_{uuid.uuid4()}",
            sender="ai",
            content=response.content,
            type="answer"
        )
        chat_history.append(ai_message)

    user_message = ChatMessage(
        id=f"chat_{uuid.uuid4()}",
        sender="user",
        content=user_message_content
    )
    chat_history.append(user_message)

    updated_state = {
        **state,
        "chat_history": PydanticSerializer.dumps(chat_history),
        "user_answers": user_answers,
        "current_interaction": None
    }
    # print(f"--- [DEBUG] updated_state: {updated_state} ---")
    return updated_state


async def generate_summary_node(state: QuizGraphState) -> dict:
    """
    Nœud final. Calcule les statistiques et génère un texte de résumé.
    """
    print(f"--- [QUIZ GRAPH] NODE: Generating Summary ---")
    
    try:
        questions = PydanticSerializer.loads(state["questions"], List[QuizQuestionInternal])
        chat_history = PydanticSerializer.loads(state["chat_history"], List[ChatMessage])
    except Exception as e:
        print(f"--- FATAL ERROR: Could not deserialize state for summary: {e} ---")
        return {}
    
    user_answers = state["user_answers"]
    
    correct_count = sum(1 for answer in user_answers.values() if answer["isCorrect"])
    incorrect_count = len(user_answers) - correct_count
    skipped_count = len(questions) - len(user_answers)
    total_count = len(questions)

    prompt = GENERATE_SUMMARY_PROMPT.format(
        correct_count=correct_count,
        incorrect_count=incorrect_count,
        skipped_count=skipped_count,
        total_count=total_count
    )
    
    response = await llm.ainvoke(prompt)
    recap_text = response.content
    
    summary_message = ChatMessage(
        id=f"chat_{uuid.uuid4()}",
        sender="ai",
        type="recap",
        stats={"pass": correct_count, "fail": incorrect_count, "skipped": skipped_count},
        recapText=recap_text,
        content=recap_text # Le contenu peut être le même que le recapText
    )
    chat_history.append(summary_message)
    
    return {"chat_history": PydanticSerializer.dumps(chat_history)}


# ==============================================================================
# 2. DÉFINITION DU GRAPHE ET DE SON FLUX
# ==============================================================================

def should_process_interaction(state: QuizGraphState) -> Literal["process_interaction", "__end__"]:
    """
    Routeur simple. Si une action est en attente, on la traite. Sinon, on termine (on se met en pause).
    """
    if state.get("current_interaction"):
        return "process_interaction"
    return END


def route_quiz_entry(state: QuizGraphState) -> Literal["process_interaction", "generate_questions"]:
    """
    Détermine le point d'entrée du graphe en fonction de l'état/input.
    """
    # Si l'appel contient une interaction (ex: réponse, demande d'indice)
    interaction = state.get("current_interaction")
    if interaction:
        print("--- [ROUTER] Interaction is 'finish'. Routing to 'generate_summary'. ---")
        if interaction.get("type") == "finish":
            return "generate_summary"
        
        print(f"--- [ROUTER] Interaction detected. Routing to 'process_interaction'. ---")
        return "process_interaction"
    
    # Sinon, c'est un démarrage de quiz
    print(f"--- [ROUTER] No interaction. Routing to 'generate_questions'. ---")
    return "generate_questions"


# Variable globale pour le cache, comme pour les autres graphes
_quiz_graph: Optional[Pregel] = None
_quiz_graph_lock = asyncio.Lock()

async def get_quiz_graph() -> Pregel:
    """
    Construit et compile le graphe de quiz, en le mettant en cache.
    """
    global _quiz_graph
    async with _quiz_graph_lock:
        if _quiz_graph is None:
            print("--- LAZY INIT: Building quiz graph for the first time ---")
            
            # Comme cette fonction est 'async', elle s'exécute dans l'event loop principal
            # où 'get_running_loop()' réussira.
            checkpointer = get_checkpointer()
            
            workflow = StateGraph(QuizGraphState)

            # --- Ajout des Nœuds ---
            workflow.add_node("generate_questions", generate_questions_node)
            workflow.add_node("process_interaction", process_interaction_node)
            workflow.add_node("generate_summary", generate_summary_node)
            
            # --- Définition du Flux ---
            workflow.set_conditional_entry_point(
                route_quiz_entry,
                {
                    "generate_questions": "generate_questions",
                    "process_interaction": "process_interaction",
                    "generate_summary": "generate_summary"
                }
            )

            workflow.add_edge("generate_questions", END)
            workflow.add_edge("process_interaction", END)
            workflow.add_edge("generate_summary", END)

            # Compilation
            _quiz_graph = workflow.compile(checkpointer=checkpointer)
            
    return _quiz_graph
