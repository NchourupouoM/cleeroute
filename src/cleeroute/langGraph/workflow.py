from typing import TypedDict, List, Dict
from langgraph.graph import StateGraph, END
import json

from src.cleeroute.langGraph.course_agents import (
    get_planner_agent, get_research_agent, get_outline_agent, 
    get_detailing_agent, get_assembler_agent, CourseOutline
)
from src.cleeroute.models import CourseInput, Section, Course

# Graph state
class GraphState(TypedDict):
    initial_request: CourseInput
    course_brief: str
    research_notes: str
    course_title: str
    outline: List[Dict] 
    detailed_sections: List[Dict] 
    final_course: dict

# Node functions
# Each function corresponds to a node in the graph and processes the state accordingly.
# They are responsible for invoking the respective agents and returning the updated state.
def planner_node(state: GraphState):
    print("--- planner node execution ---")
    agent = get_planner_agent()
    result = agent.invoke(state["initial_request"].model_dump())
    print(result.content)
    return {"course_brief": result.content}

def research_node(state: GraphState):
    print("--- Search node execution ---")
    agent = get_research_agent()
    result = agent.invoke({"course_brief": state["course_brief"]})
    print(result.content)
    return {"research_notes": result.content}

def outline_node(state: GraphState):
    print("--- Outline node execution ---")
    agent = get_outline_agent()
    
    # L'agent retourne directement un objet Pydantic grâce à with_structured_output
    result: CourseOutline = agent.invoke({
        "course_brief": state["course_brief"],
        "research_notes": state["research_notes"]
    })

    print(f"--- INFO: Found title: '{result.title}' and {len(result.sections)} sections ---")
    
   
    sections_as_dicts = [section.model_dump() for section in result.sections]
    
    return {"outline": sections_as_dicts, "course_title": result.title}

def detailing_node(state: GraphState):
    print("--- detailling node execution ---")
    agent = get_detailing_agent()
    detailed_sections_as_dicts = []
    
    for section_outline in state["outline"]:
        print(f"-> Section details : {section_outline['title']}")
        result = agent.invoke({
            "course_brief": state["course_brief"],
            "section_title": section_outline["title"],
            "section_description": section_outline["description"]
        })
        
        result_as_dict = result.model_dump()

        full_section_obj = Section(
            title=section_outline["title"],
            description=section_outline["description"],
            subsections=result_as_dict["subsections"], 
            project=result_as_dict["project"]
        )
        
        detailed_sections_as_dicts.append(full_section_obj.model_dump())
        
    return {"detailed_sections": detailed_sections_as_dicts}


def assembler_node(state: GraphState):
    print("--- Assembler node execution---")
    agent = get_assembler_agent()
    sections_summary = "\n".join([f"- {s['title']}: {s['description']}" for s in state["detailed_sections"]])
    
    introduction = agent.invoke({
        "course_title": state["course_title"],
        "sections_summary": sections_summary
    }).content
    
    final_course = {
        "title": state["course_title"],
        "introduction": introduction,
        "sections": state["detailed_sections"]
    }
    
    print("--- final course assembler ---")
    return {"final_course": final_course}

def get_course_graph():
    workflow = StateGraph(GraphState)

    workflow.add_node("planner", planner_node)
    workflow.add_node("researcher", research_node)
    workflow.add_node("outliner", outline_node)
    workflow.add_node("detailer", detailing_node)
    workflow.add_node("assembler", assembler_node)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "researcher")
    workflow.add_edge("researcher", "outliner")
    workflow.add_edge("outliner", "detailer")
    workflow.add_edge("detailer", "assembler")
    workflow.add_edge("assembler", END)

    return workflow.compile()