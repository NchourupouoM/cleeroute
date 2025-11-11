# In state.py

from typing import List, TypedDict, Optional, Any,Annotated
from pydantic import BaseModel, TypeAdapter, ValidationError
import json
import operator

from .models import Course_meta_datas, AnalyzedPlaylist, SyllabusOptions

# Custom serializer for Pydantic models
class PydanticSerializer:
    """
        Handles serialization and deserialization for Pydantic models to/from JSON strings,
        ensuring compatibility with checkpointers that only store primitive types.
        This implementation is compatible with Pydantic V2.
    """
    @staticmethod
    def dumps(obj: Any) -> str:
        """Serializes a Pydantic model or a list of models to a JSON string."""
        if isinstance(obj, BaseModel):
            # .model_dump_json() is the correct method in V2
            return obj.model_dump_json()
        if isinstance(obj, list) and all(isinstance(item, BaseModel) for item in obj):
            # For lists, we dump each model to a dict, then dump the list to a JSON string
            return json.dumps([item.model_dump() for item in obj])
        return json.dumps(obj)

    @staticmethod
    def loads(s: str, model_type: Any) -> Any:
        """
        Deserializes a JSON string back into a Pydantic model or list of models.
        Will raise an exception if the string is not valid JSON or doesn't match the model.
        """
        # On enlève le try...except qui masquait les erreurs.
        # Si le parsing échoue, on VEUT que ça lève une exception pour pouvoir la déboguer.
        # Le seul cas où on ne veut pas d'erreur, c'est si 's' n'est pas du JSON du tout
        # (comme une simple question).
        if not s.strip().startswith(('{', '[')):
            return s # C'est une simple chaîne, pas du JSON.

        # Laisser Pydantic lever une ValidationError si le JSON est mal formé.
        adapter = TypeAdapter(model_type)
        return adapter.validate_json(s)

def _overwrite(left: Any, right: Any) -> Any:
    return right


# The State dictionary will only store serialized strings for Pydantic objects.
# We will deserialize them within the nodes when we need to use them.
class GraphState(TypedDict):
    # --- Inputs ---
    user_input_text: Annotated[str, _overwrite] # Stored as str
    user_input_links: Annotated[Optional[List[str]], _overwrite] # Stored as string
    metadata_str: Annotated[str, _overwrite] # Stored as str # Serialized Course_meta_datas

    # --- Conversation / HITL ---
    conversation_history: Annotated[List[tuple[str, str]], operator.add ] # List of (human_message, ai_message)
    current_question: Annotated[Optional[str], _overwrite]
    is_conversation_finished: Annotated[bool, _overwrite]

    # --- Data Collection ---
    search_queries: Annotated[List[str], _overwrite]
    user_playlist_str: Annotated[Optional[str], _overwrite]
    searched_playlists_str: Annotated[List[str], _overwrite]
    merged_resources_str: Annotated[List[str], _overwrite]

    syllabus_blueprint_str: Annotated[Optional[str], _overwrite]

    found_project_videos: Annotated[Optional[str], _overwrite]
    
    # --- Final Output ---
    final_syllabus_options_str: Annotated[Optional[str], _overwrite]

    blueprint_retries: int

    current_node: Optional[str]

