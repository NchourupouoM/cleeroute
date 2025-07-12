from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
from typing import List, Dict, Any

import src.cleeroute.langGraph.prompt_tamplate as prompts
from src.cleeroute.models import Section, Project, Subsection
import os

from dotenv import load_dotenv
load_dotenv()


llm = ChatGoogleGenerativeAI(model=os.getenv("MODEL_2"), google_api_key=os.getenv("GEMINI_API_KEY"))

# llm = ChatGroq(model="llama-3.1-8b-instant", api_key=os.getenv("GROQ_API_KEY"))

class OutlineSection(BaseModel):
    title: str = Field(description="The concise and informative title of the course section.")
    description: str = Field(description="A detailed paragraph explaining what will be covered in this section.")

class SectionDetailOutput(BaseModel):
    subsections: List[Subsection] = Field(description="List of subsections, each a dict with 'title' and 'description'")
    project: Project = Field(description="A dictionary representing the project details")

class CourseOutline(BaseModel):
    title: str = Field(description="The main title for the entire course.")
    sections: List[OutlineSection] = Field(description="The list of all main sections that make up the course.")

# Agent 1: Planer
def get_planner_agent():
    prompt = ChatPromptTemplate.from_template(prompts.PLANNER_PROMPT)
    return prompt | llm

# Agent 2: Searcher
def get_research_agent():
    prompt = ChatPromptTemplate.from_template(prompts.RESEARCH_PROMPT)
    return prompt | llm

# Agent 3: Structurer
def get_outline_agent():
    structured_llm = llm.with_structured_output(CourseOutline)
    prompt = ChatPromptTemplate.from_template(prompts.OUTLINE_AGENT_PROMPT)
    return prompt | structured_llm

# Agent 4: Detailer
def get_detailing_agent():
    structured_llm = llm.with_structured_output(SectionDetailOutput)
    prompt = ChatPromptTemplate.from_template(prompts.DETAILING_AGENT_PROMPT)
    return prompt | structured_llm

# Agent 5: Assembler
def get_assembler_agent():
    prompt = ChatPromptTemplate.from_template(prompts.ASSEMBLER_PROMPT)
    return prompt | llm