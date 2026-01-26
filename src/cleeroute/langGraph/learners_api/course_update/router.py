# import uuid
# import asyncio
# from typing import Optional
# from fastapi import APIRouter, HTTPException, Depends
# from langgraph.pregel import Pregel

# # 1. Importations des modèles et des composants du graphe
# from .model import StartModificationRequest, ContinueModificationRequest, ModificationResponse
# from src.cleeroute.langGraph.learners_api.course_gen.dependencies import get_updated_graph
# from .graph import build_modification_graph

# updated_router = APIRouter()


# @updated_router.post("/start_modification", response_model=ModificationResponse)
# async def start_modification(
#     request: StartModificationRequest,
#     mod_graph: Pregel = Depends(get_updated_graph)
#     ):
#     """
#     Démarre une nouvelle session de modification de cours.
#     Crée un nouveau thread et exécute le graphe jusqu'à la première interruption.
#     """
#     # 3. Création d'un NOUVEAU thread_id pour cette session de modification
#     thread_id = str(uuid.uuid4())
#     config = {"configurable": {"thread_id": thread_id}}
    
#     print(f"--- Démarrage d'une nouvelle session de modification [Thread ID: {thread_id}] ---")

#     # 4. Définition de l'état initial du graphe
#     initial_state = {
#         "original_course": request.chosen_course.model_dump(mode="json"),
#         "working_course": request.chosen_course.model_copy(deep=True).model_dump(mode="json"),
#         "user_request": request.user_request,
#         "is_finalized": False,
#     }

#     final_state = None
#     # On exécute le graphe et on garde le résultat de la TOUTE DERNIÈRE mise à jour.
#     async for state_update in mod_graph.astream(initial_state, config=config):
#         final_state = state_update
        
#     # Le 'final_state' est un dictionnaire qui contient les sorties des derniers nœuds.
#     # On accède directement aux clés de ce dictionnaire.
#     if final_state is None:
#         raise HTTPException(status_code=500, detail="Graph execution did not produce a final state.")

#     # On extrait les valeurs du dictionnaire de l'état final.
#     # Le nom du canal (la clé) peut varier, donc on prend la première valeur.
#     final_values = list(final_state.values())[0]
#     # 6. Construction et envoi de la réponse
#     return ModificationResponse(
#         thread_id=thread_id,
#         # On utilise le 'final_values' que nous venons d'extraire
#         message_to_user=final_values.get("message_to_user", "An error occurred."),
#         current_course_state=final_values.get("working_course"),
#         is_finalized=final_values.get("is_finalized", False)
#     )


# @updated_router.post(
#         "/continue_modification", 
#         response_model=ModificationResponse
# )
# async def continue_modification(
#     request: ContinueModificationRequest,
#     mod_graph: Pregel = Depends(get_updated_graph)
# ):
#     """
#     Continue une session de modification existante avec une nouvelle demande de l'utilisateur.
#     """

#     thread_id = request.thread_id
#     config = {"configurable": {"thread_id": thread_id}}

#     print(f"--- Continuation de la session de modification [Thread ID: {thread_id}] ---")

#     # 1. Lire l'état actuel
#     current_state = await mod_graph.aget_state(config)
#     if not current_state:
#         raise HTTPException(status_code=404, detail="Session thread not found.")
    
#     # On prend la première (et seule) valeur du dictionnaire des canaux
#     state_values = list(current_state.values.values())[0]
#     state_values["user_request"] = request.user_request

#     # 7. Mise à jour de l'état avec la nouvelle requête de l'utilisateur AVANT de relancer
#     final_state = None
#     async for state_update in mod_graph.astream(state_values, config=config):
#         final_state = state_update

#     if final_state is None:
#         # Cette erreur ne devrait plus se produire
#         raise HTTPException(status_code=500, detail="Graph execution did not produce a final state after continuation.")

#     final_values = list(final_state.values())[0]

#     # 9. Construction et envoi de la réponse
#     return ModificationResponse(
#         thread_id=thread_id,
#         message_to_user=final_values.get("message_to_user", "An error occurred."),
#         current_course_state=final_values.get("working_course"),
#         is_finalized=final_values.get("is_finalized", False)
#     )