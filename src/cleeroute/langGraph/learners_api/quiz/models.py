# Fichier: src/cleeroute/langGraph/learners_api/quiz/models.py

from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Literal, Dict, TypedDict, Any
from datetime import datetime

# ==============================================================================
# 1. MODÈLES POUR LES QUESTIONS DU QUIZ
# Ces modèles représentent la structure d'une question.
# ==============================================================================

class QuizQuestion(BaseModel):
    """Représente une seule question du quiz telle qu'elle est envoyée au frontend."""
    questionId: str = Field(..., description="Identifiant unique de la question (ex: 'q_uuid_01').")
    questionText: str = Field(..., description="Le texte complet de la question.")
    options: List[str] = Field(..., description="Une liste de chaînes de caractères pour les options de réponse.")

class QuizQuestionInternal(QuizQuestion):
    """
    Modèle interne qui étend QuizQuestion avec des informations sensibles
    qui NE SERONT PAS envoyées au frontend.
    """
    correctAnswerIndex: int = Field(
        ..., 
        description="L'index (0, 1, 2, 3) de la bonne réponse dans la liste 'options'."
    )
    explanation: str = Field(
        ..., 
        description="Une brève explication de pourquoi la réponse est correcte."
    )
class QuizContent(BaseModel):
    """
    Un modèle conteneur pour la sortie complète de la génération de quiz.
    Le LLM doit générer un objet de ce type en une seule fois.
    """
    title: str = Field(..., description="Un titre court, clair et engageant pour le quiz.")
    questions: List[QuizQuestionInternal] = Field(..., description="La liste des questions de quiz générées.")

# ==============================================================================
# 2. MODÈLES POUR L'HISTORIQUE DU CHAT
# Ces modèles structurent chaque message de la conversation.
# ==============================================================================

class ChatMessage(BaseModel):
    """Représente un seul message dans l'historique de la conversation."""
    id: str = Field(..., description="Identifiant unique du message (ex: 'chat_msg_001').")
    sender: Literal["user", "ai"] = Field(..., description="Qui a envoyé le message.")
    content: str = Field(..., description="Le contenu textuel du message.")
    isCorrect: Optional[bool] = Field(None, description="Pour les réponses de l'IA, indique si la réponse de l'utilisateur était correcte.")
    type: Optional[str] = Field(None, description="Un type spécial pour certains messages de l'IA, ex: 'recap'.")
    stats: Optional[Dict[str, int]] = Field(None, description="Statistiques pour un message de type 'recap' (pass, fail, skipped).")
    recapText: Optional[str] = Field(None, description="Texte de résumé pour un message de type 'recap'.")

# ==============================================================================
# 3. MODÈLES POUR LES REQUÊTES ET RÉPONSES DE L'API
# Ces modèles définissent le contrat de votre API REST.
# ==============================================================================

# --- Requêtes (ce que le frontend envoie) ---

class StartQuizRequest(BaseModel):
    """Corps de la requête pour POST /api/v1/quiz-attempts."""
    scope: Literal["course", "section", "subsection", "video"]
    threadId: str # ID du cours
    sectionId: Optional[str] = None
    subsectionId: Optional[str] = None
    videoId: Optional[str] = None

    content_for_quiz: str = Field(
        ..., 
        description="A string containing all the relevant text (descriptions, etc.) for the chosen scope, which will be used to generate questions."
    )

    preferences: Dict[str, Any] # ex: {"difficulty": "Intermediate", "questionCount": 5}

    class Config:
        json_schema_extra = {
            "examples": [
                {
                        "scope": "subsection",
                        "threadId": "b83e5680-95ab-4df1-88f2-942570e43968",
                        "sectionId": "section_uuid_67890",
                        "subsectionId": "subsection_uuid_abcde",
                        "content_for_quiz": "React Router is a standard library for routing in React. It enables the navigation among views of various components in a React Application, allows changing the browser URL, and keeps the UI in sync with the URL. This video provides a complete tutorial on React Router.",
                        "preferences": {
                            "difficulty": "Intermediate",
                            "questionCount": 3
                        }
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

# --- Réponses (ce que le backend renvoie) ---

class QuizAttemptResponse(BaseModel):
    """Réponse pour POST /api/v1/quiz-attempts."""
    attemptId: str
    title: str
    questions: List[QuizQuestion] # Important: utilise le modèle public, sans la bonne réponse
    chatHistory: List[ChatMessage]

class ChatHistoryResponse(BaseModel):
    """Réponse standard pour les interactions qui mettent à jour le chat."""
    chatHistory: List[ChatMessage]

class QuizzesForCourseResponse(BaseModel):
    """Modèle pour la liste des quiz d'un cours."""
    attemptId: str
    title: str
    passPercentage: float

# ==============================================================================
# 4. ÉTAT INTERNE DU GRAPHE LANGGRAPH
# C'est la "mémoire" de chaque session de quiz, qui sera sauvegardée
# dans la base de données par le checkpointer.
# ==============================================================================

class QuizGraphState(TypedDict):
    """
        Définit la structure de la mémoire pour une seule tentative de quiz.\
    """
    
    attemptId: str
    title: str
    context: Dict[str, Any]
    preferences: Dict[str, Any]
    
    questions: str

    user_answers: Dict[str, Dict] 
    
    chat_history: str 

    current_interaction: Optional[Dict]



# Model for libre QA 

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


# class QAHistoryItem(BaseModel):
#     id: str
#     scope: str
#     question: str
#     answer: str
#     contextTitle: Optional[str] = None
#     createdAt: datetime