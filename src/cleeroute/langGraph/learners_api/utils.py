# for retrying after an error or llm timeout anf hallucination
from langgraph.types import RetryPolicy
from google.api_core import exceptions
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
import os
from dotenv import load_dotenv
load_dotenv()


def get_llm(api_key: str = None) -> ChatGoogleGenerativeAI:
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY")
    return ChatGoogleGenerativeAI(
        model=os.getenv("MODEL_2", "gemini-flash-lite-latest"), 
        google_api_key=api_key,
        temperature=0.2
    )

def get_vision_model(api_key: str = None) -> ChatGoogleGenerativeAI:
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY")
    return ChatGoogleGenerativeAI(
        model=os.getenv("VISION_MODEL", "gemini-2.5-flash"), 
        google_api_key=api_key,
        temperature=0.1
    )

def get_embedding_model(api_key: str = None):
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY")
    return GoogleGenerativeAIEmbeddings(
        model=os.getenv("EMBEDDING_MODEL", EMBEDDING_MODEL),
        google_api_key=api_key,
        task_type="retrieval_document"
    )

resilient_retry_policy = RetryPolicy(
    max_attempts=3,
    retry_on=[TimeoutError, ConnectionError, exceptions.ResourceExhausted ],
    initial_interval=1.0,
    backoff_factor=2.0,
    jitter=True
)

