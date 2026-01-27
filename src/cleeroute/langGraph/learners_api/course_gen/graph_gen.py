# In graph.py

import os
from typing import Optional, List
from langgraph.graph import StateGraph, END
import re
from .models import AnalyzedPlaylist, SyllabusOptions
from .state import GraphState, PydanticSerializer
from .prompt import Prompts
import asyncio
from googleapiclient.discovery import build
from .models import VideoInfo
from .services import smart_search_and_curate, fetch_playlist_light, classify_youtube_url, analyze_single_video
from .models import SyllabusOptions, CompleteCourse, AnalyzedPlaylist, VideoInfo, Section, Subsection, CourseBlueprint
from dotenv import load_dotenv
from src.cleeroute.langGraph.learners_api.utils import resilient_retry_policy, get_llm
from langchain_core.prompts import ChatPromptTemplate


def build_course_from_blueprint(blueprint: CourseBlueprint, original_videos: List[VideoInfo]) -> CompleteCourse:
    """
    Reconstructs the course with STRICT adherence to:
    1. Original Playlist Order (0 to N).
    2. Completeness (No video left behind).
    
    Strategy: "The Zipper"
    We use the LLM's indices as 'boundaries' or 'hints', but we iterate 
    sequentially through the original video list to fill the sections.
    """
    final_sections = []
    total_videos = len(original_videos)
    
    # Pointeur pour suivre où on en est dans la liste originale (0 à N)
    current_video_cursor = 0
    
    # 1. On parcourt les sections proposées par l'IA
    for i, sec_plan in enumerate(blueprint.sections):
        
        # Si on a déjà tout traité, on arrête (ou on crée des sections vides, mais mieux vaut arrêter)
        if current_video_cursor >= total_videos:
            break

        # On nettoie les index proposés par l'IA (on enlève les hors-limites)
        valid_indices = [idx for idx in sec_plan.video_indices if 0 <= idx < total_videos]
        
        if not valid_indices:
            # Si l'IA n'a mis aucun index valide, on essaie de remplir avec le curseur actuel
            # pour ne pas avoir une section vide, ou on saute.
            # Stratégie : On prend un chunk par défaut de 3 vidéos si dispo
            end_boundary = min(current_video_cursor + 3, total_videos - 1)
        else:
            # L'IA a proposé des index. On cherche le plus grand index de cette section.
            # Cela devient notre "Frontière de fin" pour cette section.
            max_proposed_index = max(valid_indices)
            
            # Sécurité : La frontière ne peut pas reculer (Ordre strict)
            if max_proposed_index < current_video_cursor:
                # L'IA a proposé des vidéos qu'on a DÉJÀ traitées dans la section d'avant.
                # On force l'avancement d'au moins 1 vidéo ou on saute.
                max_proposed_index = current_video_cursor
            
            end_boundary = max_proposed_index

        # --- CŒUR DE LA LOGIQUE ---
        # On prend TOUTES les vidéos entre le curseur actuel et la frontière suggérée.
        # Cela remplit automatiquement les trous (Missing videos) et force l'ordre (Slicing).
        
        # Petit ajustement : end_boundary est inclusif dans la logique humaine, exclusif dans slice python
        chunk_videos = original_videos[current_video_cursor : end_boundary + 1]
        
        # Mise à jour du curseur pour la prochaine section
        current_video_cursor = end_boundary + 1
        
        # Création des sous-sections
        subsections = []
        for vid in chunk_videos:
            subsections.append(Subsection(
                title=vid.title,
                description=vid.description if vid.description else "",
                video_url=vid.video_url,
                thumbnail_url=vid.thumbnail_url,
                channel_title=vid.channel_title
            ))
            
        if subsections:
            final_sections.append(Section(
                title=sec_plan.title,
                description=sec_plan.description,
                subsections=subsections
            ))

    # 2. FILET DE SÉCURITÉ (CATCH-ALL)
    # Si après avoir fini toutes les sections de l'IA, il reste des vidéos (ex: 68 traitées sur 71)
    # On les ajoute OBLIGATOIREMENT.
    if current_video_cursor < total_videos:
        print(f"---Catch-all triggered: {total_videos - current_video_cursor} videos were left behind. Adding them now. ---")
        remaining_videos = original_videos[current_video_cursor:]
        
        subsections = [
            Subsection(
                title=v.title, 
                description=v.description[:150] + "...", 
                video_url=v.video_url, 
                thumbnail_url=v.thumbnail_url, 
                channel_title=v.channel_title
            ) for v in remaining_videos
        ]
        
        # On les ajoute à la dernière section existante ou on en crée une nouvelle "Bonus"
        if final_sections:
            final_sections[-1].subsections.extend(subsections)
            # Petit fix cosmétique : si la dernière section devient énorme, tant pis, la priorité est la complétude.
        else:
            final_sections.append(Section(
                title="Additional Modules",
                description="Remaining videos from the playlist.",
                subsections=subsections
            ))

    return CompleteCourse(
        title=blueprint.course_title,
        introduction=blueprint.course_introduction,
        tag=blueprint.course_tag,
        sections=final_sections
    )

def create_fallback_course(playlist: AnalyzedPlaylist) -> CompleteCourse:
    """Fast chunking fallback if LLM fails."""
    videos = playlist.videos
    sections = []
    chunk_size = 5
    for i in range(0, len(videos), chunk_size):
        chunk = videos[i:i + chunk_size]
        sections.append(Section(
            title=f"Part {i//chunk_size + 1}",
            description=f"Videos {i+1} to {min(i+chunk_size, len(videos))}",
            subsections=[
                Subsection(title=v.title, video_url=v.video_url, thumbnail_url=v.thumbnail_url) 
                for v in chunk
            ]
        ))
    return CompleteCourse(
        title=playlist.playlist_title, 
        introduction="Auto-generated structure.", 
        tag="practice-focused", 
        sections=sections
    )

async def fast_data_collection(state: GraphState) -> dict:
    """
    Récupération PARALLÈLE des données (recherche + détails).
    """
    print("--- NODE: Parallel Data Collection ---")
    user_links = state.get('user_input_links', [])
    user_text = state.get('user_input_text', "")
    lang = state.get('language', 'English')
    history = state.get('conversation_history', [])

    playlists = []
    fetch_tasks = [] # Liste de coroutines

    # Cas 1: Liens directs fournis par l'utilisateur
    if user_links:
        for link in user_links:
            l_type = classify_youtube_url(link)
            if l_type == 'playlist': 
                fetch_tasks.append(fetch_playlist_light(link))
            elif l_type == 'video': 
                fetch_tasks.append(analyze_single_video(link))

    # Cas 2: Recherche automatique (si pas de liens)
    else:
        conversation_summary = ""
        if history:
            conversation_summary = "\n".join([f"User: {h}\nAI: {a}" for h, a in history])
        else:
            conversation_summary = "Initial request, no conversation history."

        # Recherche des IDs (Rapide)
        ids = await smart_search_and_curate(user_text, conversation_summary, lang)
        
        # Préparation des tâches de récupération
        for pid in ids:
            fetch_tasks.append(fetch_playlist_light(pid))

    # --- EXECUTION PARALLÈLE ---
    if fetch_tasks:
        print(f"--- Fetching {len(fetch_tasks)} resources in parallel... ---")
        results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
        
        single_vids = []
        for r in results:
            if isinstance(r, AnalyzedPlaylist) and r.videos:
                playlists.append(r)
            elif isinstance(r, VideoInfo):
                single_vids.append(r)
        
        if single_vids:
            playlists.append(AnalyzedPlaylist(
                playlist_title="Custom Selection", playlist_url="http://youtube.com", videos=single_vids
            ))

    serialized = [PydanticSerializer.dumps(p) for p in playlists]
    return {"merged_resources_str": serialized, "status": "resources_merged"}


async def fast_syllabus_generation(state: GraphState) -> dict:
    """
    Génération PARALLÈLE des syllabus avec contraintes de structure.
    """
    print("--- NODE: Parallel Syllabus Generation ---")
    merged_str = state.get('merged_resources_str', [])
    if not merged_str:
        return {"status": "generation_failed_empty", "final_syllabus_options_str": None}

    playlists = [PydanticSerializer.loads(s, AnalyzedPlaylist) for s in merged_str]
    lang = state.get('language', 'English')
    user_input = state.get('user_input_text', '')
    
    llm = get_llm()
    structured_llm = llm.with_structured_output(CourseBlueprint)

    async def process_playlist_async(pl: AnalyzedPlaylist):
        if not pl.videos: return None
        
        # On envoie index et titre
        video_list_txt = "\n".join([f"[{i}] {v.title}" for i, v in enumerate(pl.videos)])
        
        prompt = ChatPromptTemplate.from_template(Prompts.STRUCTURE_GENERATION_PROMPT)
        chain = prompt | structured_llm

        try:
            print(f"--- Generating blueprint for '{pl.playlist_title}'...")
            
            blueprint = await asyncio.wait_for(
                chain.ainvoke({
                    "user_input": user_input,
                    "language": lang,
                    "playlist_title": pl.playlist_title,
                    "video_list_text": video_list_txt
                }), 
                timeout=60.0 # Timeout un peu plus long pour les grosses playlists
            )
            
            # Utilisation de la nouvelle fonction de reconstruction robuste
            return build_course_from_blueprint(blueprint, pl.videos)

        except Exception as e:
            print(f"--- Error '{pl.playlist_title}': {e} -> Fallback ---")
            return create_fallback_course(pl)

    generation_tasks = [process_playlist_async(pl) for pl in playlists]
    results = await asyncio.gather(*generation_tasks)
    
    valid_courses = [c for c in results if c is not None]

    if not valid_courses:
         return {"status": "generation_failed_empty", "final_syllabus_options_str": None}

    return {
        "final_syllabus_options_str": PydanticSerializer.dumps(SyllabusOptions(syllabi=valid_courses)),
        "status": "completed",
        "merged_resources_str": [] 
    }



def create_syllabus_generation_graph(checkpointer=None):
    wf = StateGraph(GraphState)
    wf.add_node("collection", fast_data_collection, retry=resilient_retry_policy)
    wf.add_node("generation", fast_syllabus_generation, retry=resilient_retry_policy)
    
    wf.set_entry_point("collection")
    wf.add_edge("collection", "generation")
    wf.add_edge("generation", END)
    
    return wf.compile(checkpointer=checkpointer)