import json
from typing import Optional, Tuple
# Importez vos modèles de cours complets (Project, Section, etc.)
from src.cleeroute.langGraph.learners_api.course_gen.models import CompleteCourse, Section, Subsection, Project

def extract_context_from_course(
    course: CompleteCourse, 
    scope: str, 
    section_idx: Optional[int] = None, 
    subsection_idx: Optional[int] = None,
    video_id: Optional[str] = None
) -> str:
    """Construit le contexte textuel (RAG) selon le scope défini."""
    context_text = ""

    # 1. SCOPE: VIDEO (Nouveau)
    if scope == "video":
        # Recherche de la vidéo dans tout le cours (approche naïve par parcours)
        found = False
        for s_idx, sec in enumerate(course.sections):
            for sub_idx, sub in enumerate(sec.subsections):
                # On suppose que video_url ou un ID correspond
                # Ici on compare l'URL ou on utilise les index si video_id n'est pas fourni
                if (video_id and sub.video_url == video_id) or (section_idx == s_idx and subsection_idx == sub_idx):
                    context_text += f"FOCUS VIDEO: {sub.title}\n"
                    context_text += f"Description/Transcript: {sub.description}\n"
                    context_text += f"URL: {sub.video_url}\n"
                    found = True
                    break
            if found: break
        if not found: context_text = "Specific video context not found."

    # 2. SCOPE: SUBSECTION
    elif scope == "subsection":
        if section_idx is not None and 0 <= section_idx < len(course.sections):
            section = course.sections[section_idx]
            if subsection_idx is not None and 0 <= subsection_idx < len(section.subsections):
                sub = section.subsections[subsection_idx]
                context_text += f"SECTION: {section.title}\n"
                context_text += f"SUBSECTION TOPIC: {sub.title}\n"
                context_text += f"CONTENT: {sub.description}\n"
                context_text += f"VIDEO LINK: {sub.video_url}\n"

    # 3. SCOPE: SECTION
    elif scope == "section":
        if section_idx is not None and 0 <= section_idx < len(course.sections):
            section = course.sections[section_idx]
            context_text += f"CURRENT SECTION: {section.title}\n"
            context_text += f"OVERVIEW: {section.description}\n"
            if section.project:
                context_text += f"PROJECT: {section.project.title}\n"
            for sub in section.subsections:
                context_text += f"- Topic: {sub.title} ({sub.description[:100]}...)\n"

    # 4. SCOPE: COURSE (Défaut)
    else:
        context_text += f"COURSE TITLE: {course.title}\n"
        context_text += f"INTRO: {course.introduction}\n"
        for i, sec in enumerate(course.sections):
            context_text += f"Module {i+1}: {sec.title}\n"

    return context_text

async def get_student_quiz_context(db, courseId: str) -> str:
    """Récupère les performances et questions des 3 derniers quiz."""
    try:
        cursor = await db.execute(
            """
            SELECT title, pass_percentage, summary_text, interaction_json
            FROM quiz_attempts
            WHERE course_id = %s AND status = 'completed'
            ORDER BY completed_at DESC LIMIT 3
            """,
            (courseId,)
        )
        records = await cursor.fetchall()
        
        if not records:
            return "No recent quiz activity."

        summary = "--- STUDENT QUIZ HISTORY ---\n"
        for rec in records:
            # Compatibilité Tuple/Dict
            if isinstance(rec, tuple):
                title, score, txt, history = rec[0], rec[1], rec[2], rec[3]
            else:
                title, score, txt, history = rec["title"], rec["pass_percentage"], rec["summary_text"], rec["interaction_json"]

            summary += f"\n- Quiz '{title}': Score {score}%. AI Feedback: {txt}\n"
            
            # Extraction des questions posées par l'élève dans le quiz
            questions = []
            if history:
                # Si c'est une string JSON, on parse
                if isinstance(history, str):
                    try: history_list = json.loads(history)
                    except: history_list = []
                else:
                    history_list = history # Déjà un dict/list via psycopg adapter
                
                if isinstance(history_list, list):
                    for msg in history_list:
                        # On cherche les questions explicites (pas les réponses QCM)
                        if msg.get('sender') == 'user' and "choose option" not in msg.get('content', ''):
                            questions.append(msg.get('content'))
            
            if questions:
                summary += "  Student asked during quiz: " + "; ".join(questions) + "\n"
        
        return summary
    except Exception as e:
        print(f"Ctx Error: {e}")
        return ""

async def fetch_course_hierarchy(db, course_id: str) -> CompleteCourse:
    """
    Reconstruit l'objet CompleteCourse à partir des tables relationnelles
    (course, section, subsection).
    """
    
    # 1. Récupérer les infos du COURS
    # Note: J'adapte les champs selon votre description (course_id, title, description)
    cursor = await db.execute(
        """
        SELECT title, description 
        FROM course 
        WHERE id = %s
        """,
        (course_id,)
    )
    course_row = await cursor.fetchone()
    
    if not course_row:
        raise ValueError(f"Course with id {course_id} not found")
        
    # Adaptation tuple vs dict selon votre config driver
    c_title = course_row[0] if isinstance(course_row, tuple) else course_row["title"]
    c_desc = course_row[1] if isinstance(course_row, tuple) else course_row["description"]

    # 2. Récupérer les SECTIONS
    cursor = await db.execute(
        """
        SELECT id, title, description 
        FROM section 
        WHERE course_id = %s 
        ORDER BY position ASC
        """,
        (course_id,)
    )
    section_rows = await cursor.fetchall()
    
    sections_list = []

    # 3. Pour chaque section, récupérer les SUBSECTIONS
    for s_row in section_rows:
        s_id = s_row[0] if isinstance(s_row, tuple) else s_row["id"]
        s_title = s_row[1] if isinstance(s_row, tuple) else s_row["title"]
        s_desc = s_row[2] if isinstance(s_row, tuple) else s_row["description"]
        
        # On suppose ici que la table subsection a une colonne 'section_id' 
        # ou qu'on peut filtrer par course_id et positionner correctement.
        # Si vous n'avez pas section_id, il faut revoir votre modélisation BDD.
        # Je suppose ici que 'section_id' existe.

        # description: a ajouter
        cursor = await db.execute(
            """
            SELECT title, content, content_type
            FROM subsection 
            WHERE section_id = %s 
            ORDER BY position ASC
            """,
            (s_id,)
        )
        sub_rows = await cursor.fetchall()
        
        subsections_list = []
        for sub in sub_rows:
            if isinstance(sub, tuple):
                sub_title, sub_content, sub_type = sub
            else:
                sub_title = sub["title"]
                # sub_desc = sub["description"]
                sub_content = sub["content"]
                sub_type = sub["content_type"]

            # Mapping vers le modèle Pydantic Subsection
            # On utilise 'content' comme video_url si c'est une vidéo, ou description
            final_video_url = "http://placeholder.url" # Valeur par défaut valide
            
            if sub_type == 'video' and sub_content:
                # Si c'est une liste (ex: ['https://...']), on prend le premier élément
                if isinstance(sub_content, list):
                    if len(sub_content) > 0:
                        final_video_url = str(sub_content[0])
                # Si c'est déjà une string
                elif isinstance(sub_content, str):
                    # Parfois stocké comme string "['https...']", nettoyage basique
                    clean = sub_content.strip()
                    if clean.startswith("['") and clean.endswith("']"):
                         final_video_url = clean[2:-2] # Enlève [' et ']
                    else:
                         final_video_url = clean
            
            subsections_list.append(Subsection(
                title=sub_title,
                description=None,
                video_url=final_video_url, 
                thumbnail_url=None, # À récupérer via une jointure table video si nécessaire
                channel_title=None
            ))

        # Création de l'objet Section
        sections_list.append(Section(
            title=s_title,
            description=s_desc,
            subsections=subsections_list,
            project=None # À implémenter si vous avez une table project liée
        ))

    # 4. Retourner l'objet complet


    return CompleteCourse(
        title=c_title,
        introduction=c_desc,
        tag="Generated", # Valeur par défaut ou à récupérer
        sections=sections_list
    )