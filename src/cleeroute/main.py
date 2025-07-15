from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from src.cleeroute.crew import Course_structure_crew, Course_meta_datas_crew
from src.cleeroute.models import CourseInput, Course_meta_datas_input
import time
import math

from src.cleeroute.db.models import VideoSearch, VideoResponse, PaginatedVideoResponse
from src.cleeroute.db.services import  fetch_channel_categories,get_sentence_transformer_model,search_videos_pgvector_manual_string
from src.cleeroute.langGraph.stream_endpoint import router
from src.cleeroute.langGraph.meta_data_gen import router_metadata_2, router_metadata_1

app = FastAPI()

# Configurer les origines autorisées
origins = [
    "http://localhost",
    "http://localhost:3000",
    "https://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1",
    "http://127.0.0.1:3000",
    "https://cleeroute.pages.dev",
    "https://www.cleeroute.com",
    "https://cleeroute.com",
    "http://127.0.0.1",
    "http://127.0.0.1:35084",
    "http://127.0.0.1:5500", # Pour le développement local avec Live Server
    "http://localhost:5500", # Pour le développement local avec Live Server
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"],
)

# --- Model Configuration ---
MODEL_CONFIG = {
    "model_name": "intfloat/multilingual-e5-small",
    "use_gpu": True,
    "use_fp16": True 
}


# ======================== Meta data generator =====================================
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
MODEL_CONFIG = {
    "model_name": "intfloat/multilingual-e5-small",
    "use_gpu": True,
    "use_fp16": True 
}


model = get_sentence_transformer_model(MODEL_CONFIG)

@app.post("/search", response_model=PaginatedVideoResponse)
async def search_videos(
    request: VideoSearch, 
    page: int = Query(1, ge=1, description="Page number to retrieve"),
    size: int = Query(10, ge=1, le=100, description="Number of items per page (max 100)")
):
    # 1. Initialize the list of videos you will return BEFORE the loop.
    all_response_video_objects = []

    try:
        channel_names_list = fetch_channel_categories(request.category)
        top_k_results_from_search = 1000
        top_videos = search_videos_pgvector_manual_string(
            request.subsection, 
            channel_names_list, 
            model,
            top_k = top_k_results_from_search
        )

        if not top_videos: # handle the case where no videos are found
            return PaginatedVideoResponse(
                items=[],
                total_items=0,
                total_pages=0,
                current_page=page,
                page_size=size
            )
        
        # The pagination logique on top_videos
        total_items = len(top_videos)
        total_pages = math.ceil(total_items / size)

        # make sure the page number is within the valid range
        if page > total_pages and total_pages > 0: 
             raise HTTPException(status_code=404, detail=f"Page not found. Total pages: {total_pages}")
        
        start_index = (page - 1) * size
        end_index = start_index + size
        videos_on_page = top_videos[start_index:end_index]
    
        for video_data in videos_on_page:
            all_response_video_objects.append(
                VideoResponse(
                    channel_name=video_data.get('channel_name', 'N/A'),
                    thumbnail=video_data.get('thumbnail', 'N/A'),
                    url=video_data.get('video_id', 'N/A'),
                    duration=str(video_data.get('duration', '0')),
                    title=video_data.get('title', 'N/A'),
                )
            )
        return PaginatedVideoResponse(
            items=all_response_video_objects,
            total_items=total_items,
            total_pages=total_pages,
            current_page=page,
            page_size=size
        )

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"An error occurred during video search: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error: " + str(e))

app.include_router(router, prefix="/course", tags=["Course Generator"])
app.include_router(router_metadata_1, prefix="/metadata", tags=["Frist Metadata Generator"])
app.include_router(router_metadata_2, prefix="/metadata", tags=["Second Metadata Generator"])

    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True, )