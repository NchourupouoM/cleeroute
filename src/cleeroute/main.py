from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import time

from src.cleeroute.db.checkpointer import lifespan as checkpointer_lifespan
from src.cleeroute.db.app_db import app_db_lifespan as application_db_lifespan
from contextlib import asynccontextmanager

from src.cleeroute.langGraph.learners_api.metadata_from_learner.meta_data_gen import router_metadata
from src.cleeroute.langGraph.course_agents import course_structure_router
from src.cleeroute.langGraph.project_generator import project_content_router

from src.cleeroute.langGraph.streaming_project_content.test_streaming import project_content_router_stream
from src.cleeroute.langGraph.streaming_course_structure.main_course import course_structure_router_stream
from src.cleeroute.langGraph.sections_subsections_sep.section_subsection import course_outline_router, course_subsections_router
# from src.cleeroute.langGraph.updated_syllabus.update_syllabus import course_modification_router, course_human_intervention_router
from src.cleeroute.langGraph.learners_api.course_gen.routers import syllabus_router
from src.cleeroute.langGraph.learners_api.course_gen.router_with_streaming import stream_syllabus_router
# from src.cleeroute.langGraph.learners_api.course_update.router import updated_router
from src.cleeroute.langGraph.learners_api.quiz.routers import quiz_router
from src.cleeroute.langGraph.learners_api.chats.routers import global_chat_router, upload_file_router
from src.cleeroute.langGraph.learners_api.chats.routers import stream_global_chat_router
from src.cleeroute.langGraph.learners_api.quiz.router_with_streaming import stream_quiz_router
from fastapi import APIRouter
# from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

@asynccontextmanager
async def main_lifespan(app: FastAPI):
    """
    Le gestionnaire de cycle de vie principal qui orchestre les autres.
    """
    # On entre dans le contexte de chaque gestionnaire de cycle de vie
    async with checkpointer_lifespan(app):
        async with application_db_lifespan(app):
            yield

app = FastAPI(
    title="Cleeroute AI API",
    # On utilise notre nouveau lifespan principal
    lifespan=main_lifespan
)


app = FastAPI(lifespan=main_lifespan)

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


# ========================================================================================
app.include_router(router_metadata, prefix="/metadata", tags=["Metadata Generators"])
# =======================================================================================
app.include_router(course_structure_router, prefix="", tags=["Course Structure Generators"])
app.include_router(course_structure_router_stream, prefix="", tags=["Course Structure Generators"])
# ===========================================================================================
app.include_router(course_outline_router, prefix="", tags=["Sections and subsection generators"])
app.include_router(course_subsections_router, prefix="", tags=["Sections and subsection generators"])
# =======================================================================================
app.include_router(project_content_router, prefix="", tags=["Project content Generators"])
app.include_router(project_content_router_stream, prefix="", tags=["Project content Generators"])
# ============================================================================================
# app.include_router(course_modification_router, prefix="", tags=["Course structure update"])
# app.include_router(course_human_intervention_router, prefix="", tags=["Course structure update"])
# ============================================================================================
app.include_router(syllabus_router, prefix="", tags=["Syllabus Generators for Learners using youtube playlists"])
# =============================================================================================
app.include_router(stream_syllabus_router, prefix="", tags=["Streaming Syllabus Generators for Learners using youtube playlists"])
# =============================================================================================
# app.include_router(updated_router, prefix="", tags=["Updated the learner choose path in the course structure"])
# =============================================================================================
app.include_router(quiz_router, prefix="", tags=["Quiz Generators for Learners"])
# =============================================================================================
app.include_router(stream_quiz_router, prefix="", tags=["Streaming Quiz Generators for Learners"])
# =============================================================================================
app.include_router(global_chat_router, prefix="", tags=["Global Chat for Learners"])
# =============================================================================================
app.include_router(stream_global_chat_router, prefix="", tags=["Streaming Global Chat for Learners"])
# =============================================================================================
app.include_router(upload_file_router, prefix="", tags=["File Uploads for chat sessions"])
# =============================================================================================
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True, )