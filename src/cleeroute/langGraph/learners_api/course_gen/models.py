from typing import List, Optional
from pydantic import BaseModel, HttpUrl, Field
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
    user_input_text: str = Field(..., min_length=10)
    user_input_links: Optional[List[HttpUrl]] = Field(
        None, 
        description="A list of YouTube URLs (can be playlists or single videos)."
    )
    metadata: Course_meta_datas

# --------------------------
# YouTube / Video models
# --------------------------
class VideoInfo(BaseModel):
    title: str
    description: Optional[str] = None
    video_url: HttpUrl
    channel_title: Optional[str] = None
    thumbnail_url: Optional[HttpUrl] = None

class AnalyzedPlaylist(BaseModel):
    playlist_title: str
    playlist_description: Optional[str] = None
    playlist_url: HttpUrl
    videos: List[VideoInfo]

# --------------------------
# Course & Syllabus models
# --------------------------
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