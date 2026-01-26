import os
import json
import asyncio
import re
from typing import List, Optional, Dict
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

# Google / YouTube Imports
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from langchain_google_genai import ChatGoogleGenerativeAI

# Internal Imports
from .models import AnalyzedPlaylist, VideoInfo, FilteredPlaylistSelection
from .prompt import Prompts

from src.cleeroute.langGraph.learners_api.utils import get_llm

load_dotenv()

# Vérification de la clé API au chargement du module
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
if not YOUTUBE_API_KEY:
    raise ValueError("YOUTUBE_API_KEY must be set in env")

def get_youtube_service():
    """
    Creates and returns a new thread-safe YouTube Data API service instance.

    This factory function is essential because the `google-api-python-client` (based on httplib2)
    is not thread-safe. Creating a fresh instance for each request or task ensures
    compatibility with concurrent execution (asyncio/threads).

    Returns:
        googleapiclient.discovery.Resource: An authenticated YouTube API service object.
    """
    return build('youtube', 'v3', developerKey=os.getenv("YOUTUBE_API_KEY"), cache_discovery=False)


YOUTUBE_URL_REGEX = re.compile(
    r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
)

def get_video_id_from_url(url: str) -> Optional[str]:
    """
    Extracts the 11-character YouTube video ID from a given URL string.

    Supports various YouTube URL formats including:
    - Standard: youtube.com/watch?v=...
    - Short: youtu.be/...
    - Embed: youtube.com/embed/...

    Args:
        url (str): The full YouTube URL.

    Returns:
        Optional[str]: The video ID string if found, otherwise None.
    """
    match = YOUTUBE_URL_REGEX.search(url)
    return match.group(1) if match else None

def classify_youtube_url(url: str) -> str:
    """
    Analyzes a YouTube URL to determine if it points to a Playlist, a single Video,
    or if the type is unrecognizable.

    Args:
        url (str): The input URL string.

    Returns:
        str: One of the following values:
             - 'playlist': If the URL contains a 'list' parameter.
             - 'video': If the URL points to a video ID or uses 'youtu.be'.
             - 'unknown': If the URL format does not match expected patterns.
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
    High-level wrapper to fetch full details of a playlist from its URL.

    This function parses the URL to extract the playlist ID and then delegates
    the data retrieval to `_fetch_playlist_items`.

    Args:
        playlist_url (str): The full URL of the YouTube playlist.

    Returns:
        Optional[AnalyzedPlaylist]: A structured object containing the playlist metadata
                                    and its videos, or None if the URL is invalid or fetch fails.
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

async def _fetch_playlist_items(playlist_id: str, max_results: int = 1000) -> Optional[AnalyzedPlaylist]:
    """
    Internal function to fetch all videos from a YouTube playlist (with pagination).

    It executes blocking network calls within a thread to prevent blocking the asyncio loop.
    It retrieves playlist metadata (title, description) and iterates through pages
    of playlist items to gather video details.

    Args:
        playlist_id (str): The unique YouTube Playlist ID (not URL).
        max_results (int, optional): The maximum number of videos to retrieve. Defaults to 1000.
                                     (Effectively unlimited for standard courses).

    Returns:
        Optional[AnalyzedPlaylist]: The populated playlist object, or None if the ID is invalid/empty.
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
            pages_limit = 4 
            current_page = 0

            while True:
                if current_page >= pages_limit:
                    break

                vid_request = local_service.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=playlist_id,
                    maxResults=max_results,
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

def heuristic_relevance_score(snippet: Dict, user_input: str) -> float:
    """
    Calculates a heuristic score to rank playlist relevance based on metadata.
    This is a fast, CPU-bound operation avoiding expensive LLM calls for initial filtering.

    Scoring Logic:
    - Matches of user keywords in title: +10 pts each.
    - Educational keywords (course, tutorial...): +15 pts.
    - Negative keywords (short, funny...): -50 pts.

    Args:
        snippet (Dict): The 'snippet' dictionary from the YouTube API search response.
        user_input (str): The user's original search query.

    Returns:
        float: The calculated relevance score. Higher is better.
    """
    score = 0.0
    title = snippet.get("title", "").lower()
    desc = snippet.get("description", "").lower()
    keywords = user_input.lower().split()

    matches = sum(1 for w in keywords if w in title)
    score += matches * 10

    good_terms = ["course", "tutorial", "full", "complete", "bootcamp", "series", "playlist"]
    if any(t in title for t in good_terms):
        score += 15

    bad_terms = ["short", "funny", "reaction", "gameplay", "trailer"]
    if any(t in title for t in bad_terms):
        score -= 50

    return score


async def analyze_single_video(video_url: str) -> Optional[VideoInfo]:
    """
    Fetches details for a single YouTube video URL.

    This is used when the user provides specific video links instead of a playlist.
    It resolves the video ID and calls the YouTube API.

    Args:
        video_url (str): The full URL of the video.

    Returns:
        Optional[VideoInfo]: A populated video object, or None if the video is private/deleted/invalid.
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
            channel_title=snippet.get("channelTitle", "Unknown Channel"),
            thumbnail_url=thumbnail_url
        )
        
    except HttpError as e:
        print(f"--- HTTP Error analyzing video {video_id}: {e} ---")
        return None
    except Exception as e:
        print(f"--- Unexpected Error analyzing video {video_id}: {e} ---")
        return None
    

async def fast_search_youtube(user_input: str, language: str, max_results: int = 10) -> List[str]:
    """
    Executes a fast, heuristic-based search for relevant playlists.

    Unlike `search_and_filter_youtube_playlists`, this function DOES NOT use an LLM.
    It relies on `heuristic_relevance_score` to sort results instantly.

    Args:
        user_input (str): The search terms.
        language (str): The user's preferred language code (e.g., "en", "fr").
        max_results (int, optional): The number of candidates to scan. Defaults to 10.

    Returns:
        List[str]: A list containing the IDs of the TOP 2 best playlists found.
                   (Strictly limited to 2 to ensure focus and speed).
    """
    print(f"--- Fast Search: '{user_input}' ---")
    try:
        def search_sync():
            service = get_youtube_service()
            search_term = f"{user_input} course tutorial"
            
            req = service.search().list(
                q=search_term,
                part="snippet",
                type="playlist",
                maxResults=max_results, # On utilise le paramètre passé
                relevanceLanguage=language[:2] if len(language) >= 2 else "en"
            )
            return req.execute()

        response = await asyncio.to_thread(search_sync)
        
        candidates = []
        for item in response.get("items", []):
            snippet = item["snippet"]
            pid = item["id"]["playlistId"]
            score = heuristic_relevance_score(snippet, user_input)
            candidates.append((pid, score))

        # Tri et renvoi des IDs
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [c[0] for c in candidates[:2]]  # On ne renvoie que les IDs des 2 meilleurs candidats
    
    except Exception as e:
        print(f"--- Search Error: {e} ---")
        return []


async def fetch_playlist_light(playlist_input: str, limit: int = None) -> Optional[AnalyzedPlaylist]:
    """
    Retrieves playlist details and videos, optimized for speed or exhaustiveness.

    Args:
        playlist_input (str): Either a full YouTube Playlist URL or a raw Playlist ID.
        limit (int, optional): The maximum number of videos to fetch. 
                               If None, it fetches ALL videos in the playlist (pagination loop).

    Returns:
        Optional[AnalyzedPlaylist]: The populated playlist object, or None if fetch fails.
    """
    playlist_id = playlist_input.split("list=")[1].split("&")[0] if "list=" in playlist_input else playlist_input

    try:
        def fetch_sync():
            service = get_youtube_service()
            
            # 1. Info Playlist
            pl_resp = service.playlists().list(part="snippet", id=playlist_id).execute()
            if not pl_resp.get("items"): return None
            pl_info = pl_resp['items'][0]['snippet']
            
            # 2. Récupération des vidéos (PAGINATION ILLIMITÉE)
            video_infos = []
            next_page_token = None
            
            while True:
                # Si une limite est fixée et atteinte, on arrête (pour la recherche auto éventuellement)
                if limit and len(video_infos) >= limit:
                    break

                vid_req = service.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=playlist_id,
                    maxResults=50, # Max autorisé par appel API YouTube
                    pageToken=next_page_token
                )
                vid_response = vid_req.execute()

                for item in vid_response.get("items", []):
                    snippet = item.get("snippet", {})
                    vid_id = snippet.get("resourceId", {}).get("videoId")
                    
                    if vid_id:
                        # Extraction channel title robuste
                        channel_title = snippet.get("videoOwnerChannelTitle") or snippet.get("channelTitle") or pl_info.get('channelTitle')
                        
                        video_infos.append(VideoInfo(
                            title=snippet.get("title", ""),
                            description=snippet.get("description", ""),
                            video_url=f"https://www.youtube.com/watch?v={vid_id}",
                            thumbnail_url=snippet.get("thumbnails", {}).get("medium", {}).get("url"),
                            channel_title=channel_title
                        ))

                # Gestion Pagination
                next_page_token = vid_response.get('nextPageToken')
                
                # S'il n'y a plus de page, on arrête
                if not next_page_token:
                    break
            
            return AnalyzedPlaylist(
                playlist_title=pl_info['title'],
                playlist_url=f"https://www.youtube.com/playlist?list={playlist_id}",
                videos=video_infos
            )

        return await asyncio.to_thread(fetch_sync)
    except Exception as e:
        print(f"--- Error fetching playlist {playlist_id}: {e} ---")
        return None
