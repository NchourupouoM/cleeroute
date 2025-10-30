from .prompt import *
from langchain_google_genai import ChatGoogleGenerativeAI
from .model import ModificationGraphState, RemoveParams, AddParams, ReplaceParams, ClarifyParams, FinalizeParams, ActionClassifier
from langgraph.graph import StateGraph, END
from src.cleeroute.langGraph.learners_api.course_gen.models import Section, Subsection,CompleteCourse,AnalyzedPlaylist
from src.cleeroute.langGraph.learners_api.course_gen.services import search_and_filter_youtube_playlists
from src.cleeroute.db.checkpointer import get_checkpointer
from typing import Union
import json
import copy
import os
from dotenv import load_dotenv
load_dotenv()

# Initialisez votre LLM (à placer en haut du fichier)
llm = ChatGoogleGenerativeAI(model=os.getenv("MODEL_2"), google_api_key=os.getenv("GEMINI_API_KEY"))
checkpointer = get_checkpointer()

def plan_modification_node(state: ModificationGraphState) -> ModificationGraphState:
    """
    Analyzes the user's request in a robust, two-step process.
    Step 1: Classifies the user's intent.
    Step 2: Generates the specific parameters for that intent.
    """
    print("--- NODE: Planning modification (2-Step, Clean Implementation) ---")

    try:
        working_course_obj = CompleteCourse(**state["working_course"])
    except Exception as e:
        # Sécurité : si la conversion échoue, on gère l'erreur proprement.
        print(f"--- ERREUR : Impossible de charger working_course depuis l'état : {e} ---")
        # On force une clarification pour éviter un crash.
        plan_dict = {
            "action": "CLARIFY",
            "parameters": {"question_to_user": "Je rencontre une difficulté technique avec la structure du cours. Pouvez-vous recommencer le processus de modification ?"}
        }
        return {"modification_plan": plan_dict}
    
    user_request = state["user_request"]
    section_titles = [sec.title for sec in working_course_obj.sections]
    
    # --- STEP 1: CLASSIFY THE ACTION ---
    
    classifier_prompt = ACTION_CLASSIFIER_PROMPT.format(
        user_request=user_request,
    )
    
    classifier_llm = llm.with_structured_output(ActionClassifier)
    action_result = classifier_llm.invoke(classifier_prompt)
    action_name = action_result.action
    
    print(f"Step 1 - Classified Action: {action_name}")

    # --- STEP 2: GENERATE PARAMETERS FOR THE ACTION ---
    
    param_model_map = {
        "REMOVE": (RemoveParams, "Generate parameters to remove a section. Identify the exact section title to be removed."),
        "ADD": (AddParams, "Generate parameters to add a new section. Identify the topic to add and create a YouTube search query."),
        "REPLACE": (ReplaceParams, "Generate parameters to replace a section. Identify the section to replace, the new topic, and a search query."),
        "CLARIFY": (ClarifyParams, "Generate a question to ask the user for clarification."),
        "FINALIZE": (FinalizeParams, "Generate a final confirmation message for the user.")
    }
    
    ParamModel, instruction = param_model_map[action_name]
    
    parameter_prompt = PARAMETER_GENERATOR_PROMPT.format(
        user_request=user_request, 
        section_titles=json.dumps(section_titles), 
        action_name=action_name,
        instruction=instruction,
        course_title=working_course_obj.title,
        course_introduction=working_course_obj.introduction,
    )
    
    parameter_llm = llm.with_structured_output(ParamModel)
    param_obj = parameter_llm.invoke(parameter_prompt)
    
    # --- FINAL ASSEMBLY ---
    
    plan_dict = {
        "action": action_name,
        "parameters": param_obj.model_dump()
    }
    
    print(f"Step 2 - Final Plan Generated: {plan_dict}")
    
    return {"modification_plan": plan_dict}


def execute_remove_node(state: ModificationGraphState) -> ModificationGraphState:
    """
    Exécute l'action REMOVE en utilisant une discipline de sérialisation stricte.
    """
    print("--- NODE: Exécution de la suppression (Final) ---")
    plan = state["modification_plan"]
    section_to_remove = plan["parameters"].get("section_title")
    
    if not section_to_remove:
        return {"operation_report": "FAILURE: The action plan was invalid. Missing 'section_title'."}

    # 1. CHARGEMENT : Convertit le dict de l'état en objet Pydantic
    working_course_obj = CompleteCourse(**state["working_course"])
    
    original_count = len(working_course_obj.sections)
    
    # 2. TRAVAIL : Modifie l'objet Pydantic
    working_course_obj.sections = [sec for sec in working_course_obj.sections if sec.title != section_to_remove]
    
    if len(working_course_obj.sections) < original_count:
        report = f"SUCCESS: The section titled '{section_to_remove}' was successfully removed."
    else:
        current_titles = [s.title for s in working_course_obj.sections]
        report = f"FAILURE: A section titled '{section_to_remove}' could not be found. Current sections are: {current_titles}"
    
    print(f"Rapport d'opération : {report}")
    
    # 3. SAUVEGARDE : Reconvertit l'objet modifié en dict JSON-compatible
    return {
        "working_course": working_course_obj.model_dump(mode='json'),
        "operation_report": report
    }


async def execute_search_node(state: ModificationGraphState) -> ModificationGraphState:
    """
    Exécute une recherche YouTube en utilisant le service avancé de filtrage par LLM.
    C'est une fonction asynchrone car le service sous-jacent l'est.
    """
    print("--- NODE: Exécution de la recherche de ressources (avancée) ---")
    plan = state["modification_plan"]
    query = plan["parameters"].get("youtube_search_query")
    
    if not query:
        return {"message_to_user": "Plan invalide. La requête de recherche est manquante."}
    
    try:
        # On a besoin du contexte du cours original
        original_course_obj = CompleteCourse(**state["original_course"])
    except Exception as e:
        print(f"--- ERROR: Could not load original_course from state: {e} ---")
        # On retourne une liste vide si le contexte ne peut être chargé
        return {"newly_found_resources": []}

    print(f"Recherche YouTube avec la requête : '{query}'")
    
    # Récupère la demande initiale de l'utilisateur pour donner du contexte au filtre LLM
    user_context = original_course_obj.introduction # ou un autre champ pertinent

    # Appel CORRECT à votre service
    found_resources = await search_and_filter_youtube_playlists(
        queries=[query], 
        user_input=user_context
    )
    
    if not found_resources:
        print("--- Aucune ressource trouvée après le filtrage. ---")
        json_serializable_resources = []
    else:
        # On utilise une boucle pour convertir chaque objet en dict JSON-compatible
        json_serializable_resources = [
            playlist.model_dump(mode='json') for playlist in found_resources
        ]
    
    return {"newly_found_resources": json_serializable_resources}


def route_after_planning(state: ModificationGraphState) -> str:
    """
    Lit le 'modification_plan' et décide quel nœud exécuter ensuite.
    """
    plan = state.get("modification_plan")
    if not plan:
        return END # Sécurité en cas de plan manquant

    action = plan.get("action")
    print(f"Routage de l'action : {action}")

    if action == "REMOVE":
        return "execute_remove"
    elif action == "ADD" or action == "REPLACE":
        # Pour ADD et REPLACE, on doit d'abord chercher des ressources
        return "execute_search"
    elif action == "CLARIFY":
        return "execute_clarify"
    elif action == "FINALIZE":
        return "execute_finalize"
    else:
        # Si l'action est inconnue, on termine pour éviter une boucle infinie
        return END

def apply_add_replace_node(state: ModificationGraphState) -> ModificationGraphState:
    """
    Applique ADD/REPLACE en utilisant une discipline de sérialisation stricte.
    """
    print("--- NODE: Application de l'ajout/remplacement (Final) ---")
    plan = state["modification_plan"]
    new_resources_dicts = state.get("newly_found_resources")

    # 1. CHARGEMENT du cours
    working_course_obj = CompleteCourse(**state["working_course"])

    if not new_resources_dicts:
        report = f"FAILURE: The search for '{plan['parameters'].get('youtube_search_query')}' did not return any usable video playlists."
        return {
            "working_course": working_course_obj.model_dump(mode='json'),
            "operation_report": report
        }

    chosen_playlist_dict = new_resources_dicts[0]
    # CHARGEMENT de la playlist
    chosen_playlist_obj = AnalyzedPlaylist(**chosen_playlist_dict)

    print("--- Résumé des descriptions par le LLM ---")
    
    # 1. Résumer la description de la section principale (la playlist)
    summarized_section_description = ""
    if chosen_playlist_obj.playlist_description:
        try:
            prompt = SUMMARIZER_PROMPT.format(text_to_summarize=chosen_playlist_obj.playlist_description)
            response = llm.invoke(prompt)
            summarized_section_description = response.content
        except Exception as e:
            print(f"WARNING: Could not summarize section description, using truncated version. Error: {e}")
            summarized_section_description = (chosen_playlist_obj.playlist_description[:250] + '...') if len(chosen_playlist_obj.playlist_description) > 250 else chosen_playlist_obj.playlist_description

    # 2. Créer les sous-sections avec des descriptions potentiellement résumées
    summarized_subsections = []
    for video in chosen_playlist_obj.videos:
        video_desc = video.description or "" # Assure que ce n'est pas None
        
        if len(video_desc) > 250:
            final_desc = video_desc[:250].rsplit(' ', 1)[0] + '...' # Coupe au dernier mot complet
        else:
            final_desc = video_desc

        summarized_subsections.append(
            Subsection(
                title=video.title,
                description=final_desc,
                video_url=str(video.video_url),
                channel_title=video.channel_title,
                thumbnail_url=str(video.thumbnail_url) if video.thumbnail_url else None
            )
        )
    
    # 2. TRAVAIL
    new_section = Section(
        title=plan["parameters"].get("topic_to_add") or plan["parameters"].get("new_topic", chosen_playlist_obj.playlist_title),
        description=summarized_section_description,
        subsections=summarized_subsections
    )

    if plan["action"] == "ADD":
        working_course_obj.sections.append(new_section)
    elif plan["action"] == "REPLACE":
        section_to_replace = plan["parameters"].get("section_to_replace")
        index_to_replace = -1
        for i, sec in enumerate(working_course_obj.sections):
            if sec.title == section_to_replace:
                index_to_replace = i
                break
        if index_to_replace != -1:
            working_course_obj.sections[index_to_replace] = new_section
        else:
            working_course_obj.sections.append(new_section)

    report = f"SUCCESS: The action '{plan['action']}' was completed for the topic '{new_section.title}'."
    
    # 3. SAUVEGARDE
    return {
        "working_course": working_course_obj.model_dump(mode='json'),
        "operation_report": report,
        "newly_found_resources": None
    }


def execute_clarify_node(state: ModificationGraphState) -> ModificationGraphState:
    """Prépare le message pour demander une clarification à l'utilisateur."""
    print("--- NODE: Demande de clarification ---")
    plan = state["modification_plan"]
    question = plan["parameters"].get("question_to_user", "Can you provide more details?")

    
    # Le graphe va s'interrompre après ce nœud
    return {
        "message_to_user": question,
        "working_course": state.get("working_course")
    }


def execute_finalize_node(state: ModificationGraphState) -> ModificationGraphState:
    """Finalise la session de modification."""
    print("--- NODE: Finalisation de la session ---")
    plan = state["modification_plan"]
    message = plan["parameters"].get("final_message", "Voici votre cours finalisé !")
    
    return {
        "message_to_user": message, 
        "is_finalized": True,
        "working_course": state.get("working_course")
    }

def generate_user_message_node(state: ModificationGraphState) -> ModificationGraphState:
    """
    Invoque le LLM pour générer un message naturel pour l'utilisateur
    en se basant sur le rapport d'opération.
    """
    print("--- NODE: Génération du message pour l'utilisateur ---")
    report = state.get("operation_report")
    
    working_course_dict = state.get("working_course")

    if not report:
        # Sécurité : si aucun rapport n'est disponible
        return {"message_to_user": "An unexpected error occurred. What would you like to do?"}

    prompt = MESSAGE_GENERATOR_PROMPT.format(operation_report=report)
    
    # Appel LLM standard
    response = llm.invoke(prompt)
    message = response.content
    
    print(f"Message généré : {message}")
    
    # Nettoie le rapport après l'avoir utilisé
    return {
        "message_to_user": message, 
        "operation_report": None,
        "working_course": working_course_dict
    }

def build_modification_graph():
    """
    Construit et compile le graphe LangGraph pour la modification de cours.
    """
    workflow = StateGraph(ModificationGraphState)

    # 1. Ajout de TOUS les nœuds, y compris le nouveau
    workflow.add_node("plan_modification", plan_modification_node)
    workflow.add_node("execute_remove", execute_remove_node)
    workflow.add_node("execute_search", execute_search_node)
    workflow.add_node("apply_add_replace", apply_add_replace_node) # NOUVEAU
    workflow.add_node("execute_clarify", execute_clarify_node)
    workflow.add_node("execute_finalize", execute_finalize_node)
    workflow.add_node("generate_user_message", generate_user_message_node)
    
    workflow.set_entry_point("plan_modification")

    # 2. Routage conditionnel (inchangé)
    workflow.add_conditional_edges(
        "plan_modification",
        route_after_planning,
        {
            "execute_remove": "execute_remove",
            "execute_search": "execute_search",
            "execute_clarify": "execute_clarify",
            "execute_finalize": "execute_finalize",
            "end": END
        }
    )

    workflow.add_edge("execute_remove", "generate_user_message")
    workflow.add_edge("apply_add_replace", "generate_user_message")
    workflow.add_edge("generate_user_message", END)

    workflow.add_edge("execute_clarify", END)
    workflow.add_edge("execute_finalize", END)
    
    # NOUVELLE arête : après la recherche, on applique les modifications
    workflow.add_edge("execute_search", "apply_add_replace")

    # 4. Compilation (inchangée)
    graph = workflow.compile(checkpointer=checkpointer)
    return graph