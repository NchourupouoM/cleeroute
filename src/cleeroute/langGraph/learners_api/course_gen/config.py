
TOTAL_STEPS = 3

PROGRESS_MAPPING = {
    "starting": {
        "step": 1,
        "label": "Searching Resources",
        "desc": "Scanning YouTube for high-quality playlists and videos..."
    },
    "resources_merged": {
        "step": 2,
        "label": "Designing Blueprint",
        "desc": "AI is analyzing videos and structuring learning modules..."
    },
    # Fallback pour tout état inconnu
    "unknown": {
        "step": 1,
        "label": "Processing",
        "desc": "The AI is working on your request..."
    }
}