PROMPT_GENERATE_COURSE_OUTLINE = """
# ROLE & GOAL
You are an Expert Instructional Designer and Learning Content Architect.
Your task is to create the complete high-level outline for a course, including a professional title, an engaging introduction, and a structured list of main sections.

# INPUT DATA
- `original_title`: "{title}"
- `domains`: {domains}
- `categories`: {categories}
- `topics`: {topics}
- `objectives`: {objectives}
- `expectations`: {expectations}
- `prerequisites`: {prerequisites}
- `desired_level`: "{desired_level}"

# TASK
Generate a single JSON object that contains:
1.  A professional, reformulated course title.
2.  A concise and engaging 3-5 sentence introduction that presents the course, its objectives, and the target level.
3.  A list of at least 10 logical main sections, progressing from basic to advanced levels. Each section must have ONLY a title and a description. DO NOT generate subsections at this stage.

The JSON must be the ONLY thing in your response.

# STRICT JSON FORMAT
{{
  "title": "A professional and reformulated course title",
  "introduction": "A 3-5 sentence introduction that presents the course, its objectives, and the target level."
  "sections": [
    {{
      "title": "Section 1 Title (e.g., Introduction and Fundamental Concepts)",
      "description": "A brief description of what section 1 covers."
    }},
    {{
      "title": "Section 2 Title (e.g., Core Principles)",
      "description": "A brief description of section 2's content, building on previous concepts."
    }},
    // Add more examples if you think it helps the LLM
    {{
      "title": "Section N Title",
      "description": "A brief description of section N."
    }}
  ]
}}
"""

# Le PROMPT_GENERATE_SUBSECTIONS reste inchangé
PROMPT_GENERATE_SUBSECTIONS = """
# ROLE & GOAL
You are a Granular Content Specialist. Your task is to detail a specific section of a course.
Based on the overall course context and the details of a single section, generate a list of relevant subsections.

# OVERALL COURSE CONTEXT
- Course Title: "{course_title}"
- Course introduction: {course_introduction}

# SECTION TO DETAIL
- Section Title: "{section_title}"
- Section Description: "{section_description}"

# TASK
Generate a list of 3 to 6 logical and detailed subsections for the provided section. Each subsection must have a title and a description.
The JSON must be the ONLY thing in your response.

# STRICT JSON FORMAT
{{
  "subsections": [
    {{
      "title": "Subsection 1.1 Title",
      "description": "Description of what the learner will learn here."
    }},
    {{
      "title": "Subsection 1.2 Title",
      "description": "Description of the subsection."
    }}
  ]
}}
"""