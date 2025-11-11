# In services.py

import os
import json
from typing import List, Optional
import asyncio

from googleapiclient.discovery import build
from functools import lru_cache

from googleapiclient.errors import HttpError
from langchain_google_genai import ChatGoogleGenerativeAI

from .models import AnalyzedPlaylist, VideoInfo, FilteredPlaylistSelection
from .prompt import Prompts
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv
import re
load_dotenv()

# It's good practice to initialize the LLM and YouTube service once
# if the service is called multiple times.
llm = ChatGoogleGenerativeAI(model=os.getenv("MODEL_2"), google_api_key=os.getenv("GEMINI_API_KEY"), max_tokens=8192)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
if not YOUTUBE_API_KEY:
    raise ValueError("YOUTUBE_API_KEY must be set in env")

import httplib2
import ssl

# Désactive la vérification SSL (UNIQUEMENT POUR LE DÉBOGAGE)

youtube_service = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
YOUTUBE_API_TIMEOUT = 60

def classify_youtube_url(url: str) -> str:
    """
    Classifies a YouTube URL as 'playlist', 'video', or 'unknown'.
    """
    try:
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)

        if 'list' in query_params:
            return 'playlist'
        elif 'v' in query_params or parsed_url.hostname == 'youtu.be':
            return 'video'
        else:
            return 'unknown'
    except Exception as e:
        print(f"--- ERROR classifying URL {url}: {e}. Returning 'unknown'. ---")
        return 'unknown'


async def fetch_playlist_details(playlist_url: str) -> Optional[AnalyzedPlaylist]:
    """
    Fetches details for a single playlist given its full URL.
    Extracts the playlist ID from the URL.
    """
    try:
        playlist_id = playlist_url.split("list=")[1]
        return await _fetch_playlist_items(playlist_id)
    except IndexError:
        print(f"--- Invalid playlist URL: {playlist_url}. Skipping. ---")
        return None
    except Exception as e:
        print(f"--- ERROR fetching playlist {playlist_url}: {e}. Skipping. ---")
        return None


async def _fetch_playlist_items(playlist_id: str, max_retries: int = 3) -> Optional[AnalyzedPlaylist]:
    for attempt in range(max_retries):
        try:
            # 1. Récupère les métadonnées de la playlist
            playlist_request = youtube_service.playlists().list(
                part="snippet",
                id=playlist_id
            )
            playlist_response = await asyncio.to_thread(playlist_request.execute)

            if not playlist_response.get("items"):
                print(f"--- Playlist {playlist_id} not found. Skipping. ---")
                return None

            playlist_info = playlist_response['items'][0]['snippet']
            playlist_title = playlist_info['title']
            playlist_description = playlist_info.get('description', "")

            # 2. Récupère les vidéos
            video_infos = []
            next_page_token = None

            while True:
                request = youtube_service.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=next_page_token
                )
                response = await asyncio.to_thread(request.execute)

                for item in response.get("items", []):
                    snippet = item.get("snippet", {})
                    video_id = snippet.get("resourceId", {}).get("videoId")
                    if video_id:
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
                                title=snippet.get("title", "No Title"),
                                description=snippet.get("description", ""),
                                video_url=f"https://www.youtube.com/watch?v={video_id}",
                                channel_title=snippet.get("videoOwnerChannelTitle", ""),
                                thumbnail_url=thumbnail_url,
                            )
                        )

                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break

            return AnalyzedPlaylist(
                playlist_title=playlist_title,
                playlist_description=playlist_description,
                playlist_url=f"https://www.youtube.com/playlist?list={playlist_id}",
                videos=video_infos
            )
        except HttpError as e:
            if e.resp.status == 403:  # Quota exceeded
                print(f"--- YouTube API quota exceeded for playlist {playlist_id}. Skipping. ---")
                return None
            elif attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"--- HTTP Error {e.resp.status} for playlist {playlist_id}. Retrying in {wait_time}s... ---")
                await asyncio.sleep(wait_time)
            else:
                print(f"--- Max retries reached for playlist {playlist_id}. Skipping. ---")
                return None
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"--- Error fetching playlist {playlist_id}: {e}. Retrying in {wait_time}s... ---")
                await asyncio.sleep(wait_time)
            else:
                print(f"--- Max retries reached for playlist {playlist_id}. Skipping. ---")
                return None


@lru_cache(maxsize=128)
def cached_youtube_search(query: str):
    request = youtube_service.search().list(
        q=query,
        part="snippet",
        type="playlist",
        maxResults=50,
        order="date"
    )
    return request.execute()


async def search_and_filter_youtube_playlists(
    queries: List[str],
    user_input: str,
    max_candidates_per_query: int = 50,
    max_final_playlists: int = 10
) -> List[AnalyzedPlaylist]:
    """
    Recherche des playlists YouTube et filtre avec un LLM.
    En cas d'échec du LLM, utilise les 5 playlists les plus récentes comme fallback.
    """
    print("--- Starting High-Quality YouTube Search ---")

    # 1. Recherche des candidats (avec retry et gestion des erreurs)
    async def search_task(query: str, max_retries: int = 3):
        for attempt in range(max_retries):
            try:
                request = youtube_service.search().list(
                    q=query,
                    part="snippet",
                    type="playlist",
                    maxResults=max_candidates_per_query,
                    order="date"  # Tri par date pour avoir les plus récentes
                )
                return await asyncio.to_thread(request.execute)
            except Exception as e:
                print(f"--- Attempt {attempt + 1} failed for query '{query}': {e} ---")
                if attempt == max_retries - 1:
                    return None
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

    # Exécute les requêtes en parallèle
    search_tasks = [search_task(query) for query in queries]
    search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

    # 2. Fusionne tous les candidats valides
    candidate_playlists = []
    unique_ids = set()

    for response in search_results:
        if response and "items" in response:
            for item in response["items"]:
                playlist_id = item["id"]["playlistId"]
                if playlist_id not in unique_ids:
                    snippet = item["snippet"]
                    candidate_playlists.append({
                        "id": playlist_id,
                        "title": snippet["title"],
                        "description": snippet.get("description", ""),
                        "publishedAt": snippet["publishedAt"]
                    })
                    unique_ids.add(playlist_id)

    if not candidate_playlists:
        print("--- No candidates found. Aborting. ---")
        return []

    # 3. Trie les candidats par date (les plus récentes en premier)
    candidate_playlists.sort(key=lambda p: p["publishedAt"], reverse=True)
    newest_candidates = candidate_playlists[:40]  # Garde les 40 plus récentes
    print(f"--- Found {len(candidate_playlists)} total candidates. Selecting the 40 newest for LLM filtering. ---")

    # 4. Filtrage par LLM (avec fallback automatique)
    candidates_str = json.dumps(newest_candidates, indent=2)
    prompt = Prompts.FILTER_YOUTUBE_PLAYLISTS.format(
        user_input=user_input,
        playlist_candidates=candidates_str
    )

    # Liste de fallback (les 5 premières playlists)
    fallback_playlist_ids = [p["id"] for p in newest_candidates[:5]]
    selected_ids = []

    try:
        # Utilise le LLM avec un timeout strict
        structured_llm = llm.with_structured_output(FilteredPlaylistSelection)
        llm_response = await asyncio.wait_for(structured_llm.ainvoke(prompt), timeout=60)

        # Vérifie si la réponse est valide
        if llm_response and hasattr(llm_response, "selected_ids") and llm_response.selected_ids:
            selected_ids = llm_response.selected_ids
            print(f"--- LLM selected {len(selected_ids)} playlists. ---")
        else:
            print("--- WARNING: LLM returned empty or invalid selection. Using fallback playlists. ---")
            selected_ids = fallback_playlist_ids  # Fallback automatique
    except Exception as e:
        print(f"--- ERROR during LLM filtering: {e}. Using fallback playlists. ---")
        selected_ids = fallback_playlist_ids  # Fallback automatique

    # 5. Si selected_ids est vide (cas extrême), utilise le fallback
    if not selected_ids:
        print("--- WARNING: No playlists selected. Using fallback playlists. ---")
        selected_ids = fallback_playlist_ids

    # 6. Récupère les détails des playlists sélectionnées
    final_playlists = []
    for playlist_id in selected_ids[:max_final_playlists]:
        playlist_details = await _fetch_playlist_items(playlist_id)
        if playlist_details:
            final_playlists.append(playlist_details)

    print(f"--- Successfully fetched details for {len(final_playlists)} playlists. ---")
    return final_playlists




YOUTUBE_URL_REGEX = re.compile(
    r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
)


def get_video_id_from_url(url: str) -> Optional[str]:
    """
    Extracts the YouTube video ID from various URL formats using a pre-compiled regex.
    """
    match = YOUTUBE_URL_REGEX.search(url)
    return match.group(1) if match else None

async def analyze_single_video(video_url: str) -> Optional[VideoInfo]:
    """
    Analyzes a single user-provided YouTube video URL.
    Fetches its details like title, description, channel, and thumbnail.
    This function is designed to be called concurrently with other async tasks.
    """
    video_id = get_video_id_from_url(video_url)
    if not video_id:
        print(f"--- WARNING: Could not extract video ID from URL: {video_url} ---")
        return None

    print(f"--- Analyzing single video (ID: {video_id}) ---")
    
    try:
        # 1. Créer la requête de manière synchrone
        video_request = youtube_service.videos().list(
            part="snippet,contentDetails",
            id=video_id
        )
        
        # 2. Exécuter la requête bloquante dans un thread séparé pour ne pas geler l'application
        video_response = await asyncio.to_thread(video_request.execute)
        
        if not video_response.get("items"):
            print(f"--- WARNING: Video with ID {video_id} not found or is private. Skipping. ---")
            return None
        
        # 3. Extraire les métadonnées de la réponse
        item = video_response["items"][0]
        snippet = item["snippet"]
        
        # Sélection de la meilleure miniature disponible
        thumbnails = snippet.get("thumbnails", {})
        thumbnail_url = (
            thumbnails.get("maxres", {}) or
            thumbnails.get("standard", {}) or
            thumbnails.get("high", {}) or
            thumbnails.get("medium", {}) or
            thumbnails.get("default", {})
        ).get("url")

        # 4. Construire et retourner l'objet Pydantic
        return VideoInfo(
            title=snippet.get("title", "No Title Provided"),
            description=snippet.get("description"),
            video_url=f"https://www.youtube.com/watch?v={video_id}",
            channel_title=snippet.get("channelTitle"),
            thumbnail_url=thumbnail_url
        )
        
    except HttpError as e:
        print(f"--- ERROR (HttpError) analyzing video {video_id}: {e} ---")
        return None
    except Exception as e:
        print(f"--- ERROR (Unexpected) analyzing video {video_id}: {e} ---")
        return None