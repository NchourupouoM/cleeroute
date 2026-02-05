import os
from typing import Literal
from langgraph.graph import StateGraph, END
from .models import Course_meta_datas
from .state import GraphState, PydanticSerializer
from .prompt import Prompts
from googleapiclient.discovery import build
from src.cleeroute.db.checkpointer import get_checkpointer
from dotenv import load_dotenv
from src.cleeroute.langGraph.learners_api.utils import resilient_retry_policy, get_llm

load_dotenv()

# Graph Nodes
def initialize_state(state: GraphState) -> dict:
    """Initializes non-input fields of the state."""
    print("--- State Initialized ---")
    
    lang = state['language'] if 'language' in state else "English"
    return {
        'conversation_history': [],
        'current_question': None,
        'is_conversation_finished': False,
        'search_queries': [],
        'user_playlist_str': None,
        'searched_playlists_str': [],
        'merged_resources_str': [],
        'final_syllabus_options_str': None,
        'status': "starting",
        "language": lang
    }

async def intelligent_conversation(state: GraphState) -> dict:
    """Manages the conversation with the user."""
    print("--- Conducting Intelligent Conversation ---")
    history_tuples = state.get('conversation_history', [])
    history_str = "\n".join([f"Human: {h}\nAI: {a}" for h, a in history_tuples])
    llm = get_llm(api_key=os.getenv("GEMINI_API_KEY"))
    # # On désérialise les métadonnées pour les rendre lisibles
    metadata = PydanticSerializer.loads(state['metadata_str'], Course_meta_datas)

    print("language:", state['language'])
    
    prompt = Prompts.HUMAN_IN_THE_LOOP_CONVERSATION.format(
        history=history_str,
        user_input=state['user_input_text'],
        metadata=metadata.model_dump_json(indent=2),
        language=state['language']
    )

    response = await llm.ainvoke(prompt)

    content = response.content.strip()

    if "[CONVERSATION_FINISHED]" in content:
        print("--- Conversation Finished ---")

        # Le split sépare le tag du texte qui suit
        parts = content.split("[CONVERSATION_FINISHED]")

        # Si le LLM a bien mis du texte après, on le prend et on le nettoie
        closing_message = parts[1].strip() if len(parts) > 1 else ""

        # Fallback de sécurité si le message est vide (rare)
        if not closing_message:
            closing_message = "Generating course..."

        return {
            "is_conversation_finished": True, 
            "current_question": closing_message,
            "language": state["language"]
            }
    else:
        question = content
        print(f"--- Asking User: {question} ---")
        
        # On prend une copie de l'historique
        current_history = list(state.get('conversation_history', []))

        # On MET À JOUR le dernier tour avec la nouvelle question de l'IA
        if current_history:
            last_human, _ = current_history[-1]
            current_history[-1] = (last_human, question)
        else: # Cas du tout premier tour
            current_history.append(("", question))

        return {
            "is_conversation_finished": False,
            "current_question": question,
            "conversation_history": current_history,
            "language": state["language"]
        }    

def should_continue_conversation(state: GraphState) -> Literal["continue_conversation", "end_conversation"]:
    """Router node to decide if the conversation should continue."""
    print("--- Checking if Conversation Should Continue ---")
    if state.get('is_conversation_finished', False):
        return "end_conversation"
    return "continue_conversation"


def create_conversation_graph(checkpointer=None):
    """
    Creates a simple, robust graph for handling the user conversation.
    """
    checkpointer = get_checkpointer()

    workflow = StateGraph(GraphState)

    workflow.add_node("initialize", initialize_state, retry=resilient_retry_policy)
    workflow.add_node("intelligent_conversation", intelligent_conversation, retry=resilient_retry_policy)

    workflow.set_entry_point("initialize")

    workflow.add_edge("initialize", "intelligent_conversation")
    
    workflow.add_conditional_edges(
        "intelligent_conversation",
        should_continue_conversation,
        {
            "continue_conversation": "intelligent_conversation",
            "end_conversation": END
        }
    )
    
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_after=["intelligent_conversation"]
    )

