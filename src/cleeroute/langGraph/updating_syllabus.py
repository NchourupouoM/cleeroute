from src.cleeroute.models import CompleteCourse
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field
from typing import TypedDict, List, Optional, Any
from fastapi import APIRouter
from dotenv import load_dotenv
import os 
from src.cleeroute.langGraph.sections_subsections_sep.models import (
    CourseInput,
    Course_section,
)
from src.cleeroute.langGraph.meta_data_gen import Course_summary, Course_details

class SyllabusUpdateState(BaseModel):
    complete_course_draft: CompleteCourse = Field(..., description="The complete course syllabus currently being updated.")
    feedback: str = Field(None, description="The feedback provided by the user for updating the syllabus.")
    modification_plan: str = Field(None, description="structure modification plan based on the feedback genrate by LLM.")
    human_approved : bool = Field(False, description="Indicates if the human has approved the modification plan.")
    