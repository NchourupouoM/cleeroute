from typing import List
from pydantic import BaseModel, Field

# --- Modèles d'entrée pour la génération de course_outline ---
class CourseInput(BaseModel):
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
    title: str = Field(description="The concise and descriptive title of the course or project.")
    domains: List[str] = Field(description="A list of primary knowledge domains or fields this course belongs to.")
    categories: List[str] = Field(description="A list of more specific categories or sub-fields within the domains.")
    topics: List[str] = Field(description="A comprehensive list of specific keywords, concepts, or modules that will be covered.")
    objectives: List[str] = Field(description="A list of clear, measurable learning objectives.")
    expectations: List[str] = Field(description="A list of what is expected from the participants during the course.")
    prerequisites: List[str] = Field(description="A list of essential prior knowledge, skills, or tools.")
    desired_level: str = Field(description="The target proficiency level for the audience (e.g., 'Beginner', 'Intermediate', 'Advanced')")

class Section(BaseModel):
    title: str = Field(description="The title of the main section.")
    description: str = Field(description="A brief description of what this section covers.")

# Ce modèle est la CIBLE de notre sortie structurée combinée !
class Course_section(BaseModel):
    """
    Represents the high-level structure of a course, including header and main sections without subsections.
    """
    title: str 
    introduction: str
    sections: List[Section]


# --- Modèles d'entrée et de sortie pour la deuxième API (Subsection Generation) ---
class SubsectionGenerationInput(BaseModel):
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "course_title": "Achieving Native-Like English Fluency",
                    "course_introduction": "Welcome to Native English Fluency: Advanced Immersion. This course is designed for advanced learners seeking to master native-like pronunciation, intonation, and idiomatic expressions. Through targeted practice and in-depth analysis, you will refine your speaking skills, expand your vocabulary, and gain the confidence to engage in spontaneous conversations. By the end of this course, you'll be able to communicate fluently and naturally across a wide range of topics.",
                    "section_title": "Mastering English Phonetics: A Comprehensive Guide",
                    "section_description": "An overview of English phonetics, focusing on sounds that are often mispronounced by non-native speakers. Includes an introduction to the International Phonetic Alphabet (IPA)"
                }
            ]
        }
    
    course_title: str = Field(description="The overall title of the course.")
    course_introduction: str = Field(description="The main course introduction of the overall course.")
    section_title: str = Field(description="The title of the specific section for which subsections are to be generated.")
    section_description: str = Field(description="The description of the specific section.")

class Subsection(BaseModel):
    title: str = Field(description="The title of the subsection.")
    description: str = Field(description="A description of what the learner will learn in this subsection.")

class SubsectionOutput(BaseModel):
    subsections: List[Subsection]