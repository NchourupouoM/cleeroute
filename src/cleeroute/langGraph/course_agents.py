from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from typing import TypedDict
from fastapi import APIRouter
import os
from dotenv import load_dotenv
from src.cleeroute.models import (
    Course,
    CourseInput
)

from src.cleeroute.langGraph.prompt_tamplate import COURSE_STRUCTURE_PROMPT
load_dotenv()

llm = ChatGoogleGenerativeAI(
    model=os.getenv("MODEL_2"),
    google_api_key=os.getenv("GEMINI_API_KEY"),
)

# stateGraphe
class GraphState(TypedDict):
    metatadata: CourseInput
    course: Course

def Course_structurer_agent():
    structure_llm = llm.with_structured_output(Course)
    prompt = ChatPromptTemplate.from_template(COURSE_STRUCTURE_PROMPT)
    return prompt | structure_llm

# node 
def Couse_structure_node(state: GraphState) -> GraphState:
    """ 
    This node generates a course structure based on the provided metadata.
    """
    agent = Course_structurer_agent()
    metadata = state["metatadata"]
    response = agent.invoke({
        "title": metadata.title,
        "domains": metadata.domains,
        "categories": metadata.categories,
        "topics": metadata.topics,
        "objectives": metadata.objectives,
        "expectations": metadata.expectations,
        "prerequisites": metadata.prerequisites,
        "desired_level": metadata.desired_level
    })
    
    course = Course.model_validate(response)
    return {"course": course}

def get_course_structure_graph():
    """
    This function creates a state graph for generating course structures.
    """
    workflow = StateGraph(GraphState)
    workflow.add_node( "course_structure",Couse_structure_node)
    workflow.set_entry_point("course_structure")
    workflow.add_edge("course_structure", END)
    return workflow.compile()

# API Router
course_structure_router = APIRouter()

@course_structure_router.post("/course_structure")
async def course_structure(metadata: CourseInput):
    """
    Endpoint to generate a course structure based on the provided metadata.
    """
    graph = get_course_structure_graph()
    result = graph.invoke({
        "metatadata": metadata,
        "course": None
    })
    
    return result["course"]