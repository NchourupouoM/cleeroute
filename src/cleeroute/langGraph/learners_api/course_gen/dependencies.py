# in dependencies.py
from langgraph.pregel import Pregel
from .graph import create_conversation_graph, create_syllabus_generation_graph
from src.cleeroute.langGraph.learners_api.course_update.graph import build_modification_graph
from src.cleeroute.db.checkpointer import get_checkpointer
import asyncio
# This global variable will hold our compiled graph instance.

_modification_graph: Pregel | None = None

async def get_conversation_graph():
    # Vérifiez si une boucle d'événements existe
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Créez une boucle temporairement
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Initialisez le checkpointer
    checkpointer = get_checkpointer()
    return create_conversation_graph(checkpointer)

async def get_syllabus_graph():
    # Même logique pour le graphe de syllabus
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    checkpointer = get_checkpointer()
    return create_syllabus_generation_graph(checkpointer)


def get_updated_graph() -> Pregel:
    global _modification_graph
    if _modification_graph is None:
        _modification_graph = build_modification_graph()
    return _modification_graph

