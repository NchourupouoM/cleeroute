import streamlit as st
import requests
import json
import time

# --- Configuration des deux Endpoints de l'API ---
METADATA_API_URL = "http://127.0.0.1:8000/metadata/generate-stream"
COURSE_API_URL = "http://127.0.0.1:8000/course/generate-course-stream"

# --- Fonctions d'aide pour l'affichage en Markdown ---
# Ces fonctions sont réutilisées pour la phase de streaming
def project_to_markdown(project):
    """Convertit un objet projet en une chaîne de caractères Markdown."""
    if not project:
        return ""
    steps_md = "\n".join([f"    {i+1}. {step}" for i, step in enumerate(project.get('steps', []))])
    objectives_md = "\n".join([f"    - {obj}" for obj in project.get('objectives', [])])
    prereqs_md = "\n".join([f"    - {pre}" for pre in project.get('prerequisites', [])])
    return f"""
        ### 🎓 Project: {project.get('title', 'N/A')}
        *"{project.get('description', '')}"*

        <details>
        <summary><strong>Click to see project details</strong></summary>

        **🎯 Objectives:**
        {objectives_md}

        **🔑 Prerequisites:**
        {prereqs_md}

        **📝 Steps:**
        {steps_md}

        **📦 Deliverable:** {project.get('deliverable', 'N/A')}
        </details>
        """

def section_to_markdown(section):
    """Convertit un objet section en une chaîne de caractères Markdown."""
    if not section:
        return ""
    subsections_md = "\n".join([f"- **{sub['title']}:** {sub['description']}" for sub in section.get('subsections', [])])
    project_md = project_to_markdown(section.get('project'))
    return f"""
        ## {section.get('title', 'Untitled Section')}
        {section.get('description', '')}

        #### 📚 Subsections
        {subsections_md}

        {project_md}
        ---
        """

def course_to_markdown(course_data):
    """Assemble le cours complet en un seul bloc Markdown."""
    if not course_data:
        return "Waiting for course data..."
    title = course_data.get('title', 'Untitled Course')
    introduction = course_data.get('introduction', 'No introduction yet.')
    sections_list = course_data.get('sections', {}).values()
    sorted_sections = sorted(sections_list, key=lambda s: s.get('order', 99))
    sections_md = "\n".join([section_to_markdown(s) for s in sorted_sections])
    return f"""
        # {title}

        > {introduction}

        ---

        {sections_md}
        """

# --- Initialisation de l'application ---
st.set_page_config(page_title="AI Course Generator", layout="wide")
st.title("🚀 AI-Powered Course Generator")
st.markdown("A two-step process to generate a complete course from a simple idea.")

# --- Gestion de l'état du workflow ---
# On utilise le session_state pour savoir à quelle étape on est.
if 'current_step' not in st.session_state:
    st.session_state.current_step = 'ideation' # 'ideation' ou 'generation'

# ==============================================================================
# ======================== ETAPE 2 : GÉNÉRATION DU COURS COMPLET ========================
# ==============================================================================
if st.session_state.current_step == 'generation':
    st.header("Step 2: Generate the Full Course 🧠")
    st.markdown("Review or edit the generated blueprint, then click generate to create the full course content with real-time streaming.")
    
    # Bouton pour revenir à l'étape 1
    if st.button("⬅️ Back to Ideation"):
        st.session_state.current_step = 'ideation'
        # On peut optionnellement nettoyer les données
        if 'course_metadata' in st.session_state:
            del st.session_state['course_metadata']
        if 'course_data' in st.session_state:
            del st.session_state['course_data']
        st.rerun()

    with st.expander("Review and Edit Course Blueprint", expanded=True):
        metadata_json = st.text_area(
            "Course Blueprint (JSON format)",
            value=json.dumps(st.session_state.get('course_metadata', {}), indent=2),
            height=400
        )
        
        if st.button("Generate Full Course ✨", type="primary"):
            try:
                course_input_data = json.loads(metadata_json)
                st.session_state.process_running = True
            except json.JSONDecodeError:
                st.error("Invalid JSON format. Please check the blueprint.")
                st.session_state.process_running = False
        else:
            st.session_state.process_running = False

    # Zone d'affichage des résultats en streaming
    st.subheader("Generated Course Content")
    if st.session_state.get('process_running', False):
        status_placeholder = st.empty()
        result_placeholder = st.empty()
        st.session_state.course_data = {"sections": {}}

        try:
            response = requests.post(COURSE_API_URL, json=course_input_data, stream=True)
            response.raise_for_status()

            for line in response.iter_lines():
                if line.startswith(b'data:'):
                    data_str = line.decode('utf-8')[5:]
                    try:
                        update = json.loads(data_str)
                        event = update.get("event")
                        data = update.get("data")

                        if event == "status":
                            status_placeholder.info(f"⚙️ Status: {update.get('message')}", icon="⏳")
                        elif event == "outliner":
                            status_placeholder.info("Outline received! Detailing sections...", icon="🏗️")
                            st.session_state.course_data['title'] = data.get("course_title", "Untitled Course")
                            sections = data.get("outline", [])
                            for i, s in enumerate(sections):
                                s['order'] = i
                                st.session_state.course_data['sections'][s['title']] = s
                            result_placeholder.markdown(course_to_markdown(st.session_state.course_data), unsafe_allow_html=True)
                        elif event == "detailer":
                            status_placeholder.info("Sections detailed! Assembling...", icon="🧩")
                            detailed_sections = data.get("detailed_sections", [])
                            for section in detailed_sections:
                                if section['title'] in st.session_state.course_data['sections']:
                                    st.session_state.course_data['sections'][section['title']].update(section)
                            result_placeholder.markdown(course_to_markdown(st.session_state.course_data), unsafe_allow_html=True)
                        elif event == "assembler":
                            final_course = data.get("final_course", {})
                            st.session_state.course_data['introduction'] = final_course.get("introduction", "")
                            result_placeholder.markdown(course_to_markdown(st.session_state.course_data), unsafe_allow_html=True)
                        elif event == "end":
                            status_placeholder.success("🎉 Course generation complete!", icon="✅")
                            st.session_state.process_running = False
                            st.balloons()
                            break
                    except json.JSONDecodeError:
                        continue
        except requests.exceptions.RequestException as e:
            st.error(f"API Connection Error: Could not connect to the course generator.\nDetails: {e}")
        except Exception as e:
            st.error(f"An unexpected error occurred: {e}")
            
# ==============================================================================
# ======================== ETAPE 1 : GÉNÉRATION DES MÉTA-DONNÉES ========================
# ==============================================================================
else: # if st.session_state.current_step == 'ideation'
    st.header("Step 1: From Idea to Course Blueprint 🏠")
    st.markdown("Start with a simple idea. Our AI will generate the structured metadata needed to build a full course.")

    user_idea = st.text_area(
        "Describe the course you want to create in one or two sentences.",
        "I want to create a course to help people speak English like a native.",
        height=100,
        key="idea_input"
    )

    if st.button("Generate Course Blueprint ✨", type="primary"):
        if not user_idea:
            st.warning("Please enter a course idea.")
        else:
            request_payload = {"response": user_idea}
            
            with st.spinner("AI is thinking... Generating structured metadata..."):
                try:
                    response = requests.post(METADATA_API_URL, json=request_payload)
                    response.raise_for_status()
                    
                    # Stocker le résultat et changer d'étape
                    st.session_state.course_metadata = response.json()
                    st.session_state.current_step = 'generation'
                    st.rerun() # Forcer la ré-exécution du script pour afficher l'étape 2

                except requests.exceptions.RequestException as e:
                    st.error(f"API Connection Error: Could not connect to the metadata generator.\nDetails: {e}")
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")