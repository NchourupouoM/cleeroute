import streamlit as st
import requests
import json
from typing import Optional

# Configuration de la page
st.set_page_config(page_title="Générateur de Cours", layout="wide")
st.title("📚 Générateur de Cours Intelligent")

# Styles CSS personnalisés
st.markdown("""
<style>
    .section {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 20px;
    }
    .subsection {
        background-color: #ffffff;
        border-left: 4px solid #4e8cff;
        padding: 15px;
        margin: 10px 0;
        border-radius: 5px;
    }
    .quiz-question {
        background-color: #fff8e6;
        padding: 15px;
        margin: 10px 0;
        border-radius: 5px;
    }
    .project {
        background-color: #e6f7ff;
        padding: 20px;
        border-radius: 10px;
        margin: 15px 0;
    }
    h2 {
        color: #2c3e50;
    }
    h3 {
        color: #3498db;
    }
</style>
""", unsafe_allow_html=True)

# Formulaire de saisie
with st.form("course_form"):
    st.header("Paramètres du Cours")
    col1, col2 = st.columns(2)
    
    with col1:
        topic = st.text_input("Sujet du cours", "Python avancé")
        objective = st.text_area("Objectif principal", "Maîtriser les concepts avancés de Python")
    
    with col2:
        prerequisites = st.text_area("Prérequis", "Bases de Python, algorithmie")
        complexity = st.selectbox("Niveau", ["Débutant", "Intermédiaire", "Avancé"])
    
    submitted = st.form_submit_button("Générer le cours")

# Fonction pour appeler l'API
def generate_course(topic: str, objective: str, prerequisites: str) -> Optional[dict]:
    API_URL = "https://cleeroute-bt28.onrender.com/course-generated"  # Remplacez par votre URL
    
    payload = {
        "topic": topic,
        "objective": objective,
        "prerequisites": prerequisites
    }
    
    try:
        response = requests.post(API_URL, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Erreur lors de l'appel à l'API: {str(e)}")
        return None

# Affichage des résultats
if submitted:
    with st.spinner("Génération du cours en cours..."):
        course_data = generate_course(topic, objective, prerequisites)
        
        if course_data:
            st.success("Cours généré avec succès !")
            st.divider()
            
            # Affichage du titre et introduction
            st.header(course_data["title"])
            if course_data.get("introduction"):
                st.markdown(f"**Introduction:** {course_data['introduction']}")
            
            # Parcours des sections
            for section in course_data["sections"]:
                with st.container():
                    st.markdown(f'<div class="section"><h2>{section["title"]}</h2>', unsafe_allow_html=True)
                    
                    # Affichage des sous-sections
                    for subsection in section.get("subsections", []):
                        st.markdown(f"""
                        <div class="subsection">
                            <h3>{subsection["title"]}</h3>
                            <p>{subsection["description"]}</p>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # Affichage du quiz si présent
                    if section.get("quiz"):
                        st.subheader("Quiz")
                        for i, question in enumerate(section["quiz"], 1):
                            with st.expander(f"Question {i}: {question['question']}"):
                                st.write("**Options:**")
                                for opt in question["options"]:
                                    st.write(f"- {opt}")
                                st.success(f"**Réponse correcte:** {question['correct_answer']}")
                    
                    # Affichage du projet si présent
                    if section.get("project"):
                        with st.container():
                            st.markdown(f"""
                            <div class="project">
                                <h3>Projet: {section["project"]["title"]}</h3>
                                <p><strong>Description:</strong> {section["project"]["description"]}</p>
                                
                                <h4>Objectifs:</h4>
                                <ul>
                                    {"".join(f"<li>{obj}</li>" for obj in section["project"]["objectives"])}
                                </ul>
                                
                                <h4>Livrables:</h4>
                                <ul>
                                    {"".join(f"<li>{deliv}</li>" for deliv in section["project"]["deliverables"])}
                                </ul>
                            </div>
                            """, unsafe_allow_html=True)
                    
                    st.markdown("</div>", unsafe_allow_html=True)  # Fermeture de la section
            
            # Option de téléchargement
            st.divider()
            st.download_button(
                label="Télécharger le cours (JSON)",
                data=json.dumps(course_data, indent=2, ensure_ascii=False),
                file_name=f"cours_{topic.lower().replace(' ', '_')}.json",
                mime="application/json"
            )