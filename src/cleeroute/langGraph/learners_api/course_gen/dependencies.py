# We don't need 'Request' from FastAPI anymore for this dependency
from langgraph.pregel import Pregel
from .graph import create_conversation_graph, create_syllabus_generation_graph
from src.cleeroute.langGraph.learners_api.course_update.graph import build_modification_graph

# This global variable will hold our compiled graph instance.

_conversation_graph: Pregel | None = None
_syllabus_graph: Pregel | None = None
_modification_graph: Pregel | None = None

def get_conversation_graph() -> Pregel:
    global _conversation_graph
    if _conversation_graph is None:
        _conversation_graph = create_conversation_graph()
    return _conversation_graph

def get_syllabus_graph() -> Pregel:
    global _syllabus_graph
    if _syllabus_graph is None:
        _syllabus_graph = create_syllabus_generation_graph()
    return _syllabus_graph

def get_updated_graph() -> Pregel:
    global _modification_graph
    if _modification_graph is None:
        _modification_graph = build_modification_graph()
    return _modification_graph

