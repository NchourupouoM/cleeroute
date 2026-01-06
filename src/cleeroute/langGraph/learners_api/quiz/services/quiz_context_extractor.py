from psycopg.connection_async import AsyncConnection
from fastapi import HTTPException, Depends
from src.cleeroute.db.app_db import get_app_db_connection


async def build_quiz_context_from_db(
    scope: str, 
    course_id: str,
    db: AsyncConnection, 
    section_id: str = None, 
    subsection_id: str = None
) -> str:
    """
    Récupère le contenu textuel pertinent depuis la BDD pour générer le quiz.
    """
    context_text = ""

    try:
        # --- CAS 1 : SCOPE = SUBSECTION (ou VIDEO) ---
        # C'est le plus granulaire : on récupère le contenu précis de la sous-section.
        if scope in ["subsection", "video"]:
            if not subsection_id:
                raise ValueError("subsectionId is required for subsection/video scope")
            
            cursor = await db.execute(
                """
                SELECT title
                FROM subsection 
                WHERE id = %s
                """,
                (subsection_id,)
            )
            row = await cursor.fetchone()
            if not row:
                raise ValueError("Subsection not found")
            
            # Gestion tuple/dict selon le driver
            title = row[0] if isinstance(row, tuple) else row['title']
            # content = row[1] if isinstance(row, tuple) else row['content'] # Contenu (transcript de la video, résumé)
            # desc = row[2] if isinstance(row, tuple) else row['description']
            
            context_text = f"FOCUS TOPIC: {title}\n"
            # context_text += f"DETAILS:\n{content or desc or 'No detailed content available.'}"
            # context_text += f"DETAILS:\n{desc or 'No detailed content available.'}"

        # --- CAS 2 : SCOPE = SECTION ---
        # On récupère le titre/desc de la section + les résumés de toutes ses sous-sections.
        elif scope == "section":
            if not section_id:
                raise ValueError("sectionId is required for section scope")
            
            # 1. Info de la Section
            cursor = await db.execute(
                "SELECT title, description FROM section WHERE id = %s",
                (section_id,)
            )
            sec_row = await cursor.fetchone()
            if not sec_row: raise ValueError("Section not found")
            
            s_title = sec_row[0] if isinstance(sec_row, tuple) else sec_row['title']
            # s_desc = sec_row[1] if isinstance(sec_row, tuple) else sec_row['description']
            
            context_text += f"MODULE: {s_title}"
            
            # 2. Contenu des sous-sections
            cursor = await db.execute(
                "SELECT title FROM subsection WHERE section_id = %s ORDER BY position ASC",
                (section_id,)
            )
            rows = await cursor.fetchall()
            for row in rows:
                sub_title = row[0] if isinstance(row, tuple) else row['title']
                # sub_content = row[1] if isinstance(row, tuple) else row['content']
                # On limite la taille du contenu pour ne pas exploser le contexte si la section est longue
                # summary = (sub_content[:500] + "...") if sub_content and len(sub_content) > 500 else (sub_content or "")
                context_text += f"- {sub_title}\n"

        # --- CAS 3 : SCOPE = COURSE (Défaut) ---
        # On récupère l'intro du cours + la liste de toutes les sections et leurs descriptions.
        else: # scope == "course"
            cursor = await db.execute(
                "SELECT title, description FROM course WHERE id = %s",
                (course_id,)
            )
            course_row = await cursor.fetchone()
            if not course_row: raise ValueError("Course not found")
            
            c_title = course_row[0] if isinstance(course_row, tuple) else course_row['title']
            c_desc = course_row[1] if isinstance(course_row, tuple) else course_row['description']
            
            context_text += f"COURSE TITLE: {c_title}\nINTRODUCTION: {c_desc}\n\nCOURSE MODULES:\n"
            
            # 2. Liste des Sections
            cursor = await db.execute(
                "SELECT title FROM section WHERE course_id = %s ORDER BY position ASC",
                (course_id,)
            )
            rows = await cursor.fetchall()
            for row in rows:
                sec_title = row[0] if isinstance(row, tuple) else row['title']
                # sec_desc = row[1] if isinstance(row, tuple) else row['description']
                context_text += f"- Module: {sec_title}"

        if not context_text.strip():
            return "No content found for this context."
        
        # print(f"Built quiz context (scope={scope}): {context_text[:200]}...")
        print(f"Built quiz context (scope={scope}): {context_text}")
        return context_text

    except Exception as e:
        print(f"Error building quiz context: {e}")
        # En cas d'erreur DB, on renvoie une chaine vide pour ne pas faire planter l'API 
        return ""