
from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Literal, Dict, TypedDict, Any
from datetime import datetime
from enum import Enum


class ChatMessage(BaseModel):
    """Représente un seul message dans l'historique de la conversation."""
    id: str = Field(..., description="Identifiant unique du message (ex: 'chat_msg_001').")
    sender: Literal["user", "ai"] = Field(..., description="Qui a envoyé le message.")
    content: str = Field(..., description="Le contenu textuel du message.")
    isCorrect: Optional[bool] = Field(None, description="Pour les réponses de l'IA, indique si la réponse de l'utilisateur était correcte.")
    type: Optional[str] = Field(None, description="Un type spécial pour certains messages de l'IA, ex: 'recap'.")
    stats: Optional[Dict[str, int]] = Field(None, description="Statistiques pour un message de type 'recap' (pass, fail, skipped).")
    recapText: Optional[str] = Field(None, description="Texte de résumé pour un message de type 'recap'.")

class ChatHistoryResponse(BaseModel):
    """Réponse standard pour les interactions qui mettent à jour le chat."""
    chatHistory: List[ChatMessage]


class CourseAskRequest(BaseModel):
    """
    Requête pour poser une question libre sur le contenu du cours.
    """
    scope: Literal["course", "section", "subsection"] = Field(..., description="La portée de la question.")
    
    # On utilise des index (int) car vos modèles Section/Subsection n'ont pas d'ID explicites.
    # Le frontend devra envoyer l'index de la section dans la liste (0, 1, 2...).
    sectionIndex: Optional[int] = Field(None, description="Index de la section (si scope='section' ou 'subsection').")
    subsectionIndex: Optional[int] = Field(None, description="Index de la sous-section (si scope='subsection').")
    
    userQuery: str = Field(..., description="La question libre de l'utilisateur.")

class CourseAskResponse(BaseModel):
    """
    Réponse de l'IA à la question libre.
    """
    answer: str
    contextUsed: str = Field(..., description="Résumé du contexte utilisé (ex: 'Section 2: Advanced React').")


# Models for global chat 
class CreateSessionRequest(BaseModel):
    """Payload pour créer une nouvelle conversation ciblée."""
    title: Optional[str] = "New Conversation"
    scope: Literal["course", "section", "subsection", "video"]
    sectionIndex: Optional[int] = None
    subsectionIndex: Optional[int] = None
    videoId: Optional[str] = None

    class Config:
        json_schema_extra = {
            "examples": [
                # CAS 1 : Discussion sur tout le cours
                {
                    "title": "General help on python programming",
                    "scope": "course",
                    "sectionIndex": None,
                    "subsectionIndex": None,
                    "videoId": None
                },
                # CAS 2 : Discussion sur une Section (Module 2)
                {
                    "title": "Questions sur les Structures de Données",
                    "scope": "section",
                    "sectionIndex": 1, # Index 1 = 2ème section
                    "subsectionIndex": None,
                    "videoId": None
                },
                # CAS 3 : Discussion sur une Sous-section précise
                {
                    "title": "Comprendre les List Comprehensions",
                    "scope": "subsection",
                    "sectionIndex": 1, 
                    "subsectionIndex": 2, # Index 2 = 3ème sous-section de la section 1
                    "videoId": None
                },
                # CAS 4 : Discussion sur une Vidéo spécifique
                {
                    "title": "Explication de la vidéo introductive",
                    "scope": "video",
                    "sectionIndex": None,
                    "subsectionIndex": None,
                    "videoId": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
                }
            ]
        }

class ChatSessionResponse(BaseModel):
    sessionId: str
    title: str
    scope: str
    updatedAt: datetime


class MessageResponse(BaseModel):
    sender: Literal["user", "ai"]
    messageId: str
    content: str
    createdAt: datetime

class ChatAskRequest(BaseModel):
    """Payload for asking a question in an existing chat session."""
    userQuery: str

    class config:
        json_schema_extra= {
            "examples": [
                {
                     "userQuery": "Pourquoi le code plante si je mets le Hook dans une condition if ?"
                }
            ]
        }


class AnswerRequest(BaseModel):
    """Corps de la requête pour POST /api/v1/quiz-attempts/{attemptId}/answer."""
    questionId: str
    answerIndex: int

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "questionId": "q_03",
                    "answerIndex": 1
                }

            ]
        }

class AskRequest(BaseModel):
    """Corps de la requête pour POST /api/v1/quiz-attempts/{attemptId}/ask."""
    questionId: Optional[str] = None # Contexte de la question
    userQuery: str

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "questionId": "q_1",
                    "userQuery": "Why was option C incorrect? I thought it was also a valid hook."
                }
            ]
        }

# 

# suppression d'une session de chat et mise à jour du titre 
class RenameSessionRequest(BaseModel):
    """Payload for renaming a chat session."""
    newTitle: str = Field(..., min_length=1, max_length=255, description="Le nouveau titre de la conversation.")

class SessionActionResponse(BaseModel):
    """The response after performing an action (rename or delete) on a chat session"""
    status: str
    sessionId: str
    message: str

#Edite a specifique message in a chat session
class EditMessageRequest(BaseModel):
    """Payload for editing a specific message in a chat session."""
    newContent: str = Field(..., min_length=1, description="The updated content of the message.")

#Delete a specifique message in a chat session
class DeleteResponse(BaseModel):
    """The response after deleting a specific message in a chat session."""
    status: str
    deletedCount: int
    message: str


# user profile 

class ResponseStyle(str, Enum):
    CASUAL = "casual"
    FORMAL = "formal"
    CONCISE = "concise"
    HUMOROUS = "humorous"
    EMPATHIC = "empathic"
    SIMPLIFIED = "simplified"
    CUSTOM = "custom"

class UserProfile(BaseModel):
    """
    Contient les données métier pour la personnalisation.
    Ces données viennent de votre table 'users' ou 'profiles'.
    """
    user_id: str
    language: str = "English"
    profession: str = "Learner" # ex: "Software Engineer", "Nurse"
    industries: str = "General"   # ex: "Tech", "Healthcare"
    motivation: str = "Personal Growth" # ex: "To get a promotion"
    response_style: ResponseStyle = ResponseStyle.CASUAL