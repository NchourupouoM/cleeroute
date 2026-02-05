# from langchain_google_genai import ChatGoogleGenerativeAI
# from langchain_groq import ChatGroq
# from langchain_core.prompts import ChatPromptTemplate
# from langgraph.graph import StateGraph, END
# from typing import TypedDict, Optional
# from pydantic import BaseModel
# from fastapi import APIRouter, Header, HTTPException
# import os
# from dotenv import load_dotenv
# from ..models import Project

# from src.cleeroute.langGraph.learners_api.metadata_from_learner.prompt_tamplate import PROGECT_GENERATE_PROMPT
# load_dotenv()


# # llm = ChatGoogleGenerativeAI(
# #     model=os.getenv("MODEL_2"),
# #     google_api_key=os.getenv("GEMINI_API_KEY"),
# # )

# class RequiredGenProjInput(BaseModel):
#     class Config:
#         json_schema_extra = {
#             "examples": [
#                 {
#                 "course_title": "Advanced English Fluency: Mastering Natural Pronunciation and Idiomatic Language",
#                 "section_title": "Fundamentals of English Phonetics",
#                 "section_description": "Understand the core principles of English phonetics to improve pronunciation accuracy.",
#                 "subsection_titles_concatenated": "Introduction to the International Phonetic Alphabet (IPA) + Mastering Vowel Sounds + Mastering Consonant Sounds + Correcting Common Pronunciation Errors"
#             }
#          ]
#     }
#     course_title: str
#     section_title: str
#     section_description: str
#     subsection_titles_concatenated: str


# # stateGraphe
# class GraphState(TypedDict):
#     requiredInput: RequiredGenProjInput
#     project: Project

# def Project_gen_agent(llm_instance: ChatGoogleGenerativeAI):
#     structure_llm = llm_instance.with_structured_output(Project)
#     prompt = ChatPromptTemplate.from_template(PROGECT_GENERATE_PROMPT)
#     return prompt | structure_llm


# def project_content_node(state: GraphState, llm_instance: ChatGoogleGenerativeAI) -> GraphState:
#     """ 
#     This node generates a project content based on the provided metadata.
#     """
#     agent = Project_gen_agent(llm_instance=llm_instance)
#     requiredInput = state["requiredInput"]
#     response = agent.invoke({
#         "course_title": requiredInput.course_title,
#         "section_title": requiredInput.section_title,
#         "section_description": requiredInput.section_description,
#         "subsection_titles_concatenated": requiredInput.subsection_titles_concatenated
#     })
    
#     project = Project.model_validate(response)
#     return {"project": project}

# def get_project_structure_graph(llm_instance: ChatGoogleGenerativeAI):
#     """
#     This function creates a state graph for generating project content.
#     """
#     workflow = StateGraph(GraphState)
#     workflow.add_node( "project_content_node",lambda state: project_content_node(state, llm_instance=llm_instance))
#     workflow.set_entry_point("project_content_node")
#     workflow.add_edge("project_content_node", END)
#     return workflow.compile()

# # API Router
# project_content_router = APIRouter()

# @project_content_router.post("/project_content")
# async def course_structure(
#     requiredInput: RequiredGenProjInput,
#     x_gemini_api_key: Optional[str] = Header(None, alias="X-Gemini-Api-Key")
# ):
#     """
#     Endpoint to generate a course structure based on the provided metadata.
#     """
#     api_key_to_use = x_gemini_api_key if x_gemini_api_key else os.getenv("GEMINI_API_KEY")

#     if not api_key_to_use:
#         raise HTTPException(status_code=400, detail="Gemini API key is not provided. Please provide it via 'X-Gemini-Api-Key' header or set GEMINI_API_KEY in .env.")
    
#     llm_to_use = ChatGoogleGenerativeAI(
#         model=os.getenv("MODEL_2"),
#         google_api_key=api_key_to_use,
#     )

#     graph = get_project_structure_graph(llm_instance=llm_to_use)
#     result = graph.invoke({
#         "requiredInput": requiredInput,
#         "project": None
#     })
    
#     return result["project"]