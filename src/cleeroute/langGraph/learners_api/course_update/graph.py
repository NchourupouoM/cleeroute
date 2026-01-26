# from .prompt import *
# from langchain_google_genai import ChatGoogleGenerativeAI
# from .model import ModificationGraphState,UpdateCourseIntroParams,UpdateCourseTitleParams,RemoveSectionParams,AddSectionParams, RemoveSubsectionParams,AddSubsectionParams,ReplaceSubsectionParams,ClarifyParams,FinalizeParams, ActionClassifier
# from langgraph.graph import StateGraph, END
# from src.cleeroute.langGraph.learners_api.course_gen.models import Section, Subsection,CompleteCourse,AnalyzedPlaylist
# from src.cleeroute.langGraph.learners_api.course_gen.services import search_and_filter_youtube_playlists
# from src.cleeroute.db.checkpointer import get_checkpointer
# from typing import Union
# import json
# import copy
# import os
# from dotenv import load_dotenv
# load_dotenv()

# from src.cleeroute.langGraph.learners_api.utils import resilient_retry_policy, get_llm


# # Initialisez votre LLM (à placer en haut du fichier)
# llm = get_llm(os.getenv("GEMINI_API_KEY"))
# checkpointer = get_checkpointer()

# def plan_modification_node(state: ModificationGraphState) -> ModificationGraphState:
#     """
#     Analyzes the user's request in a robust, two-step process.
#     Step 1: Classifies the user's intent.
#     Step 2: Generates the specific parameters for that intent.
#     """
#     print("--- NODE: Planning modification (2-Step, Clean Implementation) ---")

#     try:
#         working_course_obj = CompleteCourse(**state["working_course"])
#     except Exception as e:
#         # Sécurité : si la conversion échoue, on gère l'erreur proprement.
#         print(f"--- ERREUR : Impossible de charger working_course depuis l'état : {e} ---")
#         # On force une clarification pour éviter un crash.
#         plan_dict = {
#             "action": "CLARIFY",
#             "parameters": {"question_to_user": "I'm having a technical difficulty with the course structure. Could you please restart the editing process?"}
#         }
#         return {"modification_plan": plan_dict}
    
#     user_request = state["user_request"]
#     section_titles = [sec.title for sec in working_course_obj.sections]
    
#     # --- STEP 1: CLASSIFY THE ACTION ---
    
#     classifier_prompt = ACTION_CLASSIFIER_PROMPT.format(
#         user_request=user_request,
#     )
    
#     classifier_llm = llm.with_structured_output(ActionClassifier)
#     action_result = classifier_llm.invoke(classifier_prompt)
#     action_name = action_result.action
    
#     print(f"Step 1 - Classified Action: {action_name}")

#     # --- ÉTAPE 2: GÉNÉRATION DES PARAMÈTRES (avec les nouveaux modèles) ---
#     param_model_map = {
#         "UPDATE_COURSE_TITLE": (UpdateCourseTitleParams, "Extract the new title for the entire course."),
#         "UPDATE_COURSE_INTRODUCTION": (UpdateCourseIntroParams, "Extract the new introduction for the course."),
#         "REMOVE_SECTION": (RemoveSectionParams, "Extract the exact title of the SECTION to remove."),
#         "ADD_SECTION": (AddSectionParams, "Extract the topic for a NEW section and generate a search query."),
#         "REMOVE_SUBSECTION": (RemoveSubsectionParams, "Extract the SECTION title and the SUBSECTION title to remove."),
#         "ADD_SUBSECTION": (AddSubsectionParams, "Extract the target SECTION title, the new SUBSECTION topic, and a search query."),
#         "REPLACE_SUBSECTION": (ReplaceSubsectionParams, "Extract the target SECTION and SUBSECTION, the new topic, and a search query."),
#         "CLARIFY": (ClarifyParams, "..."),
#         "FINALIZE": (FinalizeParams, "...")
#     }
    
#     ParamModel, instruction = param_model_map[action_name]
    
#     parameter_prompt = PARAMETER_GENERATOR_PROMPT.format(
#         user_request=user_request, 
#         section_titles=json.dumps(section_titles), 
#         action_name=action_name,
#         instruction=instruction,
#         course_title=working_course_obj.title,
#         course_introduction=working_course_obj.introduction,
#     )
    
#     parameter_llm = llm.with_structured_output(ParamModel)
#     param_obj = parameter_llm.invoke(parameter_prompt)
    
#     # --- FINAL ASSEMBLY ---
    
#     plan_dict = {
#         "action": action_name,
#         "parameters": param_obj.model_dump()
#     }
    
#     print(f"Step 2 - Final Plan Generated: {plan_dict}")
    
#     return {"modification_plan": plan_dict}


# def execute_direct_modification_node(state: ModificationGraphState) -> ModificationGraphState:
#     """
#     Exécute toutes les modifications directes sur la structure du cours.
#     Ce nœud gère les mises à jour de titre/introduction et les suppressions 
#     de sections ou de sous-sections. Il ne nécessite pas de recherche externe.
#     """
#     print("--- NODE: Executing Direct Modification ---")
#     plan = state["modification_plan"]
#     action = plan.get("action")
#     params = plan.get("parameters", {})
    
#     # CHARGEMENT : On charge le dictionnaire de l'état dans un objet Pydantic
#     try:
#         working_course_obj = CompleteCourse(**state["working_course"])
#     except Exception as e:
#         report = f"FAILURE: Could not load the course structure from the current state. Error: {e}"
#         print(f"Operation Report: {report}")
#         # On ne peut rien faire si le cours ne peut être chargé, on retourne l'état actuel
#         return {"operation_report": report}

#     report = f"FAILURE: Unknown or unimplemented direct modification action '{action}'."

#     try:
#         # --- ACTION: Mettre à jour le titre du cours ---
#         if action == "UPDATE_COURSE_TITLE":
#             new_title = params["new_title"]
#             working_course_obj.title = new_title
#             report = f"SUCCESS: The course title has been updated to '{new_title}'."

#         # --- ACTION: Mettre à jour l'introduction du cours ---
#         elif action == "UPDATE_COURSE_INTRODUCTION":
#             new_introduction = params["new_introduction"]
#             working_course_obj.introduction = new_introduction
#             report = f"SUCCESS: The course introduction has been updated."

#         # --- ACTION: Supprimer une section entière ---
#         elif action == "REMOVE_SECTION":
#             title_to_remove = params["section_title"]
#             original_count = len(working_course_obj.sections)
#             working_course_obj.sections = [s for s in working_course_obj.sections if s.title != title_to_remove]
            
#             if len(working_course_obj.sections) < original_count:
#                 report = f"SUCCESS: The section titled '{title_to_remove}' was removed."
#             else:
#                 current_titles = [s.title for s in working_course_obj.sections]
#                 report = f"FAILURE: Could not find a section titled '{title_to_remove}'. Available sections are: {current_titles}."
        
#         # --- ACTION: Supprimer une sous-section (vidéo) ---
#         elif action == "REMOVE_SUBSECTION":
#             section_title = params["section_title"]
#             subsection_title = params["subsection_title"]
            
#             section_found = False
#             for section in working_course_obj.sections:
#                 if section.title == section_title:
#                     section_found = True
#                     original_subsection_count = len(section.subsections)
#                     # Filtre les sous-sections pour enlever celle qui est ciblée
#                     section.subsections = [ss for ss in section.subsections if ss.title != subsection_title]
                    
#                     if len(section.subsections) < original_subsection_count:
#                         report = f"SUCCESS: The video '{subsection_title}' was removed from the section '{section_title}'."
#                     else:
#                         current_sub_titles = [ss.title for ss in section.subsections]
#                         report = f"FAILURE: Could not find a video titled '{subsection_title}' in the section '{section_title}'. Available videos are: {current_sub_titles}."
#                     break # On arrête de chercher une fois la bonne section trouvée et modifiée
            
#             if not section_found:
#                 current_titles = [s.title for s in working_course_obj.sections]
#                 report = f"FAILURE: Could not find the target section '{section_title}'. Available sections are: {current_titles}."

#     except KeyError as e:
#         report = f"FAILURE: The action plan was missing a required parameter '{e}' for the action '{action}'."
    
#     print(f"Operation Report: {report}")
    
#     # SAUVEGARDE : On reconvertit l'objet Pydantic modifié en dictionnaire JSON-compatible
#     return {
#         "working_course": working_course_obj.model_dump(mode='json'),
#         "operation_report": report
#     }

# async def execute_search_node(state: ModificationGraphState) -> ModificationGraphState:
#     """
#     Exécute une recherche YouTube en utilisant le service avancé de filtrage par LLM.
#     C'est une fonction asynchrone car le service sous-jacent l'est.
#     """
#     print("--- NODE: Exécution de la recherche de ressources (avancée) ---")
#     plan = state["modification_plan"]
#     query = plan["parameters"].get("youtube_search_query")
    
#     if not query:
#         return {"message_to_user": "Invalid plan. The search query is missing."}
    
#     try:
#         # On a besoin du contexte du cours original
#         original_course_obj = CompleteCourse(**state["original_course"])
#     except Exception as e:
#         print(f"--- ERROR: Could not load original_course from state: {e} ---")
#         # On retourne une liste vide si le contexte ne peut être chargé
#         return {"newly_found_resources": []}

#     print(f"Recherche YouTube avec la requête : '{query}'")
    
#     # Récupère la demande initiale de l'utilisateur pour donner du contexte au filtre LLM
#     user_context = original_course_obj.introduction # ou un autre champ pertinent

#     # Appel CORRECT à votre service
#     found_resources = await search_and_filter_youtube_playlists(
#         queries=[query], 
#         user_input=user_context
#     )
    
#     if not found_resources:
#         print("--- Aucune ressource trouvée après le filtrage. ---")
#         json_serializable_resources = []
#     else:
#         # On utilise une boucle pour convertir chaque objet en dict JSON-compatible
#         json_serializable_resources = [
#             playlist.model_dump(mode='json') for playlist in found_resources
#         ]
    
#     return {"newly_found_resources": json_serializable_resources}


# def route_after_planning(state: ModificationGraphState) -> str:
#     """
#     Lit le plan d'action granulaire et route vers le bon type d'exécution.
#     """
#     plan = state.get("modification_plan")
#     if not plan:
#         return END

#     action = plan.get("action")
#     print(f"Routing Granular Action: {action}")

#     # Actions qui modifient la structure (supprimer, mettre à jour)
#     if action in ["UPDATE_COURSE_TITLE", "UPDATE_COURSE_INTRODUCTION", "REMOVE_SECTION", "REMOVE_SUBSECTION"]:
#         return "execute_direct_modification" # Un seul nœud pour les modifications directes

#     # Actions qui nécessitent une recherche de contenu externe
#     elif action in ["ADD_SECTION", "ADD_SUBSECTION", "REPLACE_SUBSECTION"]:
#         return "execute_search" # Le flux de recherche reste le même

#     # Actions de service
#     elif action == "CLARIFY":
#         return "execute_clarify"
#     elif action == "FINALIZE":
#         return "execute_finalize"
#     else:
#         return END

# def apply_add_replace_node(state: ModificationGraphState) -> ModificationGraphState:
#     """
#     Applique les résultats d'une recherche pour les actions ADD et REPLACE
#     au niveau de la section ou de la sous-section.
#     """
#     print("--- NODE: Applying Add/Replace from Search ---")
#     plan = state["modification_plan"]
#     action = plan["action"]
#     params = plan["parameters"]
#     new_resources_dicts = state.get("newly_found_resources")
    
#     working_course_obj = CompleteCourse(**state["working_course"])
#     report = f"FAILURE: Unknown add/replace action '{action}'."

#     # 1. CHARGEMENT du cours
#     working_course_obj = CompleteCourse(**state["working_course"])

#     if not new_resources_dicts:
#         report = f"FAILURE: The search for '{params.get('youtube_search_query')}' did not return any usable video playlists."
#         return { "working_course": working_course_obj.model_dump(mode='json'), "operation_report": report }

#     chosen_playlist_obj = AnalyzedPlaylist(**new_resources_dicts[0])

#     print("--- Résumé des descriptions par le LLM ---")
    
#     # 1. Résumer la description de la section principale (la playlist)
#     summarized_section_description = ""
#     if chosen_playlist_obj.playlist_description:
#         try:
#             prompt = SUMMARIZER_PROMPT.format(text_to_summarize=chosen_playlist_obj.playlist_description)
#             response = llm.invoke(prompt)
#             summarized_section_description = response.content
#         except Exception as e:
#             print(f"WARNING: Could not summarize section description, using truncated version. Error: {e}")
#             summarized_section_description = (chosen_playlist_obj.playlist_description[:250] + '...') if len(chosen_playlist_obj.playlist_description) > 250 else chosen_playlist_obj.playlist_description

#     # 2. Créer les sous-sections avec des descriptions potentiellement résumées
#     summarized_subsections = []
#     for video in chosen_playlist_obj.videos:
#         video_desc = video.description or "" # Assure que ce n'est pas None
        
#         if len(video_desc) > 250:
#             final_desc = video_desc[:250].rsplit(' ', 1)[0] + '...' # Coupe au dernier mot complet
#         else:
#             final_desc = video_desc

#         summarized_subsections.append(
#             Subsection(
#                 title=video.title,
#                 description=final_desc,
#                 video_url=str(video.video_url),
#                 channel_title=video.channel_title,
#                 thumbnail_url=str(video.thumbnail_url) if video.thumbnail_url else None
#             )
#         )

#     try:
#         if action == "ADD_SECTION":
#             new_section = Section(title=params["topic_to_add"], description=summarized_section_description, subsections=summarized_subsections)
#             working_course_obj.sections.append(new_section)
#             report = f"SUCCESS: Section '{new_section.title}' was added."

#         elif action in ["ADD_SUBSECTION", "REPLACE_SUBSECTION"]:
#             # Pour ces actions, on ne prend que la PREMIÈRE vidéo de la playlist trouvée
#             if not summarized_subsections:
#                  raise ValueError("Search returned a playlist with no videos.")
            
#             new_subsection = summarized_subsections[0]
            
#             target_section_title = params["section_title"] if action == "ADD_SUBSECTION" else params["section_to_replace"]
            
#             section_found = False
#             for section in working_course_obj.sections:
#                 if section.title == target_section_title:
#                     section_found = True
#                     if action == "ADD_SUBSECTION":
#                         section.subsections.append(new_subsection)
#                         report = f"SUCCESS: Subsection '{new_subsection.title}' was added to section '{target_section_title}'."
                    
#                     elif action == "REPLACE_SUBSECTION":
#                         target_sub_title = params["subsection_title"]
#                         sub_index = -1
#                         for i, sub in enumerate(section.subsections):
#                             if sub.title == target_sub_title:
#                                 sub_index = i
#                                 break
#                         if sub_index != -1:
#                             section.subsections[sub_index] = new_subsection
#                             report = f"SUCCESS: Subsection '{target_sub_title}' was replaced with '{new_subsection.title}' in section '{target_section_title}'."
#                         else:
#                             report = f"FAILURE: Target subsection '{target_sub_title}' not found in section '{target_section_title}'."
#                     break
#             if not section_found:
#                 report = f"FAILURE: Target section '{target_section_title}' not found."

#     except (KeyError, ValueError) as e:
#         report = f"FAILURE: Missing data or parameter for action '{action}': {e}"

#     print(f"Operation Report: {report}")
#     return {
#         "working_course": working_course_obj.model_dump(mode='json'),
#         "operation_report": report,
#         "newly_found_resources": None
#     }



# def execute_clarify_node(state: ModificationGraphState) -> ModificationGraphState:
#     """Prépare le message pour demander une clarification à l'utilisateur."""
#     print("--- NODE: Demande de clarification ---")
#     plan = state["modification_plan"]
#     question = plan["parameters"].get("question_to_user", "Can you provide more details?")

    
#     # Le graphe va s'interrompre après ce nœud
#     return {
#         "message_to_user": question,
#         "working_course": state.get("working_course")
#     }


# def execute_finalize_node(state: ModificationGraphState) -> ModificationGraphState:
#     """Finalise la session de modification."""
#     print("--- NODE: Finalisation de la session ---")
#     plan = state["modification_plan"]
#     message = plan["parameters"].get("final_message", "here is the final course !")
    
#     return {
#         "message_to_user": message, 
#         "is_finalized": True,
#         "working_course": state.get("working_course")
#     }

# def generate_user_message_node(state: ModificationGraphState) -> ModificationGraphState:
#     """
#     Invoque le LLM pour générer un message naturel pour l'utilisateur
#     en se basant sur le rapport d'opération.
#     """
#     print("--- NODE: Génération du message pour l'utilisateur ---")
#     report = state.get("operation_report")
    
#     working_course_dict = state.get("working_course")

#     if not report:
#         # Sécurité : si aucun rapport n'est disponible
#         return {"message_to_user": "An unexpected error occurred. What would you like to do?"}

#     prompt = MESSAGE_GENERATOR_PROMPT.format(operation_report=report)
    
#     # Appel LLM standard
#     response = llm.invoke(prompt)
#     message = response.content
    
#     print(f"Message généré : {message}")
    
#     # Nettoie le rapport après l'avoir utilisé
#     return {
#         "message_to_user": message, 
#         "operation_report": None,
#         "working_course": working_course_dict
#     }

# def build_modification_graph():
#     """
#     Construit et compile le graphe LangGraph pour la modification de cours.
#     """
#     workflow = StateGraph(ModificationGraphState)

#     # 1. Ajout de TOUS les nœuds, y compris le nouveau
#     workflow.add_node("plan_modification", plan_modification_node, retry=resilient_retry_policy)
#     workflow.add_node("execute_direct_modification", execute_direct_modification_node, retry=resilient_retry_policy)
#     workflow.add_node("execute_search", execute_search_node, retry=resilient_retry_policy)
#     workflow.add_node("apply_add_replace", apply_add_replace_node, retry=resilient_retry_policy) # NOUVEAU
#     workflow.add_node("execute_clarify", execute_clarify_node, retry=resilient_retry_policy)
#     workflow.add_node("execute_finalize", execute_finalize_node, retry=resilient_retry_policy)
#     workflow.add_node("generate_user_message", generate_user_message_node, retry=resilient_retry_policy)
    
#     workflow.set_entry_point("plan_modification")

#     # 2. Routage conditionnel (inchangé)
#     workflow.add_conditional_edges(
#         "plan_modification",
#         route_after_planning,
#         {
#             "execute_direct_modification": "execute_direct_modification",
#             "execute_search": "execute_search",
#             "execute_clarify": "execute_clarify",
#             "execute_finalize": "execute_finalize",
#             "end": END
#         }
#     )

#     workflow.add_edge("execute_direct_modification", "generate_user_message")

#     # NOUVELLE arête : après la recherche, on applique les modifications
#     workflow.add_edge("execute_search", "apply_add_replace")
    
#     workflow.add_edge("apply_add_replace", "generate_user_message")
#     workflow.add_edge("generate_user_message", END)

#     workflow.add_edge("execute_clarify", END)
#     workflow.add_edge("execute_finalize", END)
    
#     # 4. Compilation (inchangée)
#     graph = workflow.compile(checkpointer=checkpointer)
#     return graph