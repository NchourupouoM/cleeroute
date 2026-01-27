# in dependencies.py
from langgraph.pregel import Pregel
from .graph_gen import create_syllabus_generation_graph
from .graph_conv import create_conversation_graph
from src.cleeroute.db.checkpointer import get_checkpointer
import asyncio

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