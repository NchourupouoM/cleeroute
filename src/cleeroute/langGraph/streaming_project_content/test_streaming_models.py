# models.py
from pydantic import BaseModel, Field
from typing import List, Optional

class RequiredGenProjInput(BaseModel):
    class Config:
        json_schema_extra = {
            "examples": [
                {
                "course_title": "Advanced English Fluency: Mastering Natural Pronunciation and Idiomatic Language",
                "section_title": "Fundamentals of English Phonetics",
                "section_description": "Understand the core principles of English phonetics to improve pronunciation accuracy.",
                "subsection_titles_concatenated": "Introduction to the International Phonetic Alphabet (IPA) + Mastering Vowel Sounds + Mastering Consonant Sounds + Correcting Common Pronunciation Errors"
            }
         ]
    }
        
    course_title: str
    section_title: str
    section_description: str
    subsection_titles_concatenated: str

# Modèles pour les sorties structurées de chaque noeud
class TitleDesc(BaseModel):
    title: str = Field(description="Le titre épique et accrocheur de la quête.")
    description: str = Field(description="Une description narrative et immersive de la quête, utilisant du Markdown.")

class ObjectivesPrereqs(BaseModel):
    objectives: List[str] = Field(description="Liste des conditions de victoire claires et mesurables.")
    prerequisites: List[str] = Field(description="Liste de l'équipement requis (connaissances, outils).")

class Steps(BaseModel):
    steps: List[str] = Field(description="Liste des étapes détaillées pour guider le Héros dans sa quête.")

class Evaluation(BaseModel):
    deliverable: List[str] = Field(description="Liste des preuves concrètes du triomphe à soumettre.")
    evaluation_criteria: Optional[List[str]] = Field(description="Liste des critères de jugement de la quête.")

# Modèle final complet du Projet
class Project(BaseModel):
    title: str
    description: str
    objectives: List[str]
    prerequisites: List[str]
    steps: List[str]
    deliverable: List[str]
    evaluation_criteria: Optional[List[str]] = None