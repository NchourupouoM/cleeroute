from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from src.cleeroute.langGraph.sections_subsections_sep.models import SubsectionGenerationInput, SubsectionOutput
from src.cleeroute.langGraph.project_generator import RequiredGenProjInput
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
    domains: List[str] 
    categories: List[str] 
    topics: List[str]
    objectives: List[str]
    expectations: List[str]
    prerequisites: List[str]
    desired_level: str

class CourseInput(Course_meta_datas):
    
    class Config:
        json_schema_extra = {
            "examples": [
            {
                "title": "Achieving Native-Like English Fluency",
                "domains": [
                    "Language Learning"
                ],
                "categories": [
                    "English Language Learning",
                    "Accent Reduction"
                ],
                "topics": [
                    "pronunciation",
                    "speaking skills",
                    "fluency",
                    "conversation practice",
                    "english idioms",
                    "phrasal verbs",
                    "intonation",
                    "rhythm",
                    "stress patterns",
                    "phonetics",
                    "grammar",
                    "vocabulary"
                ],
                "objectives": [
                    "I will develop the ability to speak English with native-like fluency and natural pronunciation.",
                    "I will expand my vocabulary and command of idiomatic expressions to sound more natural and nuanced.",
                    "I will gain confidence in engaging in spontaneous conversations across various topics.",
                    "I will refine my understanding and use of complex grammatical structures in spoken English."
                ],
                "expectations": [
                    "I want to improve my fluency so I don't hesitate when speaking.",
                    "I expect to reduce my foreign accent to sound more natural.",
                    "I anticipate learning and using more natural phrases and idioms.",
                    "I might not yet be comfortable using complex grammatical structures spontaneously.",
                    "I may struggle with understanding fast or informal native speech."
                ],
                "prerequisites": [
                    "Basic understanding of English grammar (e.g., sentence structure, common tenses).",
                    "A foundational English vocabulary (A2/B1 level or equivalent).",
                    "Ability to form simple sentences and convey basic ideas in English.",
                    "Familiarity with the English alphabet and basic pronunciation."
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

class Course(BaseModel):
    title: str
    introduction: Optional[str] = None
    sections: List[Section]

# complete course structure for the humain in the loop action

class SectionWtihProject(Section):
    project: Project

class CompleteCourse(BaseModel):
    title: str
    introduction: Optional[str] = None
    sections: List[SectionWtihProject]