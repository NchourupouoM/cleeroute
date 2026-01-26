# In graph.py

import os
from typing import Literal, Dict, Optional
from langgraph.graph import StateGraph, END
import re
from .models import Course_meta_datas, AnalyzedPlaylist, SyllabusOptions
from .state import GraphState, PydanticSerializer
from .prompt import Prompts
import asyncio
from googleapiclient.discovery import build
from .models import VideoInfo
from .services import fast_search_youtube, fetch_playlist_light, classify_youtube_url, analyze_single_video
from .models import SyllabusOptions, CompleteCourse, AnalyzedPlaylist, VideoInfo, Section, Subsection

from src.cleeroute.db.checkpointer import get_checkpointer
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
load_dotenv()

# from utils 
from src.cleeroute.langGraph.learners_api.utils import resilient_retry_policy, get_llm


# google api
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
if not YOUTUBE_API_KEY:
    raise ValueError("YOUTUBE_API_KEY must be set in env")

def get_youtube_service():
    return build('youtube', 'v3', developerKey=os.getenv("YOUTUBE_API_KEY"))

# checkpointer = get_checkpointer()

# Graph Nodes
def initialize_state(state: GraphState) -> dict:
    """Initializes non-input fields of the state."""
    print("--- State Initialized ---")
    
    lang = state['language'] if 'language' in state else "English"
    # print(f"Initial language: {lang}")
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

async def intelligent_conversation(state: GraphState) -> dict: # <-- Retourne un dict
    """Manages the conversation with the user."""
    print("--- Conducting Intelligent Conversation ---")
    history_tuples = state.get('conversation_history', [])
    history_str = "\n".join([f"Human: {h}\nAI: {a}" for h, a in history_tuples])
    llm = get_llm()
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

        # On extrait le message après le tag
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

# --- GRAPHE 1: Conversation graph
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


# ===================== optimize graph for course generation =====================


def parse_blueprint_to_course(blueprint_str: str, video_map: dict) -> Optional[CompleteCourse]:
    """
    Parses the LLM-generated blueprint into a structured course.
    Optimized for speed: uses efficient regex and minimizes loops.
    """
    try:
        # Extract metadata
        title_match = re.search(r"Course Title: (.+)", blueprint_str)
        intro_match = re.search(r"Course Introduction: (.+)", blueprint_str)
        tag_match = re.search(r"Course Tag: (.+)", blueprint_str)

        # Validate tag
        raw_tag = tag_match.group(1).strip().lower() if tag_match else "best-of-both"
        valid_tags = {"theory-focused", "practice-focused", "best-of-both", "tooling-focused"}
        final_tag = raw_tag if raw_tag in valid_tags else "best-of-both"

        # Extract sections
        sections = []
        section_blocks = re.split(r"--- SECTION START ---", blueprint_str)

        for block in section_blocks:
            if not block.strip():
                continue

            sec_title_match = re.search(r"Section Title: (.+)", block)
            sec_desc_match = re.search(r"Section Description: (.+)", block)
            if not sec_title_match:
                continue

            # Extract subsection titles
            subsection_titles = re.findall(r"- Subsection Title: (.+)", block)
            subsections = []

            for sub_title in subsection_titles:
                sub_title_clean = sub_title.strip()
                video_data = video_map.get(sub_title_clean)

                # Fuzzy match if exact title not found
                if not video_data:
                    for original_title, v_obj in video_map.items():
                        if sub_title_clean.lower() in original_title.lower():
                            video_data = v_obj
                            break

                if video_data:
                    subsections.append(Subsection(
                        title=sub_title_clean,
                        description=video_data.description or "No description available",
                        video_url=video_data.video_url,
                        thumbnail_url=video_data.thumbnail_url,
                        channel_title=video_data.channel_title
                    ))

            if subsections:
                sections.append(Section(
                    title=sec_title_match.group(1).strip(),
                    description=sec_desc_match.group(1).strip() if sec_desc_match else "",
                    subsections=subsections
                ))

        if not sections:
            return None

        return CompleteCourse(
            title=title_match.group(1).strip() if title_match else "Generated Course",
            introduction=intro_match.group(1).strip() if intro_match else "Welcome to this course.",
            tag=final_tag,
            sections=sections
        )

    except Exception as e:
        print(f"--- Parsing Error: {e} ---")
        return None


# # --- Génération du Syllabus optimisée ---
# async def fast_syllabus_generation(state: GraphState) -> dict:
#     """
#     Generates syllabi for all playlists in parallel.
#     Optimized for speed: parallel processing and minimal fallback logic.
#     """
#     print("--- NODE: Fast Syllabus Generation (Parallel) ---")
#     merged_str = state.get('merged_resources_str', [])
#     if not merged_str:
#         return {"final_syllabus_options_str": PydanticSerializer.dumps(SyllabusOptions(syllabi=[])), "status": "generation_failed_empty"}

#     playlists = [PydanticSerializer.loads(s, AnalyzedPlaylist) for s in merged_str]
#     lang = state.get('language', 'English')
#     llm = get_llm()

#     async def process_playlist(pl: AnalyzedPlaylist):
#         if not pl.videos:
#             return None
#         video_map = {v.title.strip(): v for v in pl.videos}
#         video_list_txt = "\n".join(f"- {v.title}" for v in pl.videos)

#         prompt = Prompts.DIRECT_SYLLABUS_GENERATION.format(
#             user_input=state['user_input_text'],
#             language=lang,
#             playlist_title=pl.playlist_title,
#             playlist_videos_summary=video_list_txt
#         )

#         try:
#             response = await llm.ainvoke(prompt)
#             course = parse_blueprint_to_course(response.content, video_map)
#             return course or create_fallback_course(pl, lang)
#         except Exception as e:
#             print(f"--- LLM Error for {pl.playlist_title}: {e} ---")
#             return create_fallback_course(pl, lang)

#     # Process playlists in parallel
#     tasks = [process_playlist(pl) for pl in playlists]
#     results = await asyncio.gather(*tasks)
#     valid_courses = [c for c in results if c is not None]

#     return {
#         "final_syllabus_options_str": PydanticSerializer.dumps(SyllabusOptions(syllabi=valid_courses)),
#         "status": "completed"
#     }


# --- Génération du Syllabus optimisée ---
async def fast_syllabus_generation(state: GraphState) -> dict:
    """
    Generates syllabi for all playlists in parallel.
    Optimized for speed: parallel processing with robust timeout handling.
    """
    print("--- NODE: Fast Syllabus Generation (Parallel) ---")
    merged_str = state.get('merged_resources_str', [])
    if not merged_str:
        return {
            "final_syllabus_options_str": PydanticSerializer.dumps(SyllabusOptions(syllabi=[])), 
            "status": "generation_failed_empty"
        }

    playlists = [PydanticSerializer.loads(s, AnalyzedPlaylist) for s in merged_str]
    lang = state.get('language', 'English')
    llm = get_llm()

    async def process_playlist(pl: AnalyzedPlaylist):
        if not pl.videos:
            return None
        
        # Mapping par titre (nettoyé)
        video_map = {v.title.strip(): v for v in pl.videos}
        
        # Préparation de la liste pour le prompt (nettoyage des sauts de ligne dans les titres)
        video_list_txt = "\n".join(f"- {v.title.replace('\n', ' ')}" for v in pl.videos)

        prompt = Prompts.DIRECT_SYLLABUS_GENERATION.format(
            user_input=state['user_input_text'],
            language=lang,
            playlist_title=pl.playlist_title,
            playlist_videos_summary=video_list_txt
        )

        try:
            # --- MODIFICATION MAJEURE ICI ---
            # On augmente le timeout à 60 secondes car générer un plan pour 50+ vidéos prend du temps.
            # Sans ça, Python coupe la connexion avant que l'IA ait fini d'écrire.
            response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=60.0)
            
            # Parsing du résultat
            course = parse_blueprint_to_course(response.content, video_map)
            
            if course and len(course.sections) > 0:
                print(f"--- Blueprint Success for '{pl.playlist_title}' ---")
                return course
            else:
                print(f"--- Blueprint Invalid (Empty Sections) for '{pl.playlist_title}' -> Fallback ---")
                return create_fallback_course(pl, lang)

        except asyncio.TimeoutError:
            print(f"--- ⏳ TIMEOUT (60s) for '{pl.playlist_title}'. LLM took too long -> Fallback ---")
            return create_fallback_course(pl, lang)
            
        except Exception as e:
            print(f"--- ❌ LLM Error for '{pl.playlist_title}': {e} -> Fallback ---")
            return create_fallback_course(pl, lang)

    # Process playlists in parallel
    tasks = [process_playlist(pl) for pl in playlists]
    results = await asyncio.gather(*tasks)
    
    valid_courses = [c for c in results if c is not None]

    # Sécurité supplémentaire : si tout échoue (très rare avec le fallback), on renvoie vide proprement
    if not valid_courses:
         return {
            "final_syllabus_options_str": PydanticSerializer.dumps(SyllabusOptions(syllabi=[])), 
            "status": "generation_failed_empty"
        }

    return {
        "final_syllabus_options_str": PydanticSerializer.dumps(SyllabusOptions(syllabi=valid_courses)),
        "status": "completed",
        "merged_resources_str": [] # Nettoyage de la mémoire
    }


def create_fallback_course(playlist: AnalyzedPlaylist, language: str) -> CompleteCourse:
    """
    Generates a fallback course structure if LLM parsing fails.
    Optimized for speed: minimal logic and no complex calculations.
    """
    print(f"--- Fallback for playlist: {playlist.playlist_title} ---")
    videos = playlist.videos
    sections = []
    for i in range(0, len(videos), 5):
        chunk = videos[i:i + 5]
        sections.append(Section(
            title=f"Module {i // 5 + 1}",
            description=f"Videos {i+1}-{min(i+5, len(videos))}",
            subsections=[
                Subsection(
                    title=vid.title,
                    description=vid.description or "",
                    video_url=vid.video_url,
                    thumbnail_url=vid.thumbnail_url,
                    channel_title=vid.channel_title
                )
                for vid in chunk
            ]
        ))
    return CompleteCourse(
        title=playlist.playlist_title,
        introduction=f"Fallback course for '{playlist.playlist_title}'.",
        tag="best-of-both",
        sections=sections
    )


async def fast_data_collection(state: GraphState) -> dict:
    print("--- NODE: Fast Data Collection (Optimized) ---")
    user_links = state.get('user_input_links', [])
    user_text = state.get('user_input_text', "")
    lang = state.get('language', 'English')

    # Récupération de l'historique de conversation
    history = state.get('conversation_history', [])

    print("--- history:", history)

    playlists = []

    if user_links:
        print("--- Mode: Direct Link (Optimized) ---")
        tasks = []
        for link in user_links:
            l_type = classify_youtube_url(link)
            if l_type == 'playlist':
                tasks.append(fetch_playlist_light(link))
            elif l_type == 'video':
                tasks.append(analyze_single_video(link))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid_pl = [r for r in results if isinstance(r, AnalyzedPlaylist)]
        single_vids = [r for r in results if isinstance(r, VideoInfo)]

        playlists.extend(valid_pl)
        if single_vids:
            playlists.append(AnalyzedPlaylist(
                playlist_title="Custom Selection",
                playlist_url="https://youtube.com/custom_selection",
                videos=single_vids
            ))

    else:
        # 1. RAFFINEMENT DE LA REQUÊTE (Context Aware)
        search_query = user_text 

        if history:
            print("--- Refining search query based on conversation... ---")
            try:
                # On formate l'historique en texte
                conversation_summary = "\n".join([f"User: {h}\nAI: {a}" for h, a in history])
                
                prompt = Prompts.GENERATE_OPTIMIZED_QUERY.format(
                    user_input=user_text,
                    conversation_summary=conversation_summary,
                    language=lang
                )
                
                llm = get_llm()
                # Appel rapide (Gemini Flash est très rapide pour ça)
                response = await llm.ainvoke(prompt)
                refined_query = response.content.strip().replace('"', '')
                
                if refined_query:
                    print(f"--- Optimized Query: '{refined_query}' ---")
                    search_query = refined_query
            except Exception as e:
                print(f"--- Query Refinement Failed ({e}). Using original input. ---")

        # 2. RECHERCHE YOUTUBE (Avec la requête optimisée)
        # On passe la 'search_query' optimisée au lieu de 'user_text' brut
        ids = await fast_search_youtube(search_query, lang)

        if ids:

            # On prend slice [:2] pour être absolument sûr de ne pas dépasser 2 playlists
            target_ids = ids[:2]
            # On récupère les playlists
            fetch_tasks = [fetch_playlist_light(pid, limit=None) for pid in target_ids]
            fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            
            for res in fetch_results:
                if isinstance(res, AnalyzedPlaylist) and res.videos:
                    playlists.append(res)

    print(f"--- Data Collection: {len(playlists)} playlists found. ---")
    
    serialized = [PydanticSerializer.dumps(p) for p in playlists]
    return {"merged_resources_str": serialized, "status": "resources_merged"}


# --------------------------
# DÉFINITION DU GRAPHE RAPIDE
# --------------------------
def create_syllabus_generation_graph(checkpointer=None):
    if checkpointer is None:
        checkpointer = get_checkpointer()
    
    workflow = StateGraph(GraphState)

    workflow.add_node("fast_data_collection", fast_data_collection, retry=resilient_retry_policy)
    workflow.add_node("fast_syllabus_generation", fast_syllabus_generation, retry=resilient_retry_policy)

    workflow.set_entry_point("fast_data_collection")
    workflow.add_edge("fast_data_collection", "fast_syllabus_generation")
    workflow.add_edge("fast_syllabus_generation", END)

    return workflow.compile(checkpointer=checkpointer)