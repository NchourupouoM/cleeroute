from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import Field
from typing import Dict, Any, TypedDict
from fastapi.responses import StreamingResponse

from langgraph.graph import StateGraph, END 
from fastapi import APIRouter

import src.cleeroute.langGraph.prompt_tamplate as prompts
from src.cleeroute.models import Course_meta_datas, Course_meta_datas_input
from langchain_groq import ChatGroq
import os
import json
from dotenv import load_dotenv
load_dotenv()

# --- Définitions (inchangées) ---
llm = ChatGoogleGenerativeAI(model=os.getenv("MODEL"), google_api_key=os.getenv("GEMINI_API_KEY"))

# llm = ChatGroq(model="llama-3.1-8b-instant", api_key="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")

class GraphState(TypedDict):
    initial_request: Course_meta_datas_input
    course_meta_data: Dict 

def meta_data_gen_agent():
    structured_llm = llm.with_structured_output(Course_meta_datas)
    prompt = ChatPromptTemplate.from_template(prompts.COURSE_META_DATA_PROMPT)
    return prompt | structured_llm

def meta_data_gen_node(state: GraphState) -> Dict[str, Any]:
    print("--- Execution ---")
    agent = meta_data_gen_agent()
    result: Course_meta_datas = agent.invoke(state["initial_request"].model_dump())
    print(f"--- INFO: Meta-data generated for '{result.title}' course ---")
    return {"course_meta_data": result.model_dump()}

def get_meta_data_graph():
    workflow = StateGraph(GraphState)
    workflow.add_node("meta_data_gen", meta_data_gen_node)
    workflow.set_entry_point("meta_data_gen")
    workflow.add_edge("meta_data_gen", END)
    return workflow.compile()

router_metadata = APIRouter()

@router_metadata.post("/generate-stream", response_model=Course_meta_datas)
async def generate_metadata_stream(request: Course_meta_datas_input):
    """
    Takes a simple user request and STREAMS the result of the metadata generation.
    """
    graph = get_meta_data_graph()
    
    async def stream_generator():
        inputs = {"initial_request": request}
        
        async for output in graph.astream(inputs):

            if "meta_data_gen" in output:
                response_chunk = {
                    "event": "metadata_ready",
                    "data": output["meta_data_gen"]["course_meta_data"]
                }
                
                yield f"data: {json.dumps(response_chunk)}\n\n"
        
        yield f"data: {json.dumps({'event': 'end'})}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")