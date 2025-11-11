# in dependencies.py
from langgraph.pregel import Pregel
from .graph import create_conversation_graph, create_syllabus_generation_graph
from src.cleeroute.langGraph.learners_api.course_update.graph import build_modification_graph
import asyncio
# This global variable will hold our compiled graph instance.

_conversation_graph: Pregel | None = None
_syllabus_graph: Pregel | None = None
_modification_graph: Pregel | None = None

# def get_conversation_graph() -> Pregel:
#     global _conversation_graph
#     if _conversation_graph is None:
#         _conversation_graph = create_conversation_graph()
#     return _conversation_graph

# def get_syllabus_graph() -> Pregel:
#     global _syllabus_graph
#     if _syllabus_graph is None:
#         _syllabus_graph = create_syllabus_generation_graph()
#     return _syllabus_graph

# Un verrou pour s'assurer que chaque graphe n'est construit qu'une seule fois
_convo_lock = asyncio.Lock()
_syllabus_lock = asyncio.Lock()


async def get_conversation_graph() -> Pregel:
    """
    Dépendance asynchrone qui initialise le graphe de conversation une seule fois.
    """
    global _conversation_graph
    # On utilise un verrou pour les cas où deux requêtes arrivent en même temps
    async with _convo_lock:
        if _conversation_graph is None:
            print("--- LAZY INIT: Building conversation graph for the first time ---")
            # Comme cette fonction est 'async', elle s'exécute dans l'event loop principal.
            # L'appel à create_conversation_graph() se fera donc dans le bon contexte.
            _conversation_graph = create_conversation_graph()
    return _conversation_graph

async def get_syllabus_graph() -> Pregel:
    """
    Dépendance asynchrone qui initialise le graphe de génération de syllabus une seule fois.
    """
    global _syllabus_graph
    async with _syllabus_lock:
        if _syllabus_graph is None:
            print("--- LAZY INIT: Building syllabus generation graph for the first time ---")
            _syllabus_graph = create_syllabus_generation_graph()
    return _syllabus_graph


def get_updated_graph() -> Pregel:
    global _modification_graph
    if _modification_graph is None:
        _modification_graph = build_modification_graph()
    return _modification_graph

