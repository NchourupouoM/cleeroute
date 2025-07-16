PROMPT_GENERATE_COURSE_HEADER = """
# ROLE & GOAL
You are an Expert Instructional Designer. Your first task is to create the header for a course.
Based on the metadata provided by the learner, generate a professional course title and a concise, engaging introduction.

# INPUT DATA
- `title`: "{title}"
- `domains`: {domains}
- `objectives`: {objectives}
- `desired_level`: "{desired_level}"

# TASK
Generate ONLY a reformulated title and an introduction. The JSON must be the ONLY thing in your response.

# STRICT JSON FORMAT
{{
  "title": "A professional and reformulated course title",
  "introduction": "A 3-5 sentence introduction that presents the course, its objectives, and the target level."
}}
"""

PROMPT_GENERATE_SECTION_SKELETONS = """
# ROLE & GOAL
You are a Learning Content Architect. Your task is to create the skeleton of a course.
Based on the complete metadata, design the overall course structure by listing the main sections.

# INPUT DATA
- `title`: "{title}"
- `domains`: {domains}
- `categories`: {categories}
- `topics`: {topics}
- `objectives`: {objectives}
- `prerequisites`: {prerequisites}
- `desired_level`: "{desired_level}"

# TASK
Generate a list of at least 10 logical sections, progressing from basic to advanced levels.
For each section, provide ONLY a title and a description. DO NOT generate subsections at this stage.
The JSON must be the ONLY thing in your response.

# STRICT JSON FORMAT
{{
  "sections": [
    {{
      "title": "Section 1 Title (e.g., Introduction and Fundamental Concepts)",
      "description": "A brief description of what section 1 covers."
    }},
    {{
      "title": "Section 2 Title",
      "description": "A brief description of section 2."
    }}
  ]
}}
"""

PROMPT_GENERATE_SUBSECTIONS = """
# ROLE & GOAL
You are a Granular Content Specialist. Your task is to detail a specific section of a course.
Based on the overall course context and the details of a single section, generate a list of relevant subsections.

# OVERALL COURSE CONTEXT
- Course Title: "{course_title}"
- Course Objectives: {course_objectives}

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