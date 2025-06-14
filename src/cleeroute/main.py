from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from src.cleeroute.crew import Course_structure_crew, Course_meta_datas_crew
from src.cleeroute.models import CourseInput, Course_meta_datas_input
from sqlalchemy.orm import Session
from typing import List
import time 

from src.cleeroute.db.models import VideoSearch, VideoResponse
from src.cleeroute.db.services import search_similar_videos
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
    conn = get_db_connection()
    try:
        videos = search_similar_videos(request)
        response_videos = []
        for video_tuple in videos:
            response_videos.append(
                VideoResponse(
                    thumbnail=video_tuple[0],
                    url=video_tuple[1],
                    duration=video_tuple[2],                      
                    title=video_tuple[3], 
                )
            )
        return response_videos
    except Exception as e:
        print(e)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="127.0.0.1", port=8000, reload=True, )#workers=4)