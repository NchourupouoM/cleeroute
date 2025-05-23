from fastapi import FastAPI, HTTPException
from src.cleeroute.crew import Cleeroute
from src.cleeroute.models import CourseInput

app = FastAPI()

# python -m src.cleeroute.main  // pour lancer le serveur

@app.post("/course-generated")
def generate_course(request: CourseInput):
    """
        ## Generates a complete course structure based on specified parameters.
        
        This automated function creates a comprehensive educational package including:
        - Detailed course outline with sections and subsections
        - Assessment quizzes for each section
        - Practical projects with evaluation criteria
        - Industry-relevant content based on top companies in the field

        Args:
        - topic: Main subject of the course (e.g., "JavaScript", "Data Science") \n
        - objectives: Learner's goals in string format \n
        - prerequisites: Required knowledge/skills in string format \n

        Returns:\n
        dict: `Structured course content in JSON-ready format with keys:\n \n
            - title (str): Course title \n
            - introduction (str): Course description \n
            - sections (list[dict]): List of course sections containing: \n
                * title (str): Section name \n
                * description (str): Section objectives \n
                * subsections (list[dict]): Breakdown of concepts \n
                * quiz (list[dict]): Assessment questions with: \n
                    - question (str) \n
                    - options (list[str]) \n
                    - correct_answer (str) \n
                * project (dict): Practical project details with: \n
                    - title (str) \n
                    - description (str) \n
                    - objectives (list[str]) \n
                    - deliverables (list[str]) \n
                    - evaluation_criteria (list[str]) \n`
    """
    try:
        result = Cleeroute().crew().kickoff(inputs=request.model_dump())
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)