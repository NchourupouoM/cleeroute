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
from src.cleeroute.db.user_service import get_active_pool

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

async def smart_search_and_curate(
    user_input: str, 
    conversation_summary: str, 
    language: str, 
    limit: int = 2
) -> List[str]:
    """
    Recherche 100% Curée par IA avec "Quality Cut-off".
    """
    print(f"--- AI-Driven Curation for: '{user_input}' (Max: {limit}) ---")
    
    service = get_youtube_service()

    # 1. BROAD SEARCH (limit + 10)
    fetch_count = min(limit + 10, 25)
    search_term = f"{user_input} course tutorial full"
    
    try:
        def search_sync():
            return service.search().list(
                q=search_term, part="snippet", type="playlist",
                maxResults=fetch_count, relevanceLanguage=language[:2]
            ).execute()
        response = await asyncio.to_thread(search_sync)
    except Exception as e:
        print(f"Search API Error: {e}")
        return []

    candidates = []
    # On ajoute "compilation" et "best of" qui sont souvent des nids à contenu vrac
    BLACKLIST = ["gameplay", "reaction", "trailer", "music", "mix", "funny", "memes", "shorts", "compilation"]
    
    for item in response.get("items", []):
        snippet = item["snippet"]
        title = snippet["title"]
        pid = item["id"]["playlistId"]
        
        if any(bad in title.lower() for bad in BLACKLIST): continue
        if "Topic" in snippet["channelTitle"]: continue

        candidates.append({
            "id": pid,
            "title": title,
            "channel": snippet["channelTitle"]
        })

    if not candidates: return []
    # Si on a très peu de candidats, on laisse l'IA juger quand même, 
    # sauf si c'est vraiment vide.

    # 2. LLM SELECTION
    llm = get_llm() # Gemini Flash
    
    prompt = Prompts.CURATE_PLAYLISTS_PROMPT.format(
        limit=limit,
        user_input=user_input,
        conversation_summary=conversation_summary, 
        language=language,
        candidates_json=json.dumps(candidates)
    )

    try:
        ai_msg = await asyncio.wait_for(llm.ainvoke(prompt), timeout=5.0)
        
        content = ai_msg.content.strip()
        if "```" in content:
            content = content.split("```json")[-1].split("```")[0].strip()
            
        selection = json.loads(content)
        selected_ids = selection.get("selected_ids", [])
        
        # Validation
        if isinstance(selected_ids, list) and len(selected_ids) > 0:
            print(f"--- AI Selected {len(selected_ids)} playlists (Quality Filter Applied) ---")
            
            # Anti-Hallucination : On ne garde que les IDs qui existent vraiment
            valid_ids = [pid for pid in selected_ids if any(c["id"] == pid for c in candidates)]
            
            # --- MODIFICATION CRITIQUE ICI ---
            # AVANT : On avait une boucle "for c in candidates..." qui complétait jusqu'à la limite.
            # MAINTENANT : On supprime cette boucle.
            # Si l'IA n'a gardé que 4 IDs valides sur 10 demandés, c'est qu'elle a jugé les autres mauvais.
            # On respecte son jugement.
            
            return valid_ids[:limit]

        else:
            print("--- AI returned empty selection (Too strict?). Falling back to Top 2 YouTube. ---")

    except asyncio.TimeoutError:
        print("--- AI Selection Timeout -> Falling back to YouTube Rank ---")
    except Exception as e:
        print(f"--- AI Selection Failed ({e}) -> Falling back to YouTube Rank ---")

    # FALLBACK DE SÉCURITÉ
    # Si l'IA a planté ou n'a rien renvoyé du tout, on prend les 2 premiers de YouTube 
    # pour ne pas renvoyer une liste vide (ce qui est pire).
    # On limite à 2 ou 3 max en fallback pour éviter de polluer si on n'est pas sûr.
    safe_fallback_limit = min(limit, 3)
    return [c["id"] for c in candidates[:safe_fallback_limit]]

# The last resort
async def get_emergency_video_resource(user_input: str) -> Optional[AnalyzedPlaylist]:
    """
    DERNIER RECOURS : Trouve une vidéo unique longue (tuto) et la déguise en Playlist.
    Utilisé quand aucune playlist n'est trouvée.
    """
    print(f"--- 🚨 Triggering EMERGENCY VIDEO SEARCH for: {user_input} ---")
    service = get_youtube_service()
    
    try:
        def search_sync():
            # On cherche une vidéo, longue (>20min si possible via videoDuration='long' mais l'API standard ne le garantit pas toujours facilement sans filters complexes, on reste simple)
            # On ajoute "tutorial" ou "guide" pour viser de l'éducatif
            return service.search().list(
                q=f"{user_input} tutorial guide", 
                type="video", 
                part="snippet", 
                maxResults=1
            ).execute()
            
        res = await asyncio.to_thread(search_sync)
        items = res.get("items", [])
        
        if not items:
            return None
            
        item = items[0]
        snippet = item["snippet"]
        vid_id = item["id"]["videoId"]
        
        # On crée un objet VideoInfo
        video = VideoInfo(
            title=snippet["title"],
            description=snippet["description"],
            video_url=f"https://www.youtube.com/watch?v={vid_id}",
            thumbnail_url=snippet["thumbnails"].get("medium", {}).get("url"),
            channel_title=snippet["channelTitle"]
        )
        
        # On l'emballe dans une "AnalyzedPlaylist" artificielle pour que le reste du code marche
        return AnalyzedPlaylist(
            playlist_title=f"Course: {snippet['title']}", # Titre adapté
            playlist_description=f"{user_input} course",
            playlist_url=f"https://www.youtube.com/watch?v={vid_id}",
            videos=[video]
        )
        
    except Exception as e:
        print(f"Emergency Search Failed: {e}")
        return None