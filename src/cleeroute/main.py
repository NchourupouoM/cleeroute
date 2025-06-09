from fastapi import FastAPI, HTTPException, Request
from src.cleeroute.crew import Course_structure_crew, Course_meta_datas_crew
from src.cleeroute.models import CourseInput, Course_meta_datas_input
import time 

app = FastAPI()

# python -m src.cleeroute.main  // pour lancer le serveure

# ======================== Meta data generator =====================================
# {
#   "response": "I want to learn convolutional neural network"
# }

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.perf_counter() # Utiliser time.perf_counter() pour une meilleure précision
    
    response = await call_next(request) # Exécute la requête et obtient la réponse
    
    process_time = time.perf_counter() - start_time
    # Ajoute le temps de traitement à l'en-tête de la réponse
    # Convertir en millisecondes pour une meilleure lisibilité, par exemple
    # response.headers["X-Process-Time-Ms"] = f"{process_time * 1000:.2f}" 
    # Ou en secondes
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
    

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)