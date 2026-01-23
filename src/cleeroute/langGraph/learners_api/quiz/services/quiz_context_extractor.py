from psycopg.connection_async import AsyncConnection
from src.cleeroute.langGraph.learners_api.chats.course_context_for_global_chat import fetch_course_hierarchy

async def build_quiz_context_from_db(
    db: AsyncConnection, 
    scope: str, 
    course_id: str, 
    section_id: str = None, 
    subsection_id: str = None
) -> str:
    """
    Construit le contexte pour le Quiz selon la stratégie 'Global Summary + Local Deep Dive'.
    
    1. Structure du cours (Titres).
    2. Résumés de TOUTES les vidéos du cours (Contexte Global).
    3. Transcript INTÉGRAL de la vidéo courante (si applicable).
    """
    context_text = ""

    try:
        # --- 1. STRUCTURE & INTRO (Métadonnées) ---
        course_obj = await fetch_course_hierarchy(db, course_id)
        context_text += f"=== COURSE OVERVIEW ===\nTitle: {course_obj.title}\nIntroduction: {course_obj.introduction}\n"

        # --- 2. CONTEXTE GLOBAL (Résumés de TOUTES les vidéos) ---
        # Peu importe le scope, on veut que l'IA connaisse tout le programme.
        # On joint pour récupérer les résumés liés à ce cours.
        cursor = await db.execute(
            """
            SELECT sec.title AS section_title, sub.title AS video_title, ts.summary_text
            FROM transcript_summaries ts
            JOIN subsection sub ON ts.subsection_id = sub.id
            JOIN section sec ON sub.section_id = sec.id
            WHERE sec.course_id = %s
            ORDER BY sec.position, sub.position
            """,
            (course_id,)
        )
        all_summaries = await cursor.fetchall()
        
        if all_summaries:
            context_text += "\n=== GLOBAL VIDEO SUMMARIES (All Modules) ===\n"
            current_sec = ""
            for row in all_summaries:
                # Gestion Tuple vs Dict
                if isinstance(row, tuple):
                    sec_title, vid_title, summary = row
                else:
                    sec_title, vid_title, summary = row['section_title'], row['video_title'], row['summary_text']
                
                # Organisation visuelle par section
                if sec_title != current_sec:
                    context_text += f"\n-- MODULE: {sec_title} --\n"
                    current_sec = sec_title
                
                context_text += f"Video '{vid_title}': {summary}\n"
        else:
            context_text += "\n(No video summaries available yet. The course might be new.)\n"

        # --- 3. CONTEXTE LOCAL (Transcript COMPLET de la vidéo active) ---
        # Si l'utilisateur est sur une vidéo précise, on veut que le quiz soit très précis dessus.
        if subsection_id:
            # On récupère tous les chunks de texte de cette vidéo et on les recolle
            cursor = await db.execute(
                """
                SELECT content 
                FROM transcript_chunks 
                WHERE subsection_id = %s 
                ORDER BY chunk_index ASC
                """,
                (subsection_id,)
            )
            chunks = await cursor.fetchall()
            
            if chunks:
                full_transcript = " ".join([c[0] if isinstance(c, tuple) else c['content'] for c in chunks])
                
                # On ajoute ce gros bloc de texte avec une instruction de priorité
                context_text += f"\n\n=== 🎯 CURRENT VIDEO FULL TRANSCRIPT (High Priority) ===\n"
                context_text += f"Use the specific details below to generate precise questions for this video:\n\n"
                context_text += full_transcript
            else:
                # Fallback: Si pas de chunks, on vérifie si un résumé existe dans la liste globale (déjà ajouté plus haut)
                context_text += "\n(Full transcript not processed yet for this video. Using summary above.)\n"

        return context_text

    except Exception as e:
        print(f"Error building rich quiz context: {e}")
        # En cas d'erreur SQL, on renvoie au moins le titre pour ne pas crash
        return f"Course: {course_obj.title} (Detailed context unavailable due to error)"