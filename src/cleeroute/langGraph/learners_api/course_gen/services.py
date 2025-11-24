import os
import json
import asyncio
import re
from typing import List, Optional
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

# Google / YouTube Imports
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from langchain_google_genai import ChatGoogleGenerativeAI

# Internal Imports
from .models import AnalyzedPlaylist, VideoInfo, FilteredPlaylistSelection
from .prompt import Prompts

load_dotenv()

# Vérification de la clé API au chargement du module
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
if not YOUTUBE_API_KEY:
    raise ValueError("YOUTUBE_API_KEY must be set in env")

# ==============================================================================
# FACTORY FUNCTIONS (CRITIQUE POUR LA CONCURRENCE)
# ==============================================================================

def get_youtube_service():
    """
    Crée une NOUVELLE instance du client YouTube pour chaque appel.
    Ceci est indispensable car google-api-python-client (httplib2) n'est pas thread-safe.
    """
    return build('youtube', 'v3', developerKey=os.getenv("YOUTUBE_API_KEY"), cache_discovery=False)

def get_llm():
    """
    Crée une NOUVELLE instance du LLM pour éviter les erreurs de boucle d'événements (gRPC).
    """
    return ChatGoogleGenerativeAI(
        model=os.getenv("MODEL_2", "gemini-2.5-flash"),
        google_api_key=os.getenv("GEMINI_API_KEY"),
        max_tokens=8192
    )

# ==============================================================================
# URL UTILITIES
# ==============================================================================

YOUTUBE_URL_REGEX = re.compile(
    r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
)

def get_video_id_from_url(url: str) -> Optional[str]:
    """Extracts the YouTube video ID from various URL formats."""
    match = YOUTUBE_URL_REGEX.search(url)
    return match.group(1) if match else None

def classify_youtube_url(url: str) -> str:
    """Classifies a YouTube URL as 'playlist', 'video', or 'unknown'."""
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

# ==============================================================================
# PLAYLIST SERVICES
# ==============================================================================

async def fetch_playlist_details(playlist_url: str) -> Optional[AnalyzedPlaylist]:
    """
    Fetches details for a single playlist given its full URL.
    """
    try:        
        if "list=" in playlist_url:
            playlist_id = playlist_url.split("list=")[1]
            # Nettoyage basique au cas où d'autres params suivent
            if "&" in playlist_id:
                playlist_id = playlist_id.split("&")[0]
            return await _fetch_playlist_items(playlist_id)
        else:
            print(f"--- WARNING: Invalid playlist URL format: {playlist_url} ---")
            return None
    except Exception as e:
        print(f"Error parsing playlist URL {playlist_url}: {e}")
        return None

async def _fetch_playlist_items(playlist_id: str) -> Optional[AnalyzedPlaylist]:
    """
    Internal function to fetch playlist items using a thread-local service instance.
    """
    try:
        # Exécution dans un thread séparé pour ne pas bloquer la boucle asyncio
        # et pour isoler l'instance du service (httplib2)
        def fetch_sync():
            local_service = get_youtube_service()
            
            # 1. Récupérer les métadonnées de la playlist
            pl_request = local_service.playlists().list(part="snippet", id=playlist_id)
            pl_response = pl_request.execute()

            if not pl_response.get("items"):
                print(f"--- WARNING: Playlist {playlist_id} not found or empty. ---")
                return None

            playlist_info = pl_response['items'][0]['snippet']
            playlist_title = playlist_info['title']
            playlist_description = playlist_info.get('description')

            # 2. Récupérer les vidéos (Pagination)
            video_infos = []
            next_page_token = None
            
            # On limite à 2 pages (100 vidéos max) pour la performance, sauf si besoin absolu
            pages_limit = 2 
            current_page = 0

            while True:
                if current_page >= pages_limit:
                    break

                vid_request = local_service.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=next_page_token
                )
                vid_response = vid_request.execute()

                for item in vid_response.get("items", []):
                    snippet = item.get("snippet", {})
                    video_id = snippet.get("resourceId", {}).get("videoId")
                    
                    # Ignorer les vidéos supprimées ou privées
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
                                title=snippet.get("title", "Unknown Title"),
                                description=snippet.get("description", ""),
                                video_url=f"https://www.youtube.com/watch?v={video_id}",
                                channel_title=snippet.get("videoOwnerChannelTitle"),
                                thumbnail_url=thumbnail_url,
                            )
                        )

                next_page_token = vid_response.get('nextPageToken')
                current_page += 1
                if not next_page_token:
                    break

            return AnalyzedPlaylist(
                playlist_title=playlist_title,
                playlist_url=f"https://www.youtube.com/playlist?list={playlist_id}",
                playlist_description=playlist_description,
                videos=video_infos
            )

        # Lancement asynchrone du bloc synchrone
        return await asyncio.to_thread(fetch_sync)

    except HttpError as e:
        print(f"--- HTTP Error fetching playlist {playlist_id}: {e} ---")
        return None
    except Exception as e:
        print(f"--- Unexpected Error fetching playlist {playlist_id}: {e} ---")
        return None

# ==============================================================================
# SEARCH & FILTER SERVICES
# ==============================================================================

async def search_and_filter_youtube_playlists(queries: List[str], user_input: str):
    print("--- Starting High-Quality YouTube Search ---")

    async def search_task(query: str):
        """Fonction interne pour exécuter une recherche unique de manière isolée."""
        try:
            # Instanciation locale pour thread-safety
            local_service = get_youtube_service()
            
            request = local_service.search().list(
                q=query, 
                part="snippet", 
                type="playlist", 
                maxResults=50, 
                order="date" # ou "relevance" selon le besoin
            )
            # Exécution bloquante dans un thread
            return await asyncio.to_thread(request.execute)
            
        except HttpError as e:
            print(f"--- Search HTTP Error '{query}': {e} ---")
            return None
        except Exception as e:
            print(f"--- Search Generic Error '{query}': {e} ---")
            return None

    try:
        # 1. Exécution parallèle des recherches
        search_tasks = [search_task(query) for query in queries]
        # Timeout global de 60s pour toutes les recherches
        search_results = await asyncio.wait_for(
            asyncio.gather(*search_tasks, return_exceptions=True),
            timeout=60.0
        )

        candidate_playlists = []
        unique_ids = set()

        # 2. Agrégation des résultats
        for response in search_results:
            if response is None or isinstance(response, Exception):
                continue
                
            for item in response.get("items", []):
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
            print("--- No playlist candidates found. ---")
            return []

        # Tri par date (les plus récents d'abord) et sélection des 40 premiers pour le filtre
        candidate_playlists.sort(key=lambda p: p['publishedAt'], reverse=True)
        newest_candidates = candidate_playlists[:40]

        # 3. Filtrage Intelligent via LLM
        candidates_str = json.dumps(newest_candidates, indent=2)
        prompt = Prompts.FILTER_YOUTUBE_PLAYLISTS.format(
            user_input=user_input,
            playlist_candidates=candidates_str
        )

        selected_ids = []
        try:
            # Instanciation locale du LLM
            local_llm = get_llm()
            structured_llm = local_llm.with_structured_output(FilteredPlaylistSelection)
            
            llm_response = await structured_llm.ainvoke(prompt)

            if llm_response and hasattr(llm_response, 'selected_ids'):
                selected_ids = llm_response.selected_ids
                print(f"--- LLM selected {len(selected_ids)} playlists: {selected_ids} ---")
            else:
                print(f"--- WARNING: LLM filter returned invalid response. Fallback to top 5. ---")
                selected_ids = [p['id'] for p in newest_candidates[:5]]
        except Exception as e:
            print(f"--- ERROR during LLM filter: {e}. Fallback to top 5. ---")
            selected_ids = [p['id'] for p in newest_candidates[:5]]

        # 4. Récupération des détails complets pour les playlists sélectionnées
        # On limite à 10 pour ne pas surcharger le système
        final_playlists = []
        
        # On parallélise aussi la récupération des détails
        detail_tasks = [_fetch_playlist_items(pid) for pid in selected_ids[:10]]
        detail_results = await asyncio.gather(*detail_tasks, return_exceptions=True)
        
        for res in detail_results:
            if res and isinstance(res, AnalyzedPlaylist):
                final_playlists.append(res)

        print(f"--- Successfully fetched details for {len(final_playlists)} final playlists. ---")
        return final_playlists

    except asyncio.TimeoutError:
        print("--- GLOBAL TIMEOUT during YouTube Search (60s limit reached). ---")
        return []
    except Exception as e:
        print(f"--- CRITICAL ERROR during Search Process: {e} ---")
        return []

# ==============================================================================
# SINGLE VIDEO SERVICE
# ==============================================================================

async def analyze_single_video(video_url: str) -> Optional[VideoInfo]:
    """
    Analyzes a single user-provided YouTube video URL.
    Fetches details using a thread-local service instance.
    """
    video_id = get_video_id_from_url(video_url)
    if not video_id:
        print(f"--- WARNING: Could not extract video ID from URL: {video_url} ---")
        return None

    print(f"--- Analyzing single video (ID: {video_id}) ---")
    
    try:
        def fetch_video_sync():
            local_service = get_youtube_service()
            vid_request = local_service.videos().list(
                part="snippet,contentDetails",
                id=video_id
            )
            return vid_request.execute()

        # Exécution dans un thread
        video_response = await asyncio.to_thread(fetch_video_sync)
        
        if not video_response.get("items"):
            print(f"--- WARNING: Video {video_id} not found or private. ---")
            return None
        
        item = video_response["items"][0]
        snippet = item["snippet"]
        
        thumbnails = snippet.get("thumbnails", {})
        thumbnail_url = (
            thumbnails.get("maxres", {}) or
            thumbnails.get("standard", {}) or
            thumbnails.get("high", {}) or
            thumbnails.get("medium", {}) or
            thumbnails.get("default", {})
        ).get("url")

        return VideoInfo(
            title=snippet.get("title", "No Title"),
            description=snippet.get("description"),
            video_url=f"https://www.youtube.com/watch?v={video_id}",
            channel_title=snippet.get("channelTitle"),
            thumbnail_url=thumbnail_url
        )
        
    except HttpError as e:
        print(f"--- HTTP Error analyzing video {video_id}: {e} ---")
        return None
    except Exception as e:
        print(f"--- Unexpected Error analyzing video {video_id}: {e} ---")
        return None