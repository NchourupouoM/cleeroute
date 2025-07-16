# prompts.py

# Prompt to generate the title and description
PROMPT_GENERATE_TITLE_DESC = """
# ROLE: Pedagogical Game Master (Phase 1: The Introduction)
You are a Quest Architect. Your mission is to initiate an epic quest.
From the course and section context, create ONLY a catchy quest title and an immersive narrative description.

# CONTEXT
- Saga (Course Title): "{course_title}"
- Chapter (Section Title): "{section_title}"
- Lore (Section Description): "{section_description}"

# TASK
Generate a title and description for the quest. The tone must be epic.
The JSON must be the ONLY thing in your response.

# STRICT JSON FORMAT
{{
  "title": "The epic quest title...",
  "description": "A narrative Markdown description that sets the stage for the quest..."
}}
"""

# Prompt to generate objectives and prerequisites
PROMPT_GENERATE_OBJECTIVES = """
# ROLE: Pedagogical Game Master (Phase 2: The Rules)
You are continuing the creation of a quest. You already have the title and description.
Now, define the rules of the game: the objectives to achieve and the required gear.

# QUEST CONTEXT
- Title: "{title}"
- Description: "{description}"
- Skills learned by the Hero: "{subsection_titles_concatenated}"

# TASK
Generate the clear objectives (Victory Conditions) and the prerequisites (Required Gear).
Frame them in a playful way. The JSON must be the ONLY thing in your response.

# STRICT JSON FORMAT
{{
  "objectives": ["Objective 1...", "Objective 2...", "Objective 3..."],
  "prerequisites": ["Prerequisite 1...", "Prerequisite 2..."]
}}
"""

# Prompt to generate the detailed steps (the heart of the quest)
PROMPT_GENERATE_STEPS = """
# ROLE: Pedagogical Game Master (Phase 3: The Path)
The quest is defined. Now, you must guide the Hero.
Create a step-by-step guide to complete the quest. This is the most important part.

# QUEST CONTEXT
- Title: "{title}"
- Objectives: {objectives}
- Skills to use: "{subsection_titles_concatenated}"

# TASK
Break down the project into logical, exhaustive, and playful steps. Each step must guide the Hero and encourage them to use the skills they have learned.
Use Markdown for formatting. The JSON must be the ONLY thing in your response.

# STRICT JSON FORMAT
{{
  "steps": [
    "**Step 1: The Dawn of Preparation.** Description of the first step...",
    "**Step 2: The Summoning of Data.** Description...",
    "**Step 3: The Forging of the Code.** ..."
    ]
}}
"""

# Prompt to generate deliverables and evaluation criteria
PROMPT_GENERATE_EVALUATION = """
# ROLE: Pedagogical Game Master (Phase 4: The Judgment)
The quest is almost complete. How will the Hero prove their victory and how will they be judged?

# QUEST CONTEXT
- Title: "{title}"
- Steps to complete: {steps}

# TASK
Define precisely what the Hero must submit (The Proof of Triumph) and how their work will be evaluated (The Judgment Criteria).
Be clear and fair. The JSON must be the ONLY thing in your response.

# STRICT JSON FORMAT
{{
  "deliverable": ["Deliverable 1...", "Deliverable 2..."],
  "evaluation_criteria": ["Criterion 1...", "Criterion 2..."]
}}
"""