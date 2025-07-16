from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from typing import TypedDict
from pydantic import BaseModel
from fastapi import APIRouter
import os
from dotenv import load_dotenv
from src.cleeroute.models import (
    Project
)

from src.cleeroute.langGraph.prompt_tamplate import PROGECT_GENERATE_PROMPT
load_dotenv()

llm = ChatGoogleGenerativeAI(
    model=os.getenv("MODEL_2"),
    google_api_key=os.getenv("GEMINI_API_KEY"),
)

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


# stateGraphe
class GraphState(TypedDict):
    requiredInput: RequiredGenProjInput
    project: Project

def Project_gen_agent():
    structure_llm = llm.with_structured_output(Project)
    prompt = ChatPromptTemplate.from_template(PROGECT_GENERATE_PROMPT)
    return prompt | structure_llm

# node 
def project_content_node(state: GraphState) -> GraphState:
    """ 
    This node generates a project content based on the provided metadata.
    """
    agent = Project_gen_agent()
    requiredInput = state["requiredInput"]
    response = agent.invoke({
        "course_title": requiredInput.course_title,
        "section_title": requiredInput.section_title,
        "section_description": requiredInput.section_description,
        "subsection_titles_concatenated": requiredInput.subsection_titles_concatenated
    })
    
    project = Project.model_validate(response)
    return {"project": project}

def get_project_structure_graph():
    """
    This function creates a state graph for generating project content.
    """
    workflow = StateGraph(GraphState)
    workflow.add_node( "project_content_node",project_content_node)
    workflow.set_entry_point("project_content_node")
    workflow.add_edge("project_content_node", END)
    return workflow.compile()

# API Router
project_content_router = APIRouter()

@project_content_router.post("/project_content")
async def course_structure(requiredInput: RequiredGenProjInput):
    """
    Endpoint to generate a course structure based on the provided metadata.
    """
    graph = get_project_structure_graph()
    result = graph.invoke({
        "requiredInput": requiredInput,
        "project": None
    })
    
    return result["project"]