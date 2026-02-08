from typing import List, Optional
from pydantic import BaseModel, HttpUrl, Field, field_validator
from typing import Literal, Dict

# --------------------------
# Input Models
# --------------------------
class Course_meta_datas(BaseModel):
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
    title: str
    domains: List[str]
    categories: List[str]
    topics: List[str]
    objectives: List[str]
    expectations: List[str]
    prerequisites: List[str]
    desired_level: str

class SyllabusRequest(BaseModel):
    user_id: Optional[str] = Field(
        None, 
        description="The UUID of the user. Used to determine premium limitations."
    )
    user_input_text: str
    user_input_links: Optional[List[HttpUrl]] = Field(
        None, 
        description="A list of YouTube URLs (can be playlists or single videos)."
    )
    metadata: Course_meta_datas

    language: str = Field(
        default="English", 
        description="The target language for the course content and interaction (e.g., 'French', 'Spanish', 'Swahili')."
    )

# YouTube / Video models
class VideoInfo(BaseModel):
    title: str
    description: Optional[str] = None
    video_url: HttpUrl
    channel_title: Optional[str] = None
    thumbnail_url: Optional[HttpUrl] = None
    published_at: Optional[str] = None

class AnalyzedPlaylist(BaseModel):
    playlist_title: str
    playlist_description: Optional[str] = None
    playlist_url: HttpUrl
    videos: List[VideoInfo]

# Course & Syllabus models
class Project(BaseModel):
    title: str
    description: str
    objectives: List[str]
    prerequisites: List[str]
    steps: List[str]
    deliverables: List[str]
    evaluation_criteria: Optional[List[str]] = None

class Subsection(BaseModel):
    title: str
    description: Optional[str] = None
    video_url: HttpUrl
    thumbnail_url: Optional[HttpUrl] = None
    channel_title: Optional[str] = None

class Section(BaseModel):
    title: str
    description: Optional[str] = None
    subsections: List[Subsection]
    project: Optional[Project] = None

class CompleteCourse(BaseModel):
    title: str
    introduction: Optional[str] = None
    tag: str
    sections: List[Section]

class SyllabusOptions(BaseModel):
    syllabi: List[CompleteCourse] = Field(..., description="Contains the different coherent learning paths")

# =============================================

class SectionPlan(BaseModel):
    """Ce que le LLM va générer : juste la structure."""
    title: str = Field(..., description="Titre pédagogique de la section/module")
    description: str = Field(..., description="Bref objectif pédagogique de cette section")

    start_index: int = Field(..., description="Index of the first video in this section.")
    end_index: int = Field(..., description="Index of the last video in this section.")

    @field_validator('end_index')
    def check_range(cls, v, values):
        if 'start_index' in values.data and v < values.data['start_index']:
            raise ValueError('end_index must be >= start_index')
        return v

class CourseBlueprint(BaseModel):
    """La réponse brute du LLM, très légère."""
    course_title: str
    course_introduction: str
    course_tag: str
    sections: List[SectionPlan]


class StartJourneyResponse(BaseModel):
    thread_id: str
    next_question: str

class ContinueJourneyRequest(BaseModel):
    user_answer: str

class JourneyStatusResponse(BaseModel):
    status: str
    thread_id: str
    output: Dict | None = None
    next_question: str | None = None

class FilteredPlaylistSelection(BaseModel):
    """
    A Pydantic model that defines the expected JSON structure for the LLM's
    playlist filtering task.
    """
    selected_ids: List[str] = Field(
        ..., 
        description="A list of the YouTube playlist IDs that have been selected as high-quality and relevant."
    )

class JourneyProgress(BaseModel):
    current_step: int       # Ex: 2
    total_steps: int        # Ex: 6
    percentage: int         # Ex: 33
    label: str              # Ex: "Searching YouTube"
    description: str        # Ex: "Analyzing top 50 playlists for relevance..."

class JourneyStatusResponse(BaseModel):
    status: str
    thread_id: str
    output: Optional[Dict] = None
    next_question: Optional[str] = None
    # Ajout du champ optionnel pour le tracking
    progress: Optional[JourneyProgress] = None