from src.cleeroute.langGraph.learners_api.quiz.models import UserProfile, ResponseStyle
from psycopg.connection_async import AsyncConnection
from src.cleeroute.db.app_db import get_app_db_connection
from fastapi import Depends

# 1. Mapping SOTA des styles vers des instructions LLM
STYLE_INSTRUCTIONS = {
    ResponseStyle.CASUAL: "Adopt a casual, friendly tone. Use conversational language, contractions, and occasional emojis if appropriate. Treat the user like a peer.",
    ResponseStyle.FORMAL: "Maintain a professional, academic, and objective tone. Avoid slang, contractions, or emojis. Focus on precision and clarity.",
    ResponseStyle.CONCISE: "Be extremely brief and direct. Avoid fluff, polite filler, or long introductions. Get straight to the answer. Use bullet points where possible.",
    ResponseStyle.HUMOROUS: "Be witty and incorporate light humor or tech jokes where appropriate to keep the learning engaging. Don't be afraid to be a bit playful.",
    ResponseStyle.EMPATHIC: "Be highly supportive, encouraging, and patient. Validate the user's struggles. Use phrases like 'It's normal to find this hard' or 'You're doing great'.",
    ResponseStyle.SIMPLIFIED: "Explain concepts as if the user is a beginner. Use analogies, simple vocabulary, and step-by-step scaffolding. Break down complex terms.",
    ResponseStyle.CUSTOM: "Do not give the answer directly. Instead, ask guiding questions to help the user derive the answer themselves. Act as a coach, not an encyclopedia."
}


async def get_user_profile(user_id: str, db: AsyncConnection = Depends(get_app_db_connection)) -> UserProfile:
    """
    Récupère les infos de personnalisation depuis la BDD métier.
    Gère la conversion des types PostgreSQL vers Pydantic.
    """
    try:
        # Note: Assurez-vous que les noms de colonnes ici correspondent exactement à votre table
        cursor = await db.execute(
            """
            SELECT preferred_language, professional_status, industries, motivation, ai_response_type 
            FROM profiles
            WHERE id = %s
            """, 
            (user_id,)
        )
        row = await cursor.fetchone()
        
        if row:
            # 1. Extraction sécurisée (Tuple vs Dict selon la config du driver)
            if isinstance(row, tuple):
                lang = row[0]
                prof = row[1]
                raw_industry = row[2] 
                motiv = row[3]
                raw_style = row[4]
            else:
                lang = row['preferred_language']
                prof = row['professional_status']
                raw_industry = row['industries']
                motiv = row['motivation']
                raw_style = row['ai_response_type']

            # 2. CORRECTION INDUSTRY (List -> String)
            # Si c'est une liste, on joint les éléments par des virgules
            if isinstance(raw_industry, list):
                # On filtre les éléments vides et on joint
                industry_str = ", ".join([str(i) for i in raw_industry if i])
                if not industry_str: 
                    industry_str = "General"
            else:
                industry_str = str(raw_industry) if raw_industry else "General"

            # 3. CORRECTION RESPONSE STYLE (String DB -> Enum Pydantic)
            # On crée un mapping pour relier la valeur DB ('casual') à l'Enum ('Casual/Informal')
            # On nettoie la clé (lowercase, strip) pour être robuste
            style_key = str(raw_style).lower().strip() if raw_style else "casual"
            
            # Mapping manuel pour garantir la correspondance
            style_map = {
                "casual": ResponseStyle.CASUAL,
                "formal": ResponseStyle.FORMAL,
                "concise": ResponseStyle.CONCISE,
                "humorous": ResponseStyle.HUMOROUS,
                "empathic": ResponseStyle.EMPATHIC,
                "simplified": ResponseStyle.SIMPLIFIED,
                "custom": ResponseStyle.CUSTOM,
                "casual": ResponseStyle.CASUAL,
                "simplified": ResponseStyle.SIMPLIFIED
            }
            
            # On récupère le bon Enum, ou CASUAL par défaut si inconnu
            final_style = style_map.get(style_key, ResponseStyle.CASUAL)

            return UserProfile(
                user_id=user_id,
                language=lang or "English",
                profession=prof or "Learner",
                industry=industry_str,
                motivation=motiv or "Learning",
                response_style=final_style 
            )
        else:
            # Profil introuvable
            return UserProfile(user_id=user_id)
            
    except Exception as e:
        print(f"Error fetching user profile: {e}")
        # En cas d'erreur, on retourne un profil par défaut pour ne pas bloquer l'app
        return UserProfile(user_id=user_id)


def build_personalization_block(profile: UserProfile) -> str:
    """
    Construit le bloc de texte à injecter dans le System Prompt.
    """
    style_instruction = STYLE_INSTRUCTIONS.get(profile.response_style, STYLE_INSTRUCTIONS[ResponseStyle.CASUAL])
    
    return f"""
    **PERSONALIZATION SETTINGS (CRITICAL):**
    1. **Language:** {profile.language} (Output MUST be in this language).
    2. **Learner Profile:** The user is a {profile.profession} in the {profile.industries} industries.
       - *Instruction:* Whenever possible, use analogies or examples relevant to {profile.industries}.
    3. **Motivation:** Their goal is "{profile.motivation}". 
       - *Instruction:* Relate concepts back to this goal to keep them motivated.
    4. **Tone & Style:** {style_instruction}
    """