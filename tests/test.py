# Plan de Test Complet pour le Système de Modification de Cours
# Catégorie 1 : Création d'Objets
# Test 1.1 : Création Simple (Succès direct)

# Question :
# "In the 'Neural Network Basics' section, add a new subsection titled 'Loss Functions' with the description 'Understanding how models measure their error'." OK.

# Comportement Attendu : Le système doit ajouter la sous-section directement, sans intervention. L'instruction générée doit avoir is_improvised: false.

# Test 1.2 : Création par Improvisation Intelligente (Pause pour validation)

# Question :
# "Add a new section about Transformers." OK.

# Comportement Attendu :

# Le système doit créer une section avec un titre comme "Transformers" et une description plausible qu'il a générée lui-même.

# L'instruction doit avoir is_improvised: true.

# Le graphe doit s'arrêter après le résumé, en demandant votre validation. Le message final doit être du type : "J'ai pris l'initiative de créer une section 'Transformers' avec une description. Est-ce que cela vous convient ? L'opération est en pause en attendant votre retour."

# Test 1.3 : Création Ambiguë (Intervention pour clarification)

# Question :
# "Add a new section." ?

# Comportement Attendu :

# Le système doit s'arrêter immédiatement pour intervention humaine.

# Le message doit être du type : "I can add a new section, but I need a title to proceed. What should the title be?"

# Correction Input (correction_input) :
# "The title is 'Attention Mechanisms'. Please also add a subsection titled 'Self-Attention' and a project for it."

# Comportement Attendu après Correction :

# Le système doit reprendre et générer une liste de 3 instructions simples (une pour la section, une pour la sous-section, une pour le projet).

# Les instructions pour la description de la section, la description de la sous-section et la description du projet doivent avoir is_improvised: true.

# Le système doit appliquer les 3 changements, puis s'arrêter pour validation du brouillon.

# Catégorie 2 : Modification de Listes (Précision Chirurgicale)
# Test 2.1 : Ajouter un Item à une Liste (Succès direct)

# Question :
# "In the project for the first section, add 'Basic statistics' as a prerequisite." Ok

# Comportement Attendu : Le système doit trouver la section "Introduction to Deep Learning", trouver son projet, et ajouter "Basic statistics" à la liste prerequisites. L'opération doit se terminer avec succès.

# Test 2.2 : Supprimer un Item d'une Liste (Succès direct)

# Question :
# "In the 'Build a Simple Neural Network' project, remove the 'Linear algebra fundamentals' prerequisite."

# Comportement Attendu : Le système doit trouver le bon projet et supprimer l'élément de la liste prerequisites. L'opération doit se terminer avec succès.

# Test 2.3 : Remplacer une Liste Entière (Succès direct)

# Question :
# "For the project in the 'CNNs' section, set the deliverables to just one item: 'A documented Jupyter Notebook'." OK

# Comportement Attendu : Le système doit trouver le bon projet et remplacer la liste Deliverable existante par la nouvelle liste ["A documented Jupyter Notebook"].

# Catégorie 3 : Modification de Texte ("Read-Modify-Write")
# Test 3.1 : Modifier le Contenu d'une Description (Succès direct)

# Question :
# "In the 'LSTMs and GRUs' subsection, mention that they are particularly effective for time-series forecasting." OK

# Comportement Attendu :

# L'IA doit lire la description existante ("Learn how these architectures solve the vanishing gradient problem.").

# Elle doit générer une nouvelle description complète, par exemple : "Learn how these architectures solve the vanishing gradient problem. They are particularly effective for time-series forecasting."

# Le système doit appliquer ce changement et se terminer avec succès.

# Catégorie 4 : Suppression et Réorganisation
# Test 4.1 : Suppression d'un Objet (Succès direct)

# Question :
# "Delete the subsection 'History of Neural Networks' from the introduction section." Ok

# Comportement Attendu : Le système doit trouver et supprimer la sous-section spécifiée. L'opération doit se terminer avec succès.

# Test 4.2 : Réorganisation (Succès direct)

# Question :
# "Move the last section, 'Recurrent Neural Networks (RNNs)', to be the second section in the course (index 1)." ? OK

# Comportement Attendu : Le système doit modifier l'ordre des sections dans la liste sections. L'opération doit se terminer avec succès.

# Test Bonus : La Requête Complexe
# Test 5.1 : Requête Mixte (Clarification -> Décomposition -> Improvisation -> Validation)

# Question :
# "I want a new final section. It should cover model deployment. Also, in the very first section, add 'Cloud computing basics' to the project prerequisites." OK

# Comportement Attendu :

# Le système pourrait demander une clarification pour la nouvelle section ("Quel est le titre de la section 'model deployment' ?").

# Correction Input (correction_input) :
# "The title is 'Deploying Deep Learning Models'."

# Comportement Attendu après Correction :

# L'IA doit générer une liste de 2 instructions :

# Une instruction add pour la nouvelle section "Deploying Deep Learning Models" (avec is_improvised: true pour la description).

# Une instruction add pour le project_prerequisite dans la section "Introduction to Deep Learning" (avec is_improvised: false).

# Le système doit appliquer les deux changements.

# Comme l'une des étapes était une improvisation, le système doit s'arrêter pour validation.