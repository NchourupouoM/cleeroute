# from langchain_google_genai import ChatGoogleGenerativeAI
# from langchain_groq import ChatGroq
# from langchain_core.prompts import ChatPromptTemplate
# from langgraph.graph import StateGraph, END
# from typing import TypedDict
# from fastapi import APIRouter, Header, HTTPException
# from typing import Optional, List
# from pydantic import BaseModel
# import os
# from dotenv import load_dotenv
# from src.cleeroute.models import (
#     Subsection,
#     CourseInput
# )

# class Section(BaseModel):
#     title: str
#     description: str
#     subsections: List[Subsection]

# class Course(BaseModel):
#     title: str
#     introduction: Optional[str] = None
#     sections: List[Section]

# from src.cleeroute.langGraph.learners_api.metadata_from_learner.prompt_tamplate import COURSE_STRUCTURE_PROMPT
# load_dotenv()


# # llm = ChatGoogleGenerativeAI(
# #     model=os.getenv("MODEL"),
# #     google_api_key=os.getenv("GEMINI_API_KEY"),
# # )


# # stateGraphe
# class GraphState(TypedDict):
#     metatadata: CourseInput
#     course: Course

# # cette instance du LLM en paramettre permet de a l'utilisateur de passer une cle API a travers l'interface.
# def Course_structurer_agent(llm_instance: ChatGoogleGenerativeAI):
#     structure_llm = llm_instance.with_structured_output(Course)
#     prompt = ChatPromptTemplate.from_template(COURSE_STRUCTURE_PROMPT)
#     return prompt | structure_llm

# # node 
# def Couse_structure_node(state: GraphState, llm_instance_node: ChatGoogleGenerativeAI) -> GraphState:
#     """ 
#     This node generates a course structure based on the provided metadata.
#     """
#     agent = Course_structurer_agent(llm_instance=llm_instance_node)
#     metadata = state["metatadata"]
#     response = agent.invoke({
#         "title": metadata.title,
#         "domains": metadata.domains,
#         "categories": metadata.categories,
#         "topics": metadata.topics,
#         "objectives": metadata.objectives,
#         "expectations": metadata.expectations,
#         "prerequisites": metadata.prerequisites,
#         "desired_level": metadata.desired_level
#     })
    
#     course = Course.model_validate(response)
#     return {"course": course}

# def get_course_structure_graph(llm_to_use: ChatGoogleGenerativeAI = None):
#     """
#     This function creates a state graph for generating course structures.
#     """
#     workflow = StateGraph(GraphState)
#     # Pour passer des arguments aux nœuds dans LangGraph, vous utilisez partial ou une fonction lambda
#     workflow.add_node( "course_structure",lambda state: Couse_structure_node(state, llm_to_use))
#     workflow.set_entry_point("course_structure")
#     workflow.add_edge("course_structure", END)
#     return workflow.compile()

# # API Router
# course_structure_router = APIRouter()

# @course_structure_router.post("/course_structure")
# async def course_structure(
#     metadata: CourseInput, 
#     x_gemini_api_key: Optional[str] = Header(None, alias="X-Gemini-Api-Key")
#     ):
#     """
#     Endpoint to generate a course structure based on the provided metadata.

#     Allows user to provide their own Gemini API key as a query parameter just for development purposes.
#     """

#     # just for development purpose, allowing users to provide their own Gemini API key.
#     api_key_to_use = x_gemini_api_key if x_gemini_api_key else os.getenv("GEMINI_API_KEY")

#     if not api_key_to_use:
#         raise HTTPException(status_code=400, detail="Gemini API key is not provided. Please provide it via 'X-Gemini-Api-Key' header or set GEMINI_API_KEY in .env.")
    
#     llm_to_use = ChatGoogleGenerativeAI(
#         model=os.getenv("MODEL"),
#         google_api_key=api_key_to_use,
#     )

#     graph = get_course_structure_graph(llm_to_use=llm_to_use)
#     result = graph.invoke({
#         "metatadata": metadata,
#         "course": None
#     })
    
#     return result["course"]