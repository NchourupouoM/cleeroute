from pydantic import BaseModel, Field
from typing import Optional, Dict, List, TypedDict, Literal, Union
from src.cleeroute.langGraph.learners_api.course_gen.models import CompleteCourse, AnalyzedPlaylist

class StartModificationRequest(BaseModel):
    """
    Modèle pour la toute première requête qui initie une session de modification.
    """
    class Config:
        json_schema_extra = {
            "examples": [
            {
                "chosen_course":
                {
                    "title": "React JS 10-Day Learning Path",
                    "introduction": "This course provides a structured learning path to master React JS in 10 days, covering essential topics like React Router, component lifecycle, props, state, data fetching, and context API. This course is designed for beginners to intermediate learners.",
                    "tag": "best-of-both",
                    "sections": [
                    {
                        "title": "React Router",
                        "description": "This section covers React Router for navigation.",
                        "subsections": [
                        {
                            "title": "React Router - Complete Tutorial",
                            "description": "This video provides a complete tutorial on React Router.",
                            "video_url": "https://www.youtube.com/watch?v=oTIJunBa6MA",
                            "thumbnail_url": "https://i.ytimg.com/vi/oTIJunBa6MA/hqdefault.jpg",
                            "channel_title": "Cosden Solutions"
                        }
                        ],
                        "project": None
                    },
                    {
                        "title": "Component Lifecycle Methods",
                        "description": "This section covers the lifecycle methods of React components.",
                        "subsections": [
                        {
                            "title": "ReactJS Tutorial - 22 - Component Lifecycle Methods",
                            "description": "This video explains the component lifecycle methods in ReactJS.",
                            "video_url": "https://www.youtube.com/watch?v=qnN_FuFNq2g",
                            "thumbnail_url": "https://i.ytimg.com/vi/qnN_FuFNq2g/hqdefault.jpg",
                            "channel_title": "Codevolution"
                        }
                        ],
                        "project": None
                    },
                    {
                        "title": "React Basics",
                        "description": "This section covers the basics of React.",
                        "subsections": [
                        {
                            "title": "React tutorial for beginners ⚛️",
                            "description": "This video provides a React tutorial for beginners.",
                            "video_url": "https://www.youtube.com/watch?v=hn80mWvP-9g",
                            "thumbnail_url": "https://i.ytimg.com/vi/hn80mWvP-9g/hqdefault.jpg",
                            "channel_title": "Bro Code"
                        }
                        ],
                        "project": None
                    },
                    {
                        "title": "Props Explained",
                        "description": "This section covers props in React.",
                        "subsections": [
                        {
                            "title": "PROPS in React explained 📧",
                            "description": "This video explains the concept of props in React.",
                            "video_url": "https://www.youtube.com/watch?v=uvEAvxWvwOs",
                            "thumbnail_url": "https://i.ytimg.com/vi/uvEAvxWvwOs/hqdefault.jpg",
                            "channel_title": "Bro Code"
                        }
                        ],
                        "project": None
                    },
                    {
                        "title": "useState Hook",
                        "description": "This section covers the useState hook in React.",
                        "subsections": [
                        {
                            "title": "Learn useState In 15 Minutes - React Hooks Explained",
                            "description": "This video explains the useState hook in 15 minutes.",
                            "video_url": "https://www.youtube.com/watch?v=O6P86uwfdR0",
                            "thumbnail_url": "https://i.ytimg.com/vi/O6P86uwfdR0/hqdefault.jpg",
                            "channel_title": "Web Dev Simplified"
                        }
                        ],
                        "project": None
                    },
                    {
                        "title": "Fetching Data",
                        "description": "This section covers fetching data in React.",
                        "subsections": [
                        {
                            "title": "Fetching Data in React - Complete Tutorial",
                            "description": "This video provides a complete tutorial on fetching data in React.",
                            "video_url": "https://www.youtube.com/watch?v=00lxm_doFYw",
                            "thumbnail_url": "https://i.ytimg.com/vi/00lxm_doFYw/hqdefault.jpg",
                            "channel_title": "Cosden Solutions"
                        }
                        ],
                        "project": None
                    },
                    {
                        "title": "State Management with Context API",
                        "description": "This section covers state management using Context API.",
                        "subsections": [
                        {
                            "title": "State Management in React | Context API useContext | React Tutorials for Beginners",
                            "description": "This video explains state management using Context API and useContext.",
                            "video_url": "https://www.youtube.com/watch?v=ngVvDegsAW8",
                            "thumbnail_url": "https://i.ytimg.com/vi/ngVvDegsAW8/hqdefault.jpg",
                            "channel_title": "Dave Gray"
                        }
                        ],
                        "project": None
                    },
                    {
                        "title": "React Hooks",
                        "description": "This section covers various React hooks.",
                        "subsections": [
                        {
                            "title": "10 React Hooks Explained // Plus Build your own from Scratch",
                            "description": "This video explains 10 React hooks and how to build your own.",
                            "video_url": "https://www.youtube.com/watch?v=TNhaISOUy6Q",
                            "thumbnail_url": "https://i.ytimg.com/vi/TNhaISOUy6Q/hqdefault.jpg",
                            "channel_title": "Fireship"
                        }
                        ],
                        "project": None
                    },
                    {
                        "title": "Conditional Rendering",
                        "description": "This section covers conditional rendering in React.",
                        "subsections": [
                        {
                            "title": "How to CONDITIONAL RENDER in React ?",
                            "description": "This video explains how to conditionally render elements in React.",
                            "video_url": "https://www.youtube.com/watch?v=XvURBpFxdGw",
                            "thumbnail_url": "https://i.ytimg.com/vi/XvURBpFxdGw/hqdefault.jpg",
                            "channel_title": "Bro Code"
                        }
                        ],
                        "project": None
                    },
                    {
                        "title": "Controlled Inputs (Forms)",
                        "description": "This section covers controlled inputs in React forms.",
                        "subsections": [
                        {
                            "title": "Full React Tutorial #27 - Controlled Inputs (forms)",
                            "description": "This video provides a tutorial on controlled inputs in React forms.",
                            "video_url": "https://www.youtube.com/watch?v=IkMND33x0qQ",
                            "thumbnail_url": "https://i.ytimg.com/vi/IkMND33x0qQ/hqdefault.jpg",
                            "channel_title": "Net Ninja"
                        }
                        ],
                        "project": None
                    }
                ]
            },
            "user_request" : "I want to add another section based on real work problem solving exercise"
            }
        ]
    }

    chosen_course: CompleteCourse = Field(
        ..., 
        description="L'objet complet du parcours de cours que l'apprenant a sélectionné."
    )
    user_request: str = Field(
        ..., 
        min_length=5,
        description="La première demande de modification de l'apprenant en langage naturel (ex: 'Supprime la section sur la théorie')."
    )

class ContinueModificationRequest(BaseModel):
    """
    Modèle pour toutes les requêtes suivantes dans une session de modification existante.
    """
    thread_id: str = Field(
        ..., 
        description="L'ID de la session de conversation retourné par la requête précédente."
    )
    user_request: str = Field(
        ..., 
        min_length=2,
        description="La demande de modification suivante ou la réponse à une question de clarification."
    )

class ModificationResponse(BaseModel):
    """
    Le modèle de réponse standard que notre API renverra après chaque tour de modification.
    """
    thread_id: str = Field(
        ...,
        description="L'ID de la session à utiliser pour la prochaine requête."
    )
    message_to_user: str = Field(
        ...,
        description="Un message généré pour l'utilisateur (ex: 'J'ai supprimé la section. Autre chose ?' ou une question)."
    )
    current_course_state: CompleteCourse = Field(
        ...,
        description="L'état actuel du cours après l'application des modifications."
    )
    is_finalized: bool = Field(
        default=False,
        description="Passe à 'True' uniquement lorsque l'utilisateur a confirmé que le cours est terminé."
    )







class RemoveParams(BaseModel):
    section_title: str = Field(..., description="Le titre EXACT de la section à supprimer.")

class AddParams(BaseModel):
    topic_to_add: str = Field(..., description="Un titre concis pour la nouvelle section à ajouter.")
    youtube_search_query: str = Field(..., description="Une requête de recherche YouTube efficace pour ce nouveau sujet.")

class ReplaceParams(BaseModel):
    section_to_replace: str = Field(..., description="Le titre EXACT de la section à remplacer.")
    new_topic: str = Field(..., description="Le nouveau sujet qui remplacera l'ancien.")
    youtube_search_query: str = Field(..., description="Une requête de recherche YouTube pour le nouveau sujet.")

class ClarifyParams(BaseModel):
    question_to_user: str = Field(..., description="La question spécifique et claire à poser à l'utilisateur pour obtenir plus de détails.")

class FinalizeParams(BaseModel):
    final_message: str = Field(..., description="Un bref message de confirmation positif pour l'utilisateur.")

class ActionClassifier(BaseModel):
    action: Literal["REMOVE", "ADD", "REPLACE", "CLARIFY", "FINALIZE"]

class ModificationGraphState(TypedDict):
    """
    Définit la structure de la 'mémoire' pour notre graphe de modification de cours.
    """
    original_course: Dict 
    working_course: Dict    
    user_request: str                 

    modification_plan: Optional[Dict] 
    
    newly_found_resources: Optional[List[AnalyzedPlaylist]]

    message_to_user: str

    operation_report: Optional[str]
    
    is_finalized: bool
