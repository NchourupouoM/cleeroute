from typing import List, Optional
from pydantic import BaseModel, field_validator, ConfigDict

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

    @field_validator('question', 'correct_answer', mode='before')
    @classmethod
    def clean_quiz_strings(cls, v: str) -> str:
        """Nettoie les chaînes de caractères dans QuizQuestion"""
        return v.replace('\\n', '\n').replace('\\', '') if isinstance(v, str) else v

    @field_validator('options', mode='before')
    @classmethod
    def clean_options(cls, v: List[str]) -> List[str]:
        """Nettoie chaque option du quiz"""
        return [opt.replace('\\n', '\n').replace('\\', '') if isinstance(opt, str) else opt for opt in v]

class Project(BaseModel):
    title: str
    description: str
    objectives: List[str]
    deliverables: List[str]
    evaluation_criteria: Optional[List[str]] = None

    @field_validator('title', 'description', mode='before')
    @classmethod
    def clean_project_strings(cls, v: str) -> str:
        return v.replace('\\n', '\n').replace('\\', '') if isinstance(v, str) else v

    @field_validator('objectives', 'deliverables', 'evaluation_criteria', mode='before')
    @classmethod
    def clean_project_lists(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        return [item.replace('\\n', '\n').replace('\\', '') if isinstance(item, str) else item for item in v]

class Subsection(BaseModel):
    title: str
    description: str

    @field_validator('title', 'description', mode='before')
    @classmethod
    def clean_subsection_strings(cls, v: str) -> str:
        return v.replace('\\n', '\n').replace('\\', '') if isinstance(v, str) else v

class Section(BaseModel):
    title: str
    subsections: List[Subsection]
    quiz: Optional[List[QuizQuestion]] = None
    project: Optional[Project] = None

    @field_validator('title', mode='before')
    @classmethod
    def clean_section_title(cls, v: str) -> str:
        return v.replace('\\n', '\n').replace('\\', '') if isinstance(v, str) else v

class Course(BaseModel):
    title: str
    introduction: Optional[str] = None
    sections: List[Section]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Advanced Python Programming",
                "introduction": "Master Python with advanced concepts",
                "sections": []
            }
        }
    )

    @field_validator('title', 'introduction', mode='before')
    @classmethod
    def clean_course_strings(cls, v: str) -> str:
        return v.replace('\\n', '\n').replace('\\', '') if isinstance(v, str) else v

    @field_validator('sections', mode='before')
    @classmethod
    def clean_sections_list(cls, v: List[dict]) -> List[dict]:
        """Nettoie récursivement les sections et sous-sections"""
        if not isinstance(v, list):
            return v
            
        cleaned = []
        for section in v:
            if isinstance(section, dict):
                cleaned_section = {
                    **section,
                    'title': section.get('title', '').replace('\\n', '\n').replace('\\', ''),
                    'subsections': [
                        {
                            **sub,
                            'title': sub.get('title', '').replace('\\n', '\n').replace('\\', ''),
                            'description': sub.get('description', '').replace('\\n', '\n').replace('\\', '')
                        }
                        for sub in section.get('subsections', [])
                        if isinstance(sub, dict)
                    ]
                }
                cleaned.append(cleaned_section)
            else:
                cleaned.append(section)
        return cleaned