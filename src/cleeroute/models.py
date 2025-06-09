from typing import List, Optional
from pydantic import BaseModel

class Course_meta_datas_input(BaseModel):
    response: str

    class Config:
        json_schema_extra = {
            "example": {
                "response":"I want to speak english like a native"
            }
        }

class Course_meta_datas(BaseModel):
    title: str 
    domain: str 
    category: str 
    topics: str
    objectives: List[str]
    expectations: List[str]
    prerequisites: List[str]
    desired_level: str

class CourseInput(Course_meta_datas):
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                "title": "Achieving Native-like English Fluency",
                "domain": "Language Learning",
                "category": "English Language Learning",
                "topics": "Speaking skills, Pronunciation, English idioms, Fluency, Accent Reduction",
                "objectives": [
                    "My objective is to develop my English speaking ability to a native-like level, focusing on natural flow, idiomatic expression, accurate pronunciation, and nuanced communication."
                ],
                "expectations": [
                    "I can already understand and participate in basic English conversations.",
                    "I have a reasonable vocabulary and understanding of core grammar.",
                    "I don't yet sound natural when I speak.",
                    "I want to reduce my foreign accent.",
                    "I struggle with using idioms and colloquialisms correctly."
                ],
                "prerequisites": [
                    "Intermediate level of English proficiency (B1/B2 or higher)",
                    "Basic understanding of English grammar",
                    "Core vocabulary knowledge",
                    "Ability to understand spoken English",
                    "Prior experience with English conversation practice"
                ],
                "desired_level": "advanced"
                }
            ]
        }

class Project(BaseModel):
    title: str
    description: str
    objectives: List[str]
    prerequisites: List[str]
    Steps: List[str]
    Deliverable: List[str]
    evaluation_criteria: Optional[List[str]] = None


class Subsection(BaseModel):
    title: str
    description: str

class Section(BaseModel):
    title: str
    description: str
    subsections: List[Subsection]
    project: Optional[Project] = None

class Course(BaseModel):
    title: str
    introduction: Optional[str] = None
    sections: List[Section]