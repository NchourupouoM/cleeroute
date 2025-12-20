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
    ResponseStyle.SOCRATIC: "Do not give the answer directly. Instead, ask guiding questions to help the user derive the answer themselves. Act as a coach, not an encyclopedia."
}


async def get_user_profile(user_id: str, db: AsyncConnection = Depends(get_app_db_connection)) -> UserProfile:
    """
    Récupère les infos de personnalisation depuis la BDD métier.
    (Adaptez la requête SQL selon votre schéma réel 'users').
    """
    try:
        # EXEMPLE DE REQUÊTE (A ADAPTER)
        # On suppose une table 'users' avec ces colonnes
        cursor = await db.execute(
            """
            SELECT language, professional_status, industry, motivation, response_style 
            FROM users 
            WHERE id = %s
            """, 
            (user_id,)
        )
        row = await cursor.fetchone()
        
        if row:
            # Gestion tuple/dict selon votre driver
            vals = row if isinstance(row, tuple) else (
                row['language'], row['professional_status'], row['industry'], 
                row['motivation'], row['response_style']
            )
            
            return UserProfile(
                user_id=user_id,
                language=vals[0] or "English",
                profession=vals[1] or "Learner",
                industry=vals[2] or "General",
                motivation=vals[3] or "Learning",
                response_style=vals[4] or ResponseStyle.CASUAL
            )
        else:
            # Fallback par défaut
            return UserProfile(user_id=user_id)
            
    except Exception as e:
        print(f"Error fetching user profile: {e}")
        return UserProfile(user_id=user_id)


def build_personalization_block(profile: UserProfile) -> str:
    """
    Construit le bloc de texte à injecter dans le System Prompt.
    """
    style_instruction = STYLE_INSTRUCTIONS.get(profile.response_style, STYLE_INSTRUCTIONS[ResponseStyle.CASUAL])
    
    return f"""
    **PERSONALIZATION SETTINGS (CRITICAL):**
    1. **Language:** {profile.language} (Output MUST be in this language).
    2. **Learner Profile:** The user is a {profile.profession} in the {profile.industry} industry. 
       - *Instruction:* Whenever possible, use analogies or examples relevant to {profile.industry}.
    3. **Motivation:** Their goal is "{profile.motivation}". 
       - *Instruction:* Relate concepts back to this goal to keep them motivated.
    4. **Tone & Style:** {style_instruction}
    """