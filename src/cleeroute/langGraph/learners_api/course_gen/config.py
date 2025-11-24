# Mapping des états techniques vers des messages utilisateurs
PROGRESS_MAPPING = {
    "starting": {
        "step": 1, 
        "label": "Initialization", 
        "desc": "Setting up the learning environment..."
    },
    "search_strategy_generated": {
        "step": 2, 
        "label": "Strategy Defined", 
        "desc": "Search queries generated. Now scanning YouTube..."
    },
    "user_links_processed": {
        "step": 2, 
        "label": "Analyzing Input", 
        "desc": "Processing your provided links..."
    },
    "resources_searched": {
        "step": 3, 
        "label": "Resources Found", 
        "desc": "High-quality playlists identified. Merging content..."
    },
    "resources_merged": {
        "step": 4, 
        "label": "Planning", 
        "desc": "Analyzing videos to build the optimal learning path (this takes time)..."
    },
    "syllabus_planned": {
        "step": 5, 
        "label": "Blueprint Ready", 
        "desc": "Structure created. Searching for practical projects..."
    },
    "project_videos_searching": {
        "step": 6, 
        "label": "Finalizing", 
        "desc": "Converting blueprint to final JSON format..."
    },
    "organizing_course": {
        "step": 7, 
        "label": "Formatting", 
        "desc": "Validating final structure..."
    },
    "completed": {
        "step": 8, 
        "label": "Completed", 
        "desc": "Your course is ready!"
    }
}

TOTAL_STEPS = 8