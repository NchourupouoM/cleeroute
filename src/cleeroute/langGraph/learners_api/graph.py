# In app/graph.py

import os
from typing import List, Literal, Dict
import json
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
import re
from .models import Course_meta_datas, AnalyzedPlaylist, SyllabusOptions
from .state import GraphState, PydanticSerializer
from .prompt import Prompts
import asyncio
from googleapiclient.discovery import build
from .models import VideoInfo
from .services import fetch_playlist_details, search_and_filter_youtube_playlists
# from .database import checkpointer
from src.cleeroute.db.checkpointer import get_checkpointer
from dotenv import load_dotenv
load_dotenv()

# Initialize the LLM
llm = ChatGoogleGenerativeAI(
    model=os.getenv("MODEL_2"), 
    google_api_key=os.getenv("GEMINI_API_KEY"),
)

# google api
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
if not YOUTUBE_API_KEY:
    raise ValueError("YOUTUBE_API_KEY must be set in env")

youtube_service = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

checkpointer = get_checkpointer()

# --------------------------
# Graph Nodes
# --------------------------

def initialize_state(state: GraphState) -> dict: # <-- Retourne un dict
    """Initializes non-input fields of the state."""
    print("--- State Initialized ---")
    # On retourne un dictionnaire avec TOUTES les clés à initialiser.
    return {
        'conversation_history': [],
        'current_question': None,
        'is_conversation_finished': False,
        'search_queries': [],
        'user_playlist_str': None,
        'searched_playlists_str': [],
        'merged_resources_str': [],
        'final_syllabus_options_str': None
    }

async def generate_search_strategy(state: GraphState) -> dict:
    """Generates YouTube search queries based on user input."""
    print("--- Generating Search Strategy ---")
    metadata = PydanticSerializer.loads(state['metadata_str'], Course_meta_datas)

    history_tuples = state.get('conversation_history', [])
    conversation_summary = "\n".join([f"- Human: {h}\n- AI: {a}" for h, a in history_tuples])

    prompt = Prompts.GENERATE_SEARCH_STRATEGY.format(
        user_input=state['user_input_text'],
        desired_level=metadata.desired_level,
        topics=metadata.topics,
        conversation_summary=conversation_summary
    )

    response = await llm.ainvoke(prompt)
    content = response.content.strip()

    if "<analysis>" in content:
        # content = content.split("</analysis>")[-1]
        content = content.split("</analysis>")[-1].strip()
    # 2. Enlever les balises markdown
    content = content.replace("```text", "").replace("```", "").strip()

    queries = [q.strip() for q in content.split('\n') if q.strip()]

    print(f"--- Generated Queries: {queries} ---")

    return {"search_queries": queries}

async def fetch_learner_playlist(state: GraphState) -> dict:
    """Fetches the playlist provided by the user, if any."""
    print("--- Fetching User Playlist ---")
    if state.get('user_input_link'):
        playlist = await fetch_playlist_details(state['user_input_link'])
        if playlist:
            print(f"--- Fetched User Playlist: {playlist.playlist_title} ---")
            return {"user_playlist_str": PydanticSerializer.dumps(playlist)}
    return {}

async def search_resources(state: GraphState) -> dict:
    """Searches YouTube for additional playlists using the advanced search and filter service."""
    print("--- Searching for Resources ---")
    if state['search_queries']:
        # The key change is here: call the new service and pass the user_input for context.
        playlists = await search_and_filter_youtube_playlists(
            queries=state['search_queries'],
            user_input=state['user_input_text']
        )
        print(f"--- Found and filtered {len(playlists)} high-quality playlists ---")
        # On retourne UNIQUEMENT la clé que l'on veut mettre à jour.
        return {"searched_playlists_str": [PydanticSerializer.dumps(p) for p in playlists]}
    return {}


def merge_resources(state: GraphState) -> dict: # <-- Retourne un dict
    """Merges user playlist and searched playlists."""
    print("--- Merging Resources ---")
    all_playlists = []
    if state.get('user_playlist_str'):
        all_playlists.append(state['user_playlist_str'])
    if state.get('searched_playlists_str'):
        all_playlists.extend(state['searched_playlists_str'])
    # On retourne UNIQUEMENT la clé que l'on veut mettre à jour.
    return {"merged_resources_str": all_playlists}

async def intelligent_conversation(state: GraphState) -> dict: # <-- Retourne un dict
    """Manages the conversation with the user."""
    print("--- Conducting Intelligent Conversation ---")
    history_tuples = state.get('conversation_history', [])
    history_str = "\n".join([f"Human: {h}\nAI: {a}" for h, a in history_tuples])

    # # On désérialise les métadonnées pour les rendre lisibles
    metadata = PydanticSerializer.loads(state['metadata_str'], Course_meta_datas)
    
    prompt = Prompts.HUMAN_IN_THE_LOOP_CONVERSATION.format(
        history=history_str,
        user_input=state['user_input_text'],
        metadata=metadata.model_dump_json(indent=2)
    )

    response = await llm.ainvoke(prompt)

    content = response.content.strip()

    if "[CONVERSATION_FINISHED]" in content:
        print("--- Conversation Finished ---")
        return {"is_conversation_finished": True, "current_question": None}
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
            "conversation_history": current_history
        }

def should_continue_conversation(state: GraphState) -> Literal["continue_conversation", "end_conversation"]:
    """Router node to decide if the conversation should continue."""
    print("--- Checking if Conversation Should Continue ---")
    if state.get('is_conversation_finished', False):
        return "end_conversation"
    return "continue_conversation"


# --- NOUVEAU NŒUD 1: plan_syllabus ---
async def plan_syllabus(state: GraphState) -> dict:
    print("--- Planning the Syllabus Structure ---")
    
    if not state.get('merged_resources_str'):
        return {"syllabus_blueprint_str": "No resources found."}
    
    # On désérialise les données dont on a besoin
    metadata = PydanticSerializer.loads(state['metadata_str'], Course_meta_datas)
    merged_playlists_json_str = f"[{','.join(state['merged_resources_str'])}]"
    playlists = PydanticSerializer.loads(merged_playlists_json_str, List[AnalyzedPlaylist])
    conversation_summary = "\n".join([f"- User: {h}\n- Assistant: {a}" for h, a in state.get('conversation_history', [])])
    
    # Préparation du 'resources_summary'
    video_counter = 1
    # On crée une map ID -> VideoInfo pour plus tard
    video_details_map = {} 

    resources_summary = ""
    for p in playlists:
        resources_summary += f"\n--- Playlist: {p.playlist_title} ---\n"
        for video in p.videos:
            video_id = f"video_{video_counter}"
            resources_summary += f'  - Title: "{video.title}", URL: "{str(video.video_url)}" -Channel: "{video.channel_title}"\n'
            video_details_map[video_id] = video
            video_counter += 1
            
    is_single_user_playlist = len(playlists) == 1 and state.get('user_input_link') is not None

    prompt = Prompts.PLAN_SYLLABUS_WITH_PLACEHOLDERS.format(
        user_input=state['user_input_text'],
        conversation_summary=conversation_summary,
        resources_summary=resources_summary,
        is_single_user_playlist=is_single_user_playlist,
        metadata=metadata.model_dump_json(indent=2),
    )
    
    response = await llm.ainvoke(prompt)
    plan = response.content
    print("--- Syllabus Plan Created ---")
    
    # On retourne le plan (qui est déjà une chaîne)
    return {"syllabus_blueprint_str": plan}

# NŒUD 2 : RECHERCHE DE VIDÉOS-PROJETS
async def find_and_search_project_videos(state: GraphState) -> dict:
    print("--- Searching for specific project videos based on blueprint ---")
    plan_str = state.get('syllabus_blueprint_str', '')
    
    # C'est une simplification, une meilleure version parserait le plan plus en détail.
    placeholders = re.findall(r'\[SEARCH_FOR_PRACTICAL_VIDEO: "(.+?)"\]', plan_str)
    
    if not placeholders:
        print("--- No project videos to search for. ---")
        return {"found_project_videos_str": PydanticSerializer.dumps({})}

    found_videos_map = {}
    print(f"--- Found {len(placeholders)} project video placeholders to search for. ---")

    for query in placeholders:
        try:
            request = youtube_service.search().list(
                q=f"{query} tutorial project",
                part="snippet", type="video", maxResults=1, videoDuration="medium"
            )
            response = await asyncio.to_thread(request.execute)
            
            if response.get("items"):
                item = response["items"][0]
                video_id = item["id"]["videoId"]
                snippet = item["snippet"]
                thumbnails = snippet.get("thumbnails", {})
                thumbnail_url = (thumbnails.get("high", {}) or thumbnails.get("default", {})).get("url")

                video_info = VideoInfo(
                    title=snippet["title"],
                    video_url=f"https://www.youtube.com/watch?v={video_id}",
                    thumbnail_url=thumbnail_url
                )
                found_videos_map[query] = video_info
        except Exception as e:
            print(f"--- ERROR searching for video '{query}': {e} ---")
            
    found_videos_map_dicts = {
        query: video.model_dump(mode='json')
        for query, video in found_videos_map.items()
    }

    found_videos_json_str = json.dumps(found_videos_map_dicts)

    print(f"--- Found {len(found_videos_map)} project videos. ---")
    return {"found_project_videos_str": found_videos_json_str}

async def finalize_syllabus_json(state: GraphState) -> dict:
    """
    Assembles the final syllabus by combining the blueprint with found project videos,
    then calls an LLM to translate this completed plan into a valid JSON object.
    """
    print("--- Finalizing Syllabus JSON ---")
    
    # 1. Charger toutes les données nécessaires depuis l'état
    blueprint_str = state.get('syllabus_blueprint_str', '')
    found_videos_str = state.get('found_project_videos_str', '{}')
    merged_playlists_json_str = f"[{','.join(state.get('merged_resources_str', []))}]"

    # 2. Vérifier si un plan a été créé
    if not blueprint_str or "No resources found" in blueprint_str:
        print("--- No blueprint to process. Returning empty syllabus. ---")
        empty_syllabus = SyllabusOptions(syllabi=[])
        return {"final_syllabus_options_str": PydanticSerializer.dumps(empty_syllabus)}

    # 3. Désérialiser les données en objets Python
    found_videos = PydanticSerializer.loads(found_videos_str, Dict[str, VideoInfo])
    playlists = PydanticSerializer.loads(merged_playlists_json_str, List[AnalyzedPlaylist])

    # 4. Construire la "Video Map" complète (Source de vérité pour les URL)
    video_map = {}
    # Ajouter les vidéos des playlists originales
    for p in playlists:
        for video in p.videos:
            video_map[video.title] = {
                "url": str(video.video_url),
                "thumbnail_url": str(video.thumbnail_url) if video.thumbnail_url else None,
                "channel_title": video.channel_title
            }
    # Ajouter les vidéos-projets trouvées
    for video in found_videos.values():
        video_map[video.title] = {
            "url": str(video.video_url),
            "thumbnail_url": str(video.thumbnail_url) if video.thumbnail_url else None,
            "channel_title": video.channel_title
        }

    # 5. Finaliser le blueprint en remplaçant les placeholders
    final_blueprint_str = blueprint_str
    for query, video in found_videos.items():
        placeholder = f'[SEARCH_FOR_PRACTICAL_VIDEO: "{query}"]'
        final_blueprint_str = final_blueprint_str.replace(placeholder, video.title)
    
    # 6. Préparer les données pour le prompt
    conversation_summary = "\n".join([f"- User: {h}\n- Assistant: {a}" for h, a in state.get('conversation_history', [])])
    
    # On convertit en JSON pour le prompt
    found_videos_json_str = json.dumps(
        {query: video.model_dump(mode='json') for query, video in found_videos.items()},
        indent=2
    )
    video_map_json_str = json.dumps(video_map, indent=2)

    prompt = Prompts.FINALIZE_SYLLABUS_JSON.format(
        conversation_summary=conversation_summary,
        final_syllabus_plan=final_blueprint_str,
        found_project_videos=found_videos_json_str,
        video_map=video_map_json_str
    )

    # 7. Appeler le LLM avec 'with_structured_output' pour une sortie garantie
    structured_llm = llm.with_structured_output(SyllabusOptions)
    try:
        syllabus_options = await structured_llm.ainvoke(prompt)
        
        if not syllabus_options or not syllabus_options.syllabi:
            print("--- WARNING: Final LLM translation resulted in an empty syllabus. ---")
            syllabus_options = SyllabusOptions(syllabi=[])

        print("--- Final Syllabus JSON Generated Successfully ---")
        return {"final_syllabus_options_str": PydanticSerializer.dumps(syllabus_options)}
    except Exception as e:
        print(f"--- FATAL ERROR during final JSON translation: {e} ---")
        empty_syllabus = SyllabusOptions(syllabi=[])
        return {"final_syllabus_options_str": PydanticSerializer.dumps(empty_syllabus)}

# --- NOUVEAU NŒUD 2: generate_json_from_plan ---
async def generate_json_from_plan(state: GraphState) -> dict:
    print("--- Translating Plan to JSON ---")

    plan_str = state.get('syllabus_plan_str', '')
    found_videos = PydanticSerializer.loads(state.get('found_project_videos_str', '{}'), dict)
    
    final_plan_str = plan_str
    if not plan_str or "No resources found" in plan_str:
        print("--- No plan to translate. Returning empty syllabus. ---")
        empty_syllabus = SyllabusOptions(syllabi=[])
        return {"final_syllabus_options_str": PydanticSerializer.dumps(empty_syllabus)}
        
    # On a besoin de la 'video_map' ici pour la passer au LLM de traduction
    merged_playlists_json_str = f"[{','.join(state['merged_resources_str'])}]"
    playlists = PydanticSerializer.loads(merged_playlists_json_str, List[AnalyzedPlaylist])
    video_map = {video.title: str(video.video_url) for p in playlists for video in p.videos}
    video_map_json_str = json.dumps(video_map, indent=2)

    conversation_summary = "\n".join([f"- User: {h}\n- Assistant: {a}" for h, a in state.get('conversation_history', [])])
    prompt = Prompts.TRANSLATE_PLAN_TO_JSON.format(
        syllabus_plan=plan_str,
        video_map=video_map_json_str,
        conversation_summary=conversation_summary
    )
    
    structured_llm = llm.with_structured_output(SyllabusOptions)
    try:
        syllabus_options = await structured_llm.ainvoke(prompt)

        if not syllabus_options or not syllabus_options.syllabi:
            print("--- WARNING: LLM returned a valid but empty syllabus. Forcing a non-null empty result. ---")
            # On s'assure de ne JAMAIS retourner None par accident.
            syllabus_options = SyllabusOptions(syllabi=[])

        print("--- JSON Syllabus Generated Successfully ---")
        # On sérialise le résultat final avant de le retourner
        return {"final_syllabus_options_str": PydanticSerializer.dumps(syllabus_options)}
    except Exception as e:
        print(f"--- ERROR during JSON translation: {e}. Returning empty syllabus. ---")
        empty_syllabus = SyllabusOptions(syllabi=[])
        return {"final_syllabus_options_str": PydanticSerializer.dumps(empty_syllabus)}

    
def route_data_collection(state: GraphState) -> Literal["fetch_user_playlist", "search_new_playlists"]:
    """
    Directs the graph based on whether the user provided a YouTube link.
    This is the core of our new conditional logic.
    """
    print("--- Routing Data Collection Strategy ---")
    if state.get("user_input_link"):
        print("--- User link provided. Routing to 'fetch_user_playlist'. ---")
        return "fetch_user_playlist"
    else:
        print("--- No user link. Routing to 'search_new_playlists'. ---")
        return "search_new_playlists"


# --------------------------
# Graphs Definition
# --------------------------

# --- GRAPHE 1: Graphe de Conversation (Interactif) ---
def create_conversation_graph():
    """
    Creates a simple, robust graph for handling the user conversation.
    """
    workflow = StateGraph(GraphState)

    workflow.add_node("initialize", initialize_state)
    workflow.add_node("intelligent_conversation", intelligent_conversation)

    workflow.set_entry_point("initialize")

    workflow.add_edge("initialize", "intelligent_conversation")
    
    workflow.add_conditional_edges(
        "intelligent_conversation",
        should_continue_conversation,
        {
            # Quand la conversation continue, on boucle. La pause est gérée par l'interruption.
            "continue_conversation": "intelligent_conversation",
            # Quand la conversation est finie, le graphe se termine simplement.
            # L'état final sera sauvegardé avec 'is_conversation_finished: True'.
            "end_conversation": END
        }
    )
    
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_after=["intelligent_conversation"]
    )



# --- GRAPHE 2: Graphe de Génération de Syllabus (Non-Interactif) ---
def create_syllabus_generation_graph():
    """
    Creates a non-interactive graph that takes a finished conversation state
    and generates the final syllabus.
    """
    workflow = StateGraph(GraphState)

    # --- Nœuds ---
    # Un nœud de départ qui ne fait rien. Il sert de point d'entrée propre.
    def start_generation(state):
        print("--- Starting Syllabus Generation Graph ---")
        return {}
    
    workflow.add_node("start_generation", start_generation)

    # nœuds
    workflow.add_node("fetch_learner_playlist", fetch_learner_playlist)
    workflow.add_node("generate_strategy", generate_search_strategy)
    workflow.add_node("search_resources", search_resources)
    workflow.add_node("merge_resources", merge_resources)

    workflow.add_node("plan_syllabus", plan_syllabus)
    workflow.add_node("find_and_search_project_videos", find_and_search_project_videos)
    workflow.add_node("finalize_syllabus_json", finalize_syllabus_json)
    
    # --- Arêtes ---
    workflow.set_entry_point("start_generation")

    # Après le démarrage, on route la collecte de données
    workflow.add_conditional_edges(
        "start_generation", # Le point de départ de la décision
        route_data_collection, # La fonction qui prend la décision
        {
            "fetch_user_playlist": "fetch_learner_playlist",
            "search_new_playlists": "generate_strategy"
        }
    )
    
    workflow.add_edge("generate_strategy", "search_resources")
    workflow.add_edge("fetch_learner_playlist", "merge_resources")
    workflow.add_edge("search_resources", "merge_resources")

    # workflow.add_edge("merge_resources", "synthesize_paths")
    # workflow.add_edge("synthesize_paths", END)
    workflow.add_edge("merge_resources", "plan_syllabus")
    workflow.add_edge("plan_syllabus", "find_and_search_project_videos")
    workflow.add_edge("find_and_search_project_videos", "finalize_syllabus_json")
    workflow.add_edge("finalize_syllabus_json", END)

    return workflow.compile(checkpointer=checkpointer)