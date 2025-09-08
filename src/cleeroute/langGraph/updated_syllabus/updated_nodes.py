import os
from dotenv import load_dotenv
from typing import Optional, TypedDict, Union, Literal
from langchain_core.messages import HumanMessage, SystemMessage
from src.cleeroute.models import ( CompleteCourse, InstructionSet
)
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, ValidationError, Field
from src.cleeroute.langGraph.updated_syllabus.prompts import SPECIFIC_INSTRUCTIONS_PROMPT
from src.cleeroute.langGraph.updated_syllabus.utils import _apply_course_level_modification, _apply_intra_section_modification, _apply_project_modification, _apply_section_modification, _apply_subsection_modification, _find_closest_section

load_dotenv()

def generate_gemini_structured_output_response(
        prompt:str, output_schema: type[BaseModel],
        llm_instance: ChatGoogleGenerativeAI
    ) -> Union[BaseModel, dict]:
    """
    Génère une sortie structurée depuis un prompt en utilisant le LLM Gemini.
    """
    try:
        structured_llm = llm_instance.with_structured_output(output_schema)
        messages = [
            SystemMessage(content="You're an AI assistant that can generate a structured output based on a pydantic schema."),
            HumanMessage(content=prompt),
        ]
        response = structured_llm.invoke(messages)
        return response
    except Exception as e:
        # L'appel a échoué, nous construisons un InstructionSet d'erreur
        print(f"Erreur lors de l'appel de l'API gemini ou du parsing de la sortie. Prompt: {e}")
        
        # CORRECTION : Retourner un InstructionSet valide qui indique l'erreur
        return InstructionSet(
            instructions=[], # Pas d'instructions car il y a eu une erreur
            requires_human_intervention=True,
            error_message=f"Une erreur technique est survenue lors de l'analyse de votre requête: {e}. Veuillez reformuler ou contacter le support."
        )
    
# graph state langgraph 
class CourseState(TypedDict):
    """
    Représente l'état du graphe. Version SIMPLIFIÉE et CORRIGÉE.
    """
    course: CompleteCourse
    user_input: str
    
    # CLÉ UNIQUE pour les instructions. Fini l'ambiguïté.
    instructions_to_apply: Optional[InstructionSet] 
    
    requires_human_intervention: bool
    human_correction_input: Optional[str] # On garde pour le contexte
    error_message: Optional[str]
    current_run_id: Optional[str]
    response_message: Optional[str]

def call_gemini_for_parsing(
        state: CourseState,
        llm_instance = ChatGoogleGenerativeAI
    ) -> CourseState:
    """
    Appelle le LLM Gemini pour parser la requête de l'utilisateur en un InstructionSet.
    Cette fonction gère à la fois les succès et les échecs de l'appel API.
    """
    print("\n--- Nœud: call_gemini_for_parsing ---")
    user_input = state["user_input"]
    course_json = state["course"].model_dump_json(indent=2)

    prompt = f"""
        You are an AI assistant responsible for analyzing user requests to modify a course structure.
        Your goal is to convert their natural language request into a structured JSON object
        that adheres to the `InstructionSet` Pydantic schema, which contains a LIST of `ModificationInstruction`.

        Decompose the user's request into a sequence of simple, atomic steps. For example, a request to "add a new section with two subsections and a project" should be broken down into FOUR separate instructions in the list:
        1. An `add` instruction for the `section`.
        2. An `add` instruction for the first `section_subsection`.
        3. An `add` instruction for the second `section_subsection`.
        4. An `add` or `update` instruction for the `section_project`.

        If the request is ambiguous, set "requires_human_intervention": true and provide a clear "error_message".

        {SPECIFIC_INSTRUCTIONS_PROMPT}

        --- Course Context and User Request ---
        Course context:
        ```json
        {course_json}
        ```
        User request: "{user_input}"

        Please generate the structured JSON object adhering to the `InstructionSet` schema.
    """

    # Cette fonction retourne maintenant TOUJOURS un objet InstructionSet.
    instruction_set = generate_gemini_structured_output_response(prompt=prompt, output_schema=InstructionSet, llm_instance=llm_instance)

    # --- SIMPLIFICATION MAJEURE ---
    # Plus besoin de vérifier le type. On utilise directement l'objet.
    # C'est plus simple et corrige l'erreur `AttributeError`.

    print(f"Set d'instructions parsé: {instruction_set.model_dump_json(indent=2)}")
    
    return {
        "instructions_to_apply": instruction_set, 
        "requires_human_intervention": instruction_set.requires_human_intervention,
        "error_message": instruction_set.error_message,
    }
                   
def check_intervention_needed(state: CourseState) -> Literal["human_intervention", "apply_changes"]:
    """
    Conditional node to determine if a human intervention is needed.
    """
    print("\n--- Nœud: check_intervention_needed ---")
    if state["requires_human_intervention"]:
        print("Intervention humaine requise.")
        return "human_intervention"
    else:
        print("Aucune intervention humaine requise. Application des changements.")
        return "apply_changes"
    
def human_intervention_node(state: CourseState) -> CourseState:
    """
    Node where the graph waits for human intervention.
    """
    print("\n--- Nœud: human_intervention_node --- (POINT D'INTERRUPTION)")
    return {
        "response_message": state.get("error_message", "Clarification nécessaire. Veuillez fournir plus de détails pour continuer.")
    }


def apply_modification_to_course(state: CourseState) -> CourseState:
    """
    Version finale. Lit les instructions depuis la clé unique `instructions_to_apply`.
    """
    print("\n--- Nœud: apply_modification_to_course ---")
    
    # CORRECTION : On lit depuis la clé unique. Plus de `or`.
    instruction_set_to_apply = state.get("instructions_to_apply")

    if not instruction_set_to_apply or not isinstance(instruction_set_to_apply.instructions, list) or not instruction_set_to_apply.instructions:
        error_msg = "La liste d'instructions est vide ou invalide."
        print(f"ERREUR: {error_msg}")
        return {"course": state["course"], "requires_human_intervention": True, "error_message": error_msg, "response_message": error_msg}

    course_copy = state["course"].model_copy(deep=True)
    
    for i, instruction in enumerate(instruction_set_to_apply.instructions):
        try:
            target_type = instruction.target_type
            print(f"\n--- Dispatching de l'instruction {i+1}: {instruction.action.value} {target_type} ---")

            if target_type.startswith("course_"):
                _apply_course_level_modification(instruction, course_copy)
            elif target_type == "section":
                _apply_section_modification(instruction, course_copy)
            elif target_type in ["section_title", "section_description"]:
                _apply_intra_section_modification(instruction, course_copy)
            elif target_type in ["section_subsection", "subsection_title", "subsection_description"]:
                 _apply_subsection_modification(instruction, course_copy)
            elif target_type.startswith("project_") or target_type == "section_project":
                _apply_project_modification(instruction, course_copy)
            else:
                raise ValueError(f"Type de cible non reconnu : '{target_type}'")

        except (ValueError, ValidationError) as e:
            error_msg = f"Échec à l'étape {i+1} ({instruction.action.value} {instruction.target_type}): {e}. La modification a été annulée."
            print(f"ERREUR: {error_msg}")
            return { "course": state["course"], "requires_human_intervention": True, "error_message": error_msg, "response_message": error_msg }

    print("\nModification(s) appliquée(s) avec succès à la copie du cours.")
    return { "course": course_copy, "response_message": "Les modifications demandées ont été appliquées avec succès.", "requires_human_intervention": False, "error_message": None }


def reflect_and_summarize(state: CourseState, llm_instance: ChatGoogleGenerativeAI) -> CourseState:
    """
    Use gemini to generate a summary of the changes applied to the course.
    """
    print("\n--- Nœud: reflect_and_summarize ---")
    course_json = state["course"].model_dump_json(indent=2)
    original_user_input = state["user_input"]
    applied_instruction = state.get("human_corrected_instruction") or state.get("modification_instruction")
    applied_instruction_json = applied_instruction.model_dump_json(indent=2) if applied_instruction else "Not a specific information saved"
    previous_response = state.get("response_message", "Attempted modification.")

    prompt = f"""
        You are an AI assistant reflecting on a course modification task.
        The user's original request was: "{original_user_input}"
        The system attempted to apply the following structured instruction:
        ```json
        {applied_instruction_json}
        ```
        The previous action resulted in: "{previous_response}"
        Here is the NEW updated course structure:
        ```json
        {course_json}
        ```
        Please provide a concise and user-friendly summary of the changes that were made,
        or confirm the current state of the course, and mention that the operation is complete.
    """

    messages = [
        SystemMessage(content="You are an assistant that gives concise summaries."),
        HumanMessage(content=prompt)
    ]
    summary_response = llm_instance.invoke(messages)
    summary = summary_response.content if hasattr(summary_response, 'content') else str(summary_response)

    print(f"Résumé Gemini:\n{summary}")
    return {
        "response_message": summary,
        "requires_human_intervention": False
    }
