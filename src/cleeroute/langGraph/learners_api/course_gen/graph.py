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
from .services import fetch_playlist_details, search_and_filter_youtube_playlists, classify_youtube_url, analyze_single_video
# from .database import checkpointer
from src.cleeroute.db.checkpointer import get_checkpointer
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
load_dotenv()

# Initialize the LLM
llm = ChatGoogleGenerativeAI(
    model=os.getenv("MODEL_2"), 
    google_api_key=os.getenv("GEMINI_API_KEY"),
    max_tokens=8192,
    temperature=0.3
)

# google api
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
if not YOUTUBE_API_KEY:
    raise ValueError("YOUTUBE_API_KEY must be set in env")

youtube_service = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)

# checkpointer = get_checkpointer()

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
        'final_syllabus_options_str': None,
        'status': "starting"
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

    return {"search_queries": queries, "status": "search_strategy_generated"}


async def process_user_links_node(state: GraphState) -> dict:
    """
    Processes the list of user-provided links.
    It classifies each URL and fetches its content concurrently.
    It also creates a virtual playlist for single videos.
    """
    print("--- NODE: Processing User-Provided Links ---")
    user_links = state.get('user_input_links', [])
    if not user_links:
        return {}

    # 1. Créer les tâches en fonction du type d'URL
    tasks = []
    for link_str in user_links:
        url_type = classify_youtube_url(link_str)
        if url_type == 'playlist':
            tasks.append(fetch_playlist_details(link_str))
        elif url_type == 'video':
            tasks.append(analyze_single_video(link_str))
    
    # 2. Exécuter en parallèle
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 3. Fusionner les résultats
    user_playlists = []
    single_videos = []
    for res in results:
        if isinstance(res, AnalyzedPlaylist):
            user_playlists.append(res)
        elif isinstance(res, VideoInfo):
            single_videos.append(res)
        elif isinstance(res, Exception):
            print(f"--- WARNING: Failed to process a user link: {res} ---")

    # 4. Créer la playlist virtuelle
    if single_videos:
        virtual_playlist = AnalyzedPlaylist(
            playlist_title="Your Submitted Videos",
            playlist_url="http://example.com/virtual-playlist",
            videos=single_videos
        )
        user_playlists.insert(0, virtual_playlist)
    
    print(f"--- Successfully processed {len(user_playlists)} playlists from user links. ---")
    
    # On sérialise le résultat pour le stocker dans l'état
    serialized_playlists = [PydanticSerializer.dumps(p) for p in user_playlists]
    
    # Ce nœud remplit directement 'merged_resources_str' car il n'y a pas d'autre source
    return {"merged_resources_str": serialized_playlists, "status": "user_links_processed"}



async def search_resources(state: GraphState) -> dict:
    """Searches YouTube for additional playlists using the advanced search and filter service."""
    print("--- Searching for Resources ---")
    if state['search_queries']:
        try:
            playlists = await search_and_filter_youtube_playlists(
                queries=state['search_queries'],
                user_input=state['user_input_text']
            )
            print(f"--- Found and filtered {len(playlists)} high-quality playlists ---")
            return {"searched_playlists_str": [PydanticSerializer.dumps(p) for p in playlists], "status": "resources_searched"}
        except Exception as e:
            print(f"--- ERROR during search_resources: {e} ---")
            return {"searched_playlists_str": []}
    return {"searched_playlists_str": []}


def merge_resources(state: GraphState) -> dict: # <-- Retourne un dict
    """Merges user playlist and searched playlists."""
    print("--- Merging Resources ---")
    all_playlists = []
    if state.get('user_playlist_str'):
        all_playlists.append(state['user_playlist_str'])
    if state.get('searched_playlists_str'):
        all_playlists.extend(state['searched_playlists_str'])
    # On retourne UNIQUEMENT la clé que l'on veut mettre à jour.
    return {"merged_resources_str": all_playlists, "status": "resources_merged"}

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


async def plan_syllabus(state: GraphState) -> dict:
    """
    Generates a syllabus blueprint by iterating through each playlist and
    calling the LLM once per playlist for maximum reliability.
    """
    print("--- Planning Syllabus Structure (Iterative Approach) ---")
    
    merged_playlists_json_str = f"[{','.join(state.get('merged_resources_str', []))}]"
    if not merged_playlists_json_str or merged_playlists_json_str == "[]":
        return {"syllabus_blueprint_str": ""} # Cas où il n'y a aucune ressource

    # 1. Charger toutes les playlists
    playlists = PydanticSerializer.loads(merged_playlists_json_str, List[AnalyzedPlaylist])
    conversation_summary = "\n".join([f"- User: {h}\n- Assistant: {a}" for h, a in state.get('conversation_history', [])])
    
    all_blueprints = []

    # 2. BOUCLER sur chaque playlist
    for i, playlist in enumerate(playlists):
        print(f"--- Generating blueprint for playlist {i+1}/{len(playlists)}: {playlist.playlist_title} ---")
        
        # Prépare un résumé des vidéos pour cette playlist uniquement
        playlist_videos_summary = ""
        for video in playlist.videos:
            playlist_videos_summary += f'- "{video.title}"\n'
            
        # Logique de nouvelle tentative (inchangée)
        retry_instruction = state.get("retry_instruction", "")

        # 3. Appeler le LLM pour CETTE playlist
        prompt = Prompts.PLAN_SYLLABUS_WITH_PLACEHOLDERS.format(
            conversation_summary=conversation_summary,
            playlist_title=playlist.playlist_title,
            playlist_videos_summary=playlist_videos_summary,
            retry_instruction=retry_instruction
        )
        
        try:
            response = await llm.ainvoke(prompt)
            single_blueprint = response.content
            
            # Validation simple : on s'assure que le LLM n'a pas retourné une sortie vide
            if single_blueprint and "--- COURSE START ---" in single_blueprint:
                all_blueprints.append(single_blueprint)
            else:
                print(f"--- WARNING: LLM returned an empty or invalid blueprint for playlist: {playlist.playlist_title} ---")

        except Exception as e:
            print(f"--- ERROR generating blueprint for playlist {playlist.playlist_title}: {e} ---")
            continue # On passe à la playlist suivante en cas d'erreur

    # 4. Concaténer tous les blueprints générés
    final_blueprint_str = "\n\n".join(all_blueprints)
    
    print(f"--- All blueprints generated. Total length: {len(final_blueprint_str)} chars. ---")
    return {"syllabus_blueprint_str": final_blueprint_str, "status": "syllabus_planned"}


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
    return {"found_project_videos_str": found_videos_json_str, "status": "project_videos_searching"}

#blueprint validation
def validate_blueprint_node(state: GraphState) -> dict:
    """
    Valide le blueprint généré. Ce nœud ne fait que vérifier la qualité.
    """
    print("--- Validating Syllabus Blueprint ---")
    blueprint_str = state.get('syllabus_blueprint_str', '')
    
    # Critères de validation simples mais efficaces
    if blueprint_str and "Course Title:" in blueprint_str and "Section Title:" in blueprint_str:
        print("--- Blueprint is VALID. ---")
        # On ne retourne rien de spécial, la validation passe
        return {"status": "course_valid"}
    else:
        print("--- Blueprint is INVALID or EMPTY. Incrementing retry counter. ---")
        # On incrémente le compteur de tentatives
        retries = state.get('blueprint_retries', 0) + 1
        return {"syllabus_blueprint_str": "", "blueprint_retries": retries, "status": "validating_course"}

def route_after_validation(state: GraphState) -> Literal["retry_planning", "proceed_to_projects"]:
    """
    Route le flux après la validation du blueprint.
    """
    retries = state.get('blueprint_retries', 0)
    MAX_RETRIES = 2 # On se donne 2 chances (total de 3 tentatives)

    if state.get('syllabus_blueprint_str'):
        return "proceed_to_projects"
    elif retries < MAX_RETRIES:
        print(f"--- Attempt {retries + 1}. Retrying blueprint generation. ---")
        return "retry_planning"
    else:
        print(f"--- FATAL: Max retries reached. Could not generate a valid blueprint. ---")
        # On pourrait créer une branche d'erreur ici, mais pour l'instant on continue avec un plan vide
        return "proceed_to_projects"
    

async def finalize_syllabus_json(state: GraphState) -> dict:
    """
    Parses the text blueprint and assembles the final syllabus object using
    reliable Python logic, without a final LLM call.
    """
    print("--- Finalizing Syllabus JSON from Text Blueprint (Python Parser) ---")

    blueprint_str = state.get('syllabus_blueprint_str', '')
    if not blueprint_str or "No resources found" in blueprint_str:
        print("--- No valid blueprint to process. ---")
        return {"final_syllabus_options_str": PydanticSerializer.dumps(SyllabusOptions(syllabi=[]))}

    found_videos_str = state.get('found_project_videos_str', '{}')
    found_videos = PydanticSerializer.loads(found_videos_str, Dict[str, VideoInfo])
    
    # --- 1. Remplacer les placeholders dans le blueprint ---
    final_blueprint_str = blueprint_str
    for query, video in found_videos.items():
        placeholder_line = f'Placeholder: [SEARCH_FOR_PRACTICAL_VIDEO: "{query}"]'
        replacement_line = f"- Subsection Title: {video.title}"
        final_blueprint_str = final_blueprint_str.replace(placeholder_line, replacement_line)

    # --- 2. Construire la Video Map complète ---
    video_map = {}
    merged_playlists_json_str = f"[{','.join(state.get('merged_resources_str', []))}]"
    playlists = PydanticSerializer.loads(merged_playlists_json_str, List[AnalyzedPlaylist])
    for p in playlists:
        for video in p.videos:
            video_map[video.title] = video
    for video in found_videos.values():
        video_map[video.title] = video

    # --- 3. Parser le blueprint textuel en une structure de données Python ---
    try:
        syllabi_list_of_dicts = []
        # Sépare le blueprint en blocs de cours
        course_blocks = final_blueprint_str.split("--- COURSE START ---")[1:]

        for course_text in course_blocks:
            course_dict = {"title": "", "introduction": "", "tag": "", "sections": []}
            
            # Utilise des regex pour extraire les métadonnées du cours
            course_title_match = re.search(r"Course Title: (.+)", course_text)
            if course_title_match: course_dict["title"] = course_title_match.group(1).strip()
            
            intro_match = re.search(r"Course Introduction: (.+)", course_text)
            if intro_match: course_dict["introduction"] = intro_match.group(1).strip()
            
            tag_match = re.search(r"Course Tag: (.+)", course_text)
            if tag_match: course_dict["tag"] = tag_match.group(1).strip()

            # Sépare le cours en sections et projets
            parts = re.split(r"--- (SECTION|PROJECTS) START ---", course_text)
            
            # Parser les sections
            section_blocks = re.findall(r"--- SECTION START ---(.+?)(?=--- SECTION START|--- PROJECTS START|--- COURSE END)", course_text, re.DOTALL)
            for section_text in section_blocks:
                section_dict = {"title": "", "description": "", "subsections": []}
                
                title_match = re.search(r"Section Title: (.+)", section_text)
                if title_match: section_dict["title"] = title_match.group(1).strip()
                
                desc_match = re.search(r"Section Description: (.+)", section_text)
                if desc_match: section_dict["description"] = desc_match.group(1).strip()
                
                subsection_matches = re.findall(r"- Subsection Title: (.+)", section_text)
                for sub_title in subsection_matches:
                    sub_title = sub_title.strip()
                    video_data = video_map.get(sub_title)
                    if video_data:
                        section_dict["subsections"].append({
                            "title": sub_title,
                            "description": video_data.description or "",
                            "video_url": str(video_data.video_url),
                            "channel_title": video_data.channel_title,
                            "thumbnail_url": str(video_data.thumbnail_url) if video_data.thumbnail_url else None
                        })
                course_dict["sections"].append(section_dict)

            # (Logique de parsing des projets à ajouter ici si nécessaire)

            syllabi_list_of_dicts.append(course_dict)

        # --- 4. Valider la structure de données avec Pydantic ---
        # Pydantic va convertir les dictionnaires en objets et valider les types
        validated_syllabus = SyllabusOptions(syllabi=syllabi_list_of_dicts)
        
        print("--- Final Syllabus JSON Parsed and Validated Successfully ---")
        return {"final_syllabus_options_str": PydanticSerializer.dumps(validated_syllabus), "status": "organizing_course"}

    except Exception as e:
        print(f"--- FATAL ERROR during Python blueprint parsing: {e} ---")
        return {"final_syllabus_options_str": PydanticSerializer.dumps(SyllabusOptions(syllabi=[]))}

    
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
        return {"final_syllabus_options_str": PydanticSerializer.dumps(empty_syllabus), "status": "course_completed"}

    
def route_data_collection(state: GraphState) -> Literal["fetch_user_playlist", "search_new_playlists"]:
    """
    Directs the graph based on whether the user provided a YouTube link.
    This is the core of our new conditional logic.
    """
    print("--- Routing Data Collection Strategy ---")
    if state.get("user_input_links"):
        print("--- User link provided. Routing to 'fetch_user_playlist'. ---")
        return "process_user_links"
    else:
        print("--- No user link. Routing to 'search_new_playlists'. ---")
        return "search_new_playlists"


# --------------------------
# Graphs Definition
# --------------------------

# --- GRAPHE 1: Graphe de Conversation (Interactif) ---
def create_conversation_graph(checkpointer=None):
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
def create_syllabus_generation_graph(checkpointer=None):
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
    # workflow.add_node("fetch_learner_playlist", fetch_learner_playlist)
    workflow.add_node("process_user_links", process_user_links_node)

    workflow.add_node("generate_strategy", generate_search_strategy)
    workflow.add_node("search_resources", search_resources)
    workflow.add_node("merge_resources", merge_resources)

    workflow.add_node("plan_syllabus", plan_syllabus)
    workflow.add_node("find_and_search_project_videos", find_and_search_project_videos)
    workflow.add_node("finalize_syllabus_json", finalize_syllabus_json)

    # workflow.add_node("summarize_blueprint_descriptions", summarize_blueprint_descriptions_node)
    workflow.add_node("validate_blueprint", validate_blueprint_node)
    
    # --- Arêtes ---
    workflow.set_entry_point("start_generation")

    # Après le démarrage, on route la collecte de données
    workflow.add_conditional_edges(
        "start_generation", # Le point de départ de la décision
        route_data_collection, # La fonction qui prend la décision
        {
            "process_user_links": "process_user_links",
            "search_new_playlists": "generate_strategy"
        }
    )

    workflow.add_edge("process_user_links", "plan_syllabus")
    
    workflow.add_edge("generate_strategy", "search_resources")
    # workflow.add_edge("fetch_learner_playlist", "merge_resources")
    workflow.add_edge("search_resources", "merge_resources")

    # workflow.add_edge("merge_resources", "synthesize_paths")
    # workflow.add_edge("synthesize_paths", END)
    
    workflow.add_edge("merge_resources", "plan_syllabus")
    # workflow.add_edge("plan_syllabus", "summarize_blueprint_descriptions")
    workflow.add_edge("plan_syllabus", "validate_blueprint")

    # strategie de retry apres echec de construction du syllabus 
    workflow.add_conditional_edges(
        "validate_blueprint",
        route_after_validation,
        {
            "retry_planning": "plan_syllabus", # La boucle de réparation
            "proceed_to_projects": "find_and_search_project_videos"
        }
    )

    workflow.add_edge("find_and_search_project_videos", "finalize_syllabus_json")
    workflow.add_edge("finalize_syllabus_json", END)

    return workflow.compile(checkpointer=checkpointer)