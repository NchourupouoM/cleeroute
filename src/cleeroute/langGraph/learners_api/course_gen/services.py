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
    regex = r"(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/(?:[^\/\n\s]+\/\S+\/|(?:v|e(?:mbed)?)\/|\S*?[?&]v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})"
    match = re.search(regex, url)
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

async def fetch_playlist_light(playlist_input: str, limit: int = None) -> Optional[AnalyzedPlaylist]:
    """
    Fetches playlist videos. 
    Optimized: strict limit of 150 videos to prevent LLM Context Window overflow.
    """
    # Extraction ID propre
    if "list=" in playlist_input:
        playlist_id = playlist_input.split("list=")[1].split("&")[0]
    else:
        playlist_id = playlist_input

    # Safety Cap
    HARD_LIMIT = 1000 
    if limit:
        effective_limit = min(limit, HARD_LIMIT)
    else:
        effective_limit = HARD_LIMIT

    try:
        def fetch_sync():
            service = get_youtube_service()
            
            # 1. Info Playlist
            pl_resp = service.playlists().list(part="snippet", id=playlist_id).execute()
            if not pl_resp.get("items"): return None
            pl_info = pl_resp['items'][0]['snippet']
            
            # 2. Videos
            video_infos = []
            next_page_token = None
            
            while len(video_infos) < effective_limit:
                req = service.playlistItems().list(
                    part="snippet",
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=next_page_token
                )
                res = req.execute()

                for item in res.get("items", []):
                    snippet = item.get("snippet", {})
                    vid_id = snippet.get("resourceId", {}).get("videoId")
                    title = snippet.get("title", "")
                    
                    # Filtre basique
                    if not vid_id or title in ["Private video", "Deleted video"]:
                        continue

                    channel = snippet.get("videoOwnerChannelTitle") or snippet.get("channelTitle") or pl_info.get('channelTitle')
                    thumb = snippet.get("thumbnails", {}).get("medium", {}).get("url")

                    video_infos.append(VideoInfo(
                        title=title,
                        description=snippet.get("description", ""),
                        video_url=f"https://www.youtube.com/watch?v={vid_id}",
                        thumbnail_url=thumb,
                        channel_title=channel
                    ))
                
                next_page_token = res.get('nextPageToken')
                if not next_page_token:
                    break
            
            return AnalyzedPlaylist(
                playlist_title=pl_info['title'],
                playlist_url=f"https://www.youtube.com/playlist?list={playlist_id}",
                videos=video_infos
            )

        return await asyncio.to_thread(fetch_sync)
    except Exception as e:
        print(f"Error fetching playlist {playlist_id}: {e}")
        return None
    
async def analyze_single_video(video_url: str) -> Optional[VideoInfo]:
    video_id = get_video_id_from_url(video_url)
    if not video_id: 
        return None
    try:
        def fetch_sync():
            service = get_youtube_service()
            res = service.videos().list(part="snippet", id=video_id).execute()
            if not res.get("items"): 
                return None
            
            snippet = res["items"][0]["snippet"]
            return VideoInfo(
                title=snippet.get("title"),
                description=snippet.get("description"),
                video_url=f"https://www.youtube.com/watch?v={video_id}",
                channel_title=snippet.get("channelTitle"),
                thumbnail_url=snippet.get("thumbnails", {}).get("medium", {}).get("url")
            )
            
        return await asyncio.to_thread(fetch_sync)
    except:
        return None

async def smart_search_and_curate(user_input: str, conversation_summary: str, language: str) -> List[str]:
    """
    Recherche intelligente :
    1. Récupère 15 candidats.
    2. Applique des filtres techniques (Hard Filter).
    3. Utilise un LLM pour choisir le meilleur (Soft Filter).
    """
    print(f"---Smart Curation for: '{user_input}' ---")
    
    service = get_youtube_service()
    
    # 1. BROAD SEARCH (On élargit à 15 résultats)
    # On force "playlist" et on ajoute des termes pédagogiques
    search_term = f"{user_input} course tutorial full"
    
    try:
        def search_sync():
            return service.search().list(
                q=search_term,
                part="snippet",
                type="playlist",
                maxResults=15, 
                relevanceLanguage=language[:2]
            ).execute()
            
        response = await asyncio.to_thread(search_sync)
    except Exception as e:
        print(f"Search API Error: {e}")
        return []

    candidates = []
    
    # 2. HARD FILTERING (Règles métier impératives)
    # Mots-clés à bannir absolument
    BLACKLIST_KEYWORDS = ["gameplay", "reaction", "trailer", "music", "mix", "funny", "memes", "shorts"]
    
    for item in response.get("items", []):
        snippet = item["snippet"]
        title = snippet["title"]
        desc = snippet["description"]
        pid = item["id"]["playlistId"]
        
        # Filtre A: Mots interdits
        if any(bad in title.lower() for bad in BLACKLIST_KEYWORDS):
            continue
            
        # Filtre B: Chaînes "Topic" (souvent générées auto par YouTube Musique)
        if "Topic" in snippet["channelTitle"]:
            continue

        # (Optionnel) Filtre C: Récupérer le itemCount via une 2ème requête batch 
        # pour virer les playlists < 4 vidéos. Pour la vitesse, on saute ça ici, 
        # mais pour la qualité V1, c'est recommandé.
        candidates.append({
            "id": pid,
            "title": title,
            "channel": snippet["channelTitle"],
            "description": desc[:200] # On tronque pour économiser des tokens
        })

    if not candidates:
        return []

    # Si on a moins de 3 candidats, on renvoie tout sans LLM pour aller vite
    if len(candidates) <= 3:
        return [c["id"] for c in candidates]

    # 3. LLM CURATION (L'intelligence)
    # On demande au LLM de choisir le meilleur parmi les candidats restants
    llm = get_llm()
    prompt = Prompts.CURATE_PLAYLISTS_PROMPT.format(
        user_input=user_input,
        conversation_summary=conversation_summary,
        language=language,
        candidates_json=json.dumps(candidates)
    )

    try:
        # On utilise invoke simple car on veut juste une réponse courte JSON
        ai_msg = await llm.ainvoke(prompt)
        content = ai_msg.content.strip()
        
        # Nettoyage JSON (markdown removal)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].strip()
            
        selection = json.loads(content)
        best_id = selection.get("selected_playlist_id")
        reason = selection.get("reason")
        
        print(f"---Selected: {best_id} ({reason}) ---")
        
        # On retourne le meilleur en premier, suivi d'un ou deux "backups" au cas où
        # (On prend le meilleur + les 2 premiers de la liste originale qui ne sont pas le meilleur)
        backups = [c["id"] for c in candidates if c["id"] != best_id][:1]
        
        return [best_id] + backups

    except Exception as e:
        print(f"--- Curation AI Failed ({e}), falling back to heuristic ---")
        return [c["id"] for c in candidates[:2]]