from typing import List, Optional
from pydantic import BaseModel, HttpUrl

class CourseInput(BaseModel):
    topic: str
    objective: str
    prerequisites: str

    class Config:
        json_schema_extra = {
            "example": {
                "topic": "python",
                "objective": "I want to become an expert in Python programming language",
                "prerequisites": "I have a good knowledge in algorithm"
            }
        }

class QuizQuestion(BaseModel):
    question: str
    options: List[str]
    correct_answer: str

class Project(BaseModel):
    title: str
    description: str
    objectives: List[str]
    deliverables: List[str]
    evaluation_criteria: Optional[List[str]] = None

class Subsection(BaseModel):
    title: str
    description: str

class Section(BaseModel):
    title: str
    subsections: List[Subsection]
    quiz: Optional[List[QuizQuestion]] = []
    project: Optional[Project] = None

class Course(BaseModel):
    title: str
    introduction: Optional[str] = None
    sections: List[Section]

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Course Title",
                "introduction": "General description",
                "sections": [
                    {
                    "title": "Section Name",
                    "description": "Section objectives",
                    "subsections": [
                        {
                        "title": "Sub-topic Name",
                        "description": "Detailed content"
                        }
                    ],
                    "quiz": [
                        {
                        "question": "Multiple choice question",
                        "options": ["Answers"],
                        "correct_answer": "Correct answer"
                        }
                    ],
                    "project": {
                        "title": "Project Name",
                        "description": "Instructions",
                        "objectives": ["Learning objectives"],
                        "deliverables": ["Expected deliverables"],
                        "evaluation_criteria": ["Grading criteria"]
                    }
                    }
                ]
             }
        }