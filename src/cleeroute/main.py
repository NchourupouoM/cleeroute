from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from src.cleeroute.crew import Course_structure_crew, Course_meta_datas_crew
from src.cleeroute.models import CourseInput, Course_meta_datas_input
from sqlalchemy.orm import Session
from typing import List
import time 

from src.cleeroute.db.models import VideoSearch, VideoResponse
from src.cleeroute.db.services import  fetch_channel_categories, search_videos_pgvector_manual_string #search_similar_videos,
from src.cleeroute.db.db import get_db_connection

app = FastAPI()

# Configurer les origines autorisées
origins = [
    "http://localhost",
    "http://localhost:3000", 
    "http://localhost:8000",
    "http://127.0.0.1",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)



# python -m src.cleeroute.main  // pour lancer le serveure

# ======================== Meta data generator =====================================
# {
#   "response": "I want to learn convolutional neural network"
# }

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.perf_counter() 
    response = await call_next(request)
    
    process_time = time.perf_counter() - start_time
    response.headers["X-Process-Time-Seconds"] = f"{process_time:.4f}"
    
    return response


@app.post("/gen_course_meta_data")
def generate_obj_pre(request: Course_meta_datas_input):
    try:    
        result_obj = Course_meta_datas_crew().crew().kickoff(inputs=request.model_dump())
        return result_obj.json_dict
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# ====================== Course structure generator ================================

@app.post("/gen_course_structure")
def generate_course_structure(request: CourseInput):
    try:
        result = Course_structure_crew().crew().kickoff(inputs=request.model_dump())
        return result.json_dict
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

# ===================== get videos by category for each subsection ===============

@app.post("/search", response_model=List[VideoResponse])
async def search_videos(request: VideoSearch):
    # 1. Initialize the list of videos you will return BEFORE the loop.
    response_videos = []
    conn = None # Initialize conn to None

    try:
        conn = get_db_connection()
        channel_names_list = fetch_channel_categories(request.category)
        top_videos = search_videos_pgvector_manual_string(request.subsection, channel_names_list, top_k=100)

        # 2. Check if top_videos is not None and has items before looping.
        #    This 'if top_videos:' check gracefully handles both `None` and an empty list `[]`.
        if top_videos:
            # 3. Loop directly over the items in `top_videos`. Do not use enumerate.
            for video_data in top_videos:
                response_videos.append(
                    VideoResponse(
                        # `video_data` is now the dictionary or row object, so you can access its items.
                        # Using .get() is safe as it provides a default value if a key is missing.
                        thumbnail=video_data.get('thumbnail', 'N/A'),
                        url=video_data.get('video_id', 'N/A'),
                        duration=video_data.get('duration', 'N/A'),                      
                        title=video_data.get('title', 'N/A'), 
                    )
                )

    except Exception as e:
        # It's good practice to log the actual error for debugging
        print(f"An error occurred during video search: {e}")
        # Return a proper HTTP error instead of letting the server crash
        raise HTTPException(status_code=500, detail="Internal Server Error")
    
    finally:
        # Ensure the database connection is always closed
        if conn:
            conn.close()

    # 4. Return the complete list AFTER the loop has finished.
    return response_videos
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True, )#workers=4)