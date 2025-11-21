# from typing import Optional
# # Assurez-vous d'importer vos modèles de cours définis dans votre prompt
# from src.cleeroute.langGraph.learners_api.course_gen.models import CompleteCourse # (Adaptez le chemin d'import selon votre structure)


# def extract_context_from_course(
#     course: CompleteCourse, 
#     scope: str, 
#     section_idx: Optional[int] = None, 
#     subsection_idx: Optional[int] = None
# ) -> tuple[str, str]:
#     """
#     Parcourt l'objet CompleteCourse et retourne :
#     1. Une chaîne de texte contenant le contexte pertinent.
#     2. Un titre court décrivant ce contexte.
#     """
#     context_text = ""
#     context_title = ""

#     # --- CAS 1 : Tout le cours ---
#     if scope == "course":
#         context_title = f"Full Course: {course.title}"
#         context_text += f"COURSE TITLE: {course.title}\n"
#         context_text += f"INTRODUCTION: {course.introduction}\n\n"
        
#         for i, sec in enumerate(course.sections):
#             context_text += f"SECTION {i}: {sec.title}\n"
#             if sec.description:
#                 context_text += f"Description: {sec.description}\n"
#             # On liste juste les titres des sous-sections pour ne pas surcharger le contexte global
#             for sub in sec.subsections:
#                 context_text += f" - Topic: {sub.title}\n"
#             context_text += "\n"

#     # --- CAS 2 : Une Section Spécifique ---
#     elif scope == "section":
#         if section_idx is None or section_idx < 0 or section_idx >= len(course.sections):
#             return "Invalid Section Index", "Error"
        
#         section = course.sections[section_idx]
#         context_title = f"Section: {section.title}"
        
#         context_text += f"SECTION: {section.title}\n"
#         context_text += f"DESCRIPTION: {section.description}\n\n"
        
#         if section.project:
#             context_text += "--- PROJECT ---\n"
#             context_text += f"Title: {section.project.title}\n"
#             context_text += f"Objective: {section.project.description}\n"
#             context_text += f"Deliverables: {', '.join(section.project.deliverables)}\n\n"
            
#         context_text += "--- SUBSECTIONS ---\n"
#         for sub in section.subsections:
#             context_text += f"Title: {sub.title}\n"
#             context_text += f"Content/Description: {sub.description}\n"
#             context_text += f"Video Source: {sub.video_url}\n\n"

#     # --- CAS 3 : Une Sous-section Spécifique ---
#     elif scope == "subsection":
#         if (section_idx is None or section_idx >= len(course.sections) or 
#             subsection_idx is None):
#             return "Invalid Index", "Error"
            
#         section = course.sections[section_idx]
#         if subsection_idx < 0 or subsection_idx >= len(section.subsections):
#             return "Invalid Subsection Index", "Error"
            
#         subsection = section.subsections[subsection_idx]
#         context_title = f"Subsection: {subsection.title}"
        
#         context_text += f"PARENT SECTION: {section.title}\n"
#         context_text += f"TOPIC: {subsection.title}\n"
#         context_text += f"DETAILS: {subsection.description}\n"
#         context_text += f"WATCH VIDEO AT: {subsection.video_url}\n"
#         if subsection.channel_title:
#             context_text += f"CHANNEL: {subsection.channel_title}\n"

#     return context_text, context_title