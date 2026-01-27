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
from .services import smart_search_and_curate, fetch_playlist_light, classify_youtube_url, analyze_single_video, get_youtube_service
from .models import SyllabusOptions, CompleteCourse, AnalyzedPlaylist, VideoInfo, Section, Subsection, CourseBlueprint
from dotenv import load_dotenv
from src.cleeroute.langGraph.learners_api.utils import resilient_retry_policy, get_llm
from langchain_core.prompts import ChatPromptTemplate


def build_course_from_blueprint(blueprint: CourseBlueprint, original_videos: List[VideoInfo]) -> CompleteCourse:
    """
    Assure 100% de complétude et respect de l'ordre via 'Relay Logic'.
    """
    final_sections = []
    total_videos = len(original_videos)
    sorted_sections = sorted(blueprint.sections, key=lambda x: x.start_index)
    
    # CURSEUR DE VÉRITÉ : Indique la prochaine vidéo à traiter
    current_cursor = 0
    
    for plan in sorted_sections:
        if current_cursor >= total_videos: break

        # 1. On ignore le start_index de l'IA, on force la continuité
        actual_start = current_cursor
        
        # 2. On utilise le end_index de l'IA comme suggestion de coupe
        proposed_end = plan.end_index
        
        # 3. Validation des bornes
        actual_end = max(actual_start, min(proposed_end, total_videos - 1))
        
        # 4. Slicing Python (Garantie d'ordre absolu)
        chunk = original_videos[actual_start : actual_end + 1]
        
        current_cursor = actual_end + 1
        
        subsections = [
            Subsection(
                title=v.title,
                description=v.description if v.description else "",
                video_url=v.video_url,
                thumbnail_url=v.thumbnail_url,
                channel_title=v.channel_title
            ) for v in chunk
        ]
        
        if subsections:
            final_sections.append(Section(
                title=plan.title, description=plan.description, subsections=subsections
            ))

    # 5. CATCH-ALL : Ramassage des vidéos oubliées
    if current_cursor < total_videos:
        print(f"--- Adding remaining {total_videos - current_cursor} videos ---")
        remaining = original_videos[current_cursor:]
        subsections = [
            Subsection(title=v.title, video_url=v.video_url, thumbnail_url=v.thumbnail_url, channel_title=v.channel_title) 
            for v in remaining
        ]
        if final_sections:
            final_sections[-1].subsections.extend(subsections)
        else:
            final_sections.append(Section(title="Full Content", subsections=subsections))

    return CompleteCourse(
        title=blueprint.course_title, 
        introduction=blueprint.course_introduction,
        tag=blueprint.course_tag, 
        sections=final_sections
    )


def create_fallback_course(playlist: AnalyzedPlaylist) -> CompleteCourse:
    videos = playlist.videos
    sections = []
    CHUNK = 5
    for i in range(0, len(videos), CHUNK):
        chunk = videos[i:i + CHUNK]
        sections.append(Section(
            title=f"Module {i//CHUNK + 1}",
            description=f"Videos {i+1}-{min(i+CHUNK, len(videos))}",
            subsections=[Subsection(title=v.title, video_url=v.video_url, thumbnail_url=v.thumbnail_url) for v in chunk]
        ))
    return CompleteCourse(
        title=playlist.playlist_title, 
        introduction="Generated Structure.", 
        tag="practice-focused", sections=sections
    )

async def fast_data_collection(state: GraphState) -> dict:
    print("--- NODE: Smart Data Collection ---")
    user_links = state.get('user_input_links', [])
    user_text = state.get('user_input_text', "")
    history = state.get('conversation_history', [])
    lang = state.get('language', 'English')
    
    playlists = []
    
    # CAS A: LIENS DIRECTS (Priorité absolue)
    if user_links:
        tasks = []
        for link in user_links:
            l_type = classify_youtube_url(link)
            if l_type == 'playlist': tasks.append(fetch_playlist_light(link))
            elif l_type == 'video': tasks.append(analyze_single_video(link))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, AnalyzedPlaylist): playlists.append(r)
            elif isinstance(r, VideoInfo): 
                playlists.append(AnalyzedPlaylist(playlist_title="Custom Selection", playlist_url="http://yt.com", videos=[r]))

    # CAS B: RECHERCHE INTELLIGENTE
    else:
        # Contextualisation légère
        query = user_text
        summary = ""
        if history: 
            summary = "\n".join([f"{h} -> {a}" for h, a in history])
            query = f"{user_text} {history[-1][0]}"
        
        # 1. Recherche + Curation (Max 3s)
        # On passe le résumé de conversation pour que l'IA choisisse bien
        target_ids = await smart_search_and_curate(query, summary, lang)
        
        # 2. Fetching des résultats sélectionnés
        if target_ids:
            print(f"--- Fetching {len(target_ids)} curated playlists ---")
            fetched = await asyncio.gather(*[fetch_playlist_light(pid) for pid in target_ids])
            playlists = [p for p in fetched if p and p.videos]

    serialized = [PydanticSerializer.dumps(p) for p in playlists]
    return {"merged_resources_str": serialized, "status": "resources_merged"}


async def fast_syllabus_generation(state: GraphState) -> dict:
    print("--- NODE: Fast Syllabus Generation ---")
    merged_str = state.get('merged_resources_str', [])
    if not merged_str:
        return {"status": "generation_failed_empty", "final_syllabus_options_str": None}

    playlists = [PydanticSerializer.loads(s, AnalyzedPlaylist) for s in merged_str]
    lang = state.get('language', 'English')
    user_input = state.get('user_input_text', '')
    
    # IMPORTANT: Utiliser Gemini Flash ou équivalent rapide
    llm = get_llm() 
    structured_llm = llm.with_structured_output(CourseBlueprint)

    async def process_playlist_async(pl: AnalyzedPlaylist):
        if not pl.videos: return None
        
        # Optimisation Token: On envoie index + titre tronqué
        video_list_txt = "\n".join([f"[{i}] {v.title[:80]}" for i, v in enumerate(pl.videos)])
        
        prompt = ChatPromptTemplate.from_template(Prompts.STRUCTURE_GENERATION_PROMPT)
        chain = prompt | structured_llm

        try:
            print(f"--- Generating blueprint for '{pl.playlist_title}' ({len(pl.videos)} videos)...")
            # Le timeout peut être réduit car l'output est très court (JSON avec ranges)
            blueprint = await asyncio.wait_for(
                chain.ainvoke({
                    "user_input": user_input,
                    "language": lang,
                    "playlist_title": pl.playlist_title,
                    "video_count": len(pl.videos),
                    "max_index": len(pl.videos) - 1,
                    "video_list_text": video_list_txt
                }), 
                timeout=25.0 
            )
            return build_course_from_blueprint(blueprint, pl.videos)

        except Exception as e:
            print(f"--- Error '{pl.playlist_title}': {e} -> Fallback ---")
            return create_fallback_course(pl)

    # Exécution Parallèle
    tasks = [process_playlist_async(pl) for pl in playlists]
    results = await asyncio.gather(*tasks)
    
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