import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.cleeroute.models import CourseInput
from src.cleeroute.langGraph.workflow import get_course_graph

router = APIRouter()

@router.post("/generate-course-stream")
async def generate_course_stream(request: CourseInput):
    
    graph = get_course_graph()
    
    async def stream_generator():
        inputs = {"initial_request": request}
        
        nodes_to_stream_data = {"outliner", "detailer", "assembler"}
        
        async for output in graph.astream(inputs):
            for node_name, node_data in output.items():
                print(f"--- Backend: Réception du noeud: {node_name} ---")

                if node_name == "initial_request":
                    continue

                if node_name in nodes_to_stream_data:
                    response_chunk = {
                        "event": node_name, # ex: "outliner", "detailer"
                        "data": node_data
                    }
                    yield f"data: {json.dumps(response_chunk)}\n\n"
                
                else:
                    response_chunk = {
                        "event": "status",
                        "message": f"Step '{node_name}' completed. Moving to the next step..."
                    }
                    yield f"data: {json.dumps(response_chunk)}\n\n"

        # Signal de fin
        yield f"data: {json.dumps({'event': 'end'})}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")