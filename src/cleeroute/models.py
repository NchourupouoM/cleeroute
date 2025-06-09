from typing import List, Optional
from pydantic import BaseModel

class Course_meta_datas_input(BaseModel):
    response: str

    class Config:
        json_schema_extra = {
            "example": {
                "response":"I want to learn convolutional neural network"
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
                "title": "Natural Language Processing Fundamentals",
                "domain": "Technology",
                "category": "Artificial Intelligence",
                "topics": "Text Preprocessing, Word Embeddings, Transformer Models",
                "objectives": [
                        "Tokenize and clean text data",
                        "Implement Word2Vec from scratch",
                        "Fine-tune a BERT model for sentiment analysis"
                    ],
                "expectations": [
                        "I'm comfortable with Python but new to NLP",
                        "I expect transformers to be challenging initially"
                    ],
                "prerequisites": [
                        "Python",
                        "Basic probability",
                        "Pandas library"
                    ],
                "desired_level": "Intermediate"
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