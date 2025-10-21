# from src.cleeroute.models import Section, Project, Subsection, CompleteCourse, ActionType, ModificationInstruction
# from thefuzz import process
# from typing import Optional

# def _apply_course_level_modification(instruction: ModificationInstruction, course: CompleteCourse):
#     print("  -> Spécialiste: _apply_course_level_modification")
#     target_type = instruction.target_type
#     value = instruction.new_value or instruction.new_description or instruction.new_title
#     if isinstance(value, str):
#         if target_type == "course_title": 
#             course.title = value
#         elif target_type == "course_introduction": 
#             course.introduction = value
#     else:
#         raise ValueError(f"Une valeur de type chaîne est requise pour mettre à jour {target_type}")


# def _apply_section_modification(instruction: ModificationInstruction, course: CompleteCourse):
#     print("  -> Spécialiste: _apply_section_modification")
#     action = instruction.action
#     if action == ActionType.ADD:
#         if isinstance(instruction.new_value, dict):
#             new_section = Section(**instruction.new_value)
#         elif instruction.new_title:
#             new_section = Section(title=instruction.new_title, description=instruction.new_description or "", subsections=[], project=None)
#         else:
#             raise ValueError("Pour ajouter une section, `new_value` (dict) ou `new_title` est requis.")
#         if any(s.title == new_section.title for s in course.sections): raise ValueError(f"Section '{new_section.title}' existe déjà.")
#         course.sections.append(new_section)
#         print(f"    -> Section '{new_section.title}' ajoutée avec succès.")
    
#     elif action == ActionType.DELETE:
#         # CORRECTION : Gère la suppression par titre OU par index
#         idx_to_delete = -1
#         if instruction.section_title_id:
#             idx_to_delete = next((i for i, s in enumerate(course.sections) if s.title == instruction.section_title_id), -1)
#         elif instruction.index is not None and 0 <= instruction.index < len(course.sections):
#             idx_to_delete = instruction.index
        
#         if idx_to_delete != -1:
#             deleted_title = course.sections[idx_to_delete].title
#             del course.sections[idx_to_delete]
#             print(f"    -> Section '{deleted_title}' supprimée avec succès.")
#         else:
#             raise ValueError("Section à supprimer introuvable (via title_id ou index).")
#     elif action == ActionType.UPDATE:
#         # NOUVELLE LOGIQUE DE RÉORGANISATION ROBUSTE
#         if instruction.index is not None and instruction.section_title_id:
#             section_to_move = None
#             original_index = -1
#             # On cherche l'index et l'objet en même temps
#             for i, sec in enumerate(course.sections):
#                 if sec.title == instruction.section_title_id:
#                     section_to_move = sec
#                     original_index = i
#                     break
            
#             if original_index == -1:
#                 raise ValueError(f"Section '{instruction.section_title_id}' not found to move.")
            
#             # On retire l'objet de la liste
#             moved_section = course.sections.pop(original_index)
#             # On le réinsère à la nouvelle position
#             course.sections.insert(instruction.index, moved_section)
#             print(f"    -> Section '{moved_section.title}' moved to index {instruction.index}.")
#         else:
#             raise ValueError("Update action for a section requires a 'section_title_id' and 'index'.")

# def _apply_subsection_modification(instruction: ModificationInstruction, course: CompleteCourse):
#     print("  -> Spécialiste: _apply_subsection_modification")
#     section_title_id = instruction.section_title_id
#     if not section_title_id: raise ValueError("section_title_id est requis.")
#     target_section = next((s for s in course.sections if s.title == section_title_id), None)
#     if not target_section: raise ValueError(f"Section '{section_title_id}' introuvable.")
    
#     action = instruction.action
#     if action == ActionType.ADD:
#         title = instruction.new_title
#         description = instruction.new_description or ""
#         if not title: raise ValueError("`new_title` est requis pour ajouter une sous-section.")
#         new_sub = Subsection(title=title, description=description)
#         if any(ss.title == new_sub.title for ss in target_section.subsections): raise ValueError(f"Sous-section '{new_sub.title}' existe déjà.")
#         target_section.subsections.append(new_sub)
#         print(f"    -> Sous-section '{title}' ajoutée avec succès.")
    
#     else: # Gérer UPDATE et DELETE
#         subsection_title_id = instruction.subsection_title_id
#         if not subsection_title_id: raise ValueError("subsection_title_id est requis pour cette action.")
#         sub_idx = next((i for i, ss in enumerate(target_section.subsections) if ss.title == subsection_title_id), -1)
#         if sub_idx == -1: raise ValueError(f"Sous-section '{subsection_title_id}' introuvable.")

#         if action == ActionType.DELETE:
#             del target_section.subsections[sub_idx]
#             print(f"    -> Sous-section '{subsection_title_id}' supprimée avec succès.")
        
#         elif action == ActionType.UPDATE:
#             # CORRECTION : Ajout de la logique de mise à jour manquante
#             target_subsection = target_section.subsections[sub_idx]
#             value = instruction.new_value or instruction.new_description
#             if instruction.target_type == "subsection_title" and isinstance(instruction.new_title, str):
#                 target_subsection.title = instruction.new_title
#             elif instruction.target_type == "subsection_description" and isinstance(value, str):
#                 target_subsection.description = value
#             else:
#                 raise ValueError("Action de mise à jour de sous-section non valide ou valeur manquante.")
#             print(f"    -> Sous-section '{subsection_title_id}' mise à jour avec succès.")

# # Dans votre fichier de fonctions spécialistes (ex: utils.py)

# def _apply_project_modification(instruction: ModificationInstruction, course: CompleteCourse):
#     """
#     Spécialiste pour TOUTES les modifications liées à un projet. Version finale et corrigée.
#     """
#     print("  -> Spécialiste: _apply_project_modification")
#     section_title_id = instruction.section_title_id
#     if not section_title_id: 
#         raise ValueError("section_title_id est requis.")
#     target_section = next((s for s in course.sections if s.title == section_title_id), None)
#     if not target_section: 
#         raise ValueError(f"Section '{section_title_id}' introuvable.")

#     action = instruction.action
#     target_type = instruction.target_type

#     # CAS 1: L'instruction concerne l'objet Projet lui-même (ajout, suppression)
#     if target_type == "section_project":
#         if action == ActionType.ADD:
#             title = instruction.new_title
#             if not title: raise ValueError("`new_title` est requis pour ajouter un projet.")
#             new_project = Project(
#                 title=title, 
#                 description=instruction.new_description or "",
#                 objectives=[], prerequisites=[], Steps=[], Deliverable=[]
#             )
#             target_section.project = new_project
#             print(f"    -> Projet '{title}' ajouté avec succès à la section '{target_section.title}'.")
#         elif action == ActionType.DELETE:
#             target_section.project = None
#             print(f"    -> Projet supprimé avec succès de la section '{target_section.title}'.")
#         else:
#             raise ValueError(f"Action '{action.value}' non supportée pour le target_type 'section_project'.")
#         return # Fin de l'exécution pour ce cas

#     # CAS 2: L'instruction concerne les champs À L'INTÉRIEUR d'un projet existant
#     project = target_section.project
#     if not project:
#         raise ValueError(f"Aucun projet n'existe dans la section '{section_title_id}' pour le modifier.")

#     value = instruction.new_value or instruction.new_description or instruction.new_title

#     if target_type == "project_title":
#         if action == ActionType.UPDATE and isinstance(value, str): project.title = value
#         else: raise ValueError("Action/valeur invalide pour project_title")
    
#     elif target_type == "project_description":
#         if action == ActionType.UPDATE and isinstance(value, str): project.description = value
#         else: raise ValueError("Action/valeur invalide pour project_description")
    
#     else: # CAS 3 : L'instruction concerne les listes du projet
#         list_attr_map = {
#             "project_objective": "objectives", "project_prerequisite": "prerequisites",
#             "project_step": "Steps", "project_deliverable": "Deliverable",
#             "project_evaluation_criteria": "evaluation_criteria"
#         }
#         list_attr_name = list_attr_map.get(target_type)
#         if not list_attr_name:
#             raise ValueError(f"Type de cible de projet non géré : {target_type}")

#         # 1. On récupère la liste existante ou une liste vide.
#         original_list = getattr(project, list_attr_name, []) or []
        
#         # 2. On crée une NOUVELLE liste en copiant l'ancienne.
#         new_list = original_list.copy()

#         # 3. On modifie cette NOUVELLE liste.
#         if instruction.action == ActionType.ADD:
#             value_to_add = instruction.new_value
#             if isinstance(value_to_add, list) and len(value_to_add) == 1:
#                 value_to_add = value_to_add[0]
#             if not isinstance(value_to_add, str):
#                 raise ValueError(f"L'ajout à '{list_attr_name}' requiert une chaîne.")
            
#             new_list.append(value_to_add)
#             print(f"    -> Ajout de '{value_to_add}' à la liste '{list_attr_name}'.")

#         elif instruction.action == ActionType.DELETE:
#             value_to_remove = instruction.new_value

#             if isinstance(value_to_remove, list) and len(value_to_remove) == 1:
#                 value_to_remove = value_to_remove[0] # On extrait la chaîne de la liste

#             if not isinstance(value_to_remove, str):
#                  raise ValueError("A string value is required to remove an item from a list.")
            
#             if value_to_remove in new_list:
#                 new_list.remove(value_to_remove)
#                 print(f"-> Suppression de '{value_to_remove}' de la liste '{list_attr_name}'.")
#             else:
#                 print(f"-> WARNING: Item '{value_to_remove}' not found in list '{list_attr_name}'. No changes made.")
        
#         elif instruction.action == ActionType.UPDATE:
#              if isinstance(instruction.new_value, list):
#                  new_list = instruction.new_value
#                  print(f"    -> Remplacement de la liste '{list_attr_name}'.")
#              else:
#                  raise ValueError(f"La mise à jour de '{list_attr_name}' requiert une liste.")

#         # 4. On REMPLACE l'ancienne liste par la nouvelle.
#         #    C'est cette assignation que Pydantic est garanti de détecter.
#         setattr(project, list_attr_name, new_list)

# def _find_closest_section(title_query: str, course: CompleteCourse) -> Optional[Section]:
#     """Trouve la section la plus proche d'un titre donné en utilisant la recherche floue."""
#     if not title_query:
#         return None
#     section_titles = [s.title for s in course.sections]
#     if not section_titles:
#         return None
    
#     # process.extractOne retourne le meilleur match et son score (0-100)
#     best_match, score = process.extractOne(title_query, section_titles)
    
#     # On accepte le match seulement s'il est suffisamment bon (seuil à ajuster)
#     if score > 80:
#         print(f"  -> Fuzzy Match: '{title_query}' -> '{best_match}' (Score: {score})")
#         return next((s for s in course.sections if s.title == best_match), None)
    
#     print(f"  -> Fuzzy Match: Aucun match trouvé pour '{title_query}' (Meilleur score: {score})")
#     return None

# def _apply_intra_section_modification(instruction: ModificationInstruction, course: CompleteCourse):
#     print("  -> Spécialiste: _apply_intra_section_modification")
#     section_title_id = instruction.section_title_id

#     if not section_title_id: 
#         raise ValueError("section_title_id est requis.")
    
#     target_section = _find_closest_section(instruction.section_title_id, course)
    
#     if not target_section: 
#         raise ValueError(f"Section '{section_title_id}' introuvable.")
    
#     target_type = instruction.target_type
#     value = instruction.new_value or instruction.new_description or instruction.new_title
#     if isinstance(value, str):
#         if target_type == "section_title": target_section.title = value
#         elif target_type == "section_description": target_section.description = value
