# In app/services.py

import os
import json
from typing import List, Optional
import asyncio
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from langchain_google_genai import ChatGoogleGenerativeAI

from .models import AnalyzedPlaylist, VideoInfo, FilteredPlaylistSelection
from .prompt import Prompts

from dotenv import load_dotenv
load_dotenv()

# It's good practice to initialize the LLM and YouTube service once
# if the service is called multiple times.
llm = ChatGoogleGenerativeAI(model=os.getenv("MODEL_2"), google_api_key=os.getenv("GEMINI_API_KEY"), max_tokens=8192)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
if not YOUTUBE_API_KEY:
    raise ValueError("YOUTUBE_API_KEY must be set in env")

youtube_service = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)


async def fetch_playlist_details(playlist_url: str) -> Optional[AnalyzedPlaylist]:
    """
    Fetches details for a single playlist given its full URL.
    Extracts the playlist ID from the URL.
    """
    try:
        playlist_id = playlist_url.split("list=")[1]
        return await _fetch_playlist_items(playlist_id)
    except (IndexError, HttpError) as e:
        print(f"Error fetching or parsing playlist URL {playlist_url}: {e}")
        return None

async def _fetch_playlist_items(playlist_id: str) -> Optional[AnalyzedPlaylist]:
    """
    Helper function to fetch all videos from a given playlist ID, handling pagination.
    """
    try:
        # First, get playlist metadata (title)
        playlist_request = youtube_service.playlists().list(
            part="snippet",
            id=playlist_id
        )
        playlist_response = playlist_request.execute()

        if not playlist_response.get("items"):
            print(f"--- WARNING: Playlist with ID {playlist_id} not found or is empty. Skipping. ---")
            return None # On retourne None si la playlist est invalide

        playlist_info = playlist_response['items'][0]['snippet']
        playlist_title = playlist_info['title']
        playlist_description = playlist_info.get('description')

        video_infos: List[VideoInfo] = []
        next_page_token = None

        # Loop to handle pagination for playlists with more than 50 videos
        while True:
            request = youtube_service.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=playlist_id,
                maxResults=50,  # Max allowed value
                pageToken=next_page_token
            )
            response = request.execute()

            for item in response.get("items", []):
                snippet = item.get("snippet", {})
                video_id = snippet.get("resourceId", {}).get("videoId")
                if video_id:
                    # recuperation de la miniature
                    thumbnails = snippet.get("thumbnails", {})
                    thumbnail_url = (
                        thumbnails.get("maxres", {}) or
                        thumbnails.get("standard", {}) or
                        thumbnails.get("high", {}) or
                        thumbnails.get("medium", {}) or
                        thumbnails.get("default", {})
                    ).get("url")

                    video_infos.append(
                        VideoInfo(
                            title=snippet.get("title"),
                            description=snippet.get("description"),
                            video_url=f"https://www.youtube.com/watch?v={video_id}",
                            channel_title=snippet.get("videoOwnerChannelTitle"),
                            thumbnail_url=thumbnail_url,
                        )
                    )
            
            next_page_token = response.get('nextPageToken')
            if not next_page_token:
                break
        
        return AnalyzedPlaylist(
            playlist_title=playlist_title,
            playlist_url=f"https://www.youtube.com/playlist?list={playlist_id}",
            playlist_description=playlist_description,
            videos=video_infos
        )

    except HttpError as e:
        print(f"An HTTP error {e.resp.status} occurred while fetching playlist {playlist_id}: {e.content}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while fetching playlist {playlist_id}: {e}")
        return None

async def search_and_filter_youtube_playlists(
    queries: List[str], 
    user_input: str,
    max_candidates_per_query: int = 50,
    max_final_playlists: int = 10
) -> List[AnalyzedPlaylist]:
    """
    Performs a high-quality, multi-step search for YouTube playlists.
    1. Searches for candidate playlists for each query.
    2. Uses an LLM to filter and select the most relevant candidates.
    3. Fetches full details for only the selected playlists.
    """
    print("--- Starting High-Quality YouTube Search ---")

    # 1. Recherche des candidats en parallèle
    def search_task(query: str):
        try:
            request = youtube_service.search().list(
                q=query, part="snippet", type="playlist", maxResults=max_candidates_per_query, order="date"
            )
            return request.execute()
        except HttpError as e:
            print(f"An HTTP error occurred during search for '{query}': {e}")
            return None

    search_tasks = [asyncio.to_thread(search_task, query) for query in queries]
    search_results = await asyncio.gather(*search_tasks)
    
    # 1. Search for candidate playlists (cette partie est correcte)
    candidate_playlists = []
    unique_ids = set()
    
    for response in search_results:
        if response:
            for item in response.get("items", []):
                playlist_id = item["id"]["playlistId"]
                if playlist_id not in unique_ids:
                    snippet = item["snippet"]
                    candidate_playlists.append({
                        "id": playlist_id,
                        "title": snippet["title"],
                        "description": snippet["description"],
                        "publishedAt": snippet["publishedAt"]
                    })
                    unique_ids.add(playlist_id)

    if not candidate_playlists:
        print("--- No playlist candidates found. ---")
        return []
    
    # 2. TRIER TOUS LES CANDIDATS PAR DATE (la nouveauté d'abord)
    candidate_playlists.sort(key=lambda p: p['publishedAt'], reverse=True)

    # On prend les 40 plus récents pour les envoyer au LLM (optimisation)
    newest_candidates = candidate_playlists[:40]
    print(f"--- Found {len(candidate_playlists)} total candidates. Selecting the 40 newest for LLM filtering. ---")

     # 3. Filtrage par le LLM (sur la liste des plus récents)
    candidates_str = json.dumps(newest_candidates, indent=2)

    prompt = Prompts.FILTER_YOUTUBE_PLAYLISTS.format(
        user_input=user_input,
        playlist_candidates=candidates_str
    )
    
    selected_ids = []
    try:
        # On utilise 'with_structured_output' pour garantir une sortie JSON.
        # C'est la méthode la plus fiable.
        structured_llm = llm.with_structured_output(FilteredPlaylistSelection)
        
        # APPEL CORRECT AU LLM
        llm_response = await asyncio.wait_for(structured_llm.ainvoke(prompt), timeout=60.0)
        
        
        if llm_response and hasattr(llm_response, 'selected_ids'):
            selected_ids = llm_response.selected_ids
            print(f"--- LLM selected {len(selected_ids)} playlists: {selected_ids} ---")
        else:
            # Si llm_response est None ou n'a pas le bon attribut
            print(f"--- WARNING: LLM filter step returned an invalid response or None. Proceeding without LLM filtering. ---")
            # PLAN B : Si le LLM échoue, on prend les 5 playlists les plus récentes comme solution de repli
            selected_ids = [p['id'] for p in newest_candidates[:5]]
            print(f"--- Fallback: Selecting the 5 most recent playlists: {selected_ids} ---")

    except asyncio.TimeoutError:
        print(f"--- ERROR: LLM filter step timed out. Aborting search. ---")
        return []
    except Exception as e:
        print(f"--- ERROR during LLM filter step: {e}. Aborting search. ---")
        return []

    # 3. Fetch full details (cette partie est correcte)
    final_playlists = []
    if not selected_ids:
        print("--- No playlists were selected by the LLM filter. ---")
        return []

    for playlist_id in selected_ids[:max_final_playlists]:
        playlist_details = await _fetch_playlist_items(playlist_id)
        if playlist_details:
            final_playlists.append(playlist_details)
            
    print(f"--- Successfully fetched details for {len(final_playlists)} final playlists. ---")
    return final_playlists