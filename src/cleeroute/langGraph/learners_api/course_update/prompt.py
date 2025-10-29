from langchain_core.prompts import PromptTemplate

ACTION_CLASSIFIER_PROMPT = PromptTemplate.from_template(
"""You are an expert intent classification engine. Your sole purpose is to analyze a user's request for modifying a course syllabus and classify it into exactly ONE of the following five categories.

**Classification Categories & Criteria:**

1.  **REMOVE**: The user wants to delete, remove, or get rid of a specific piece of content.
    - *Keywords: "remove", "delete", "get rid of", "don't want"*

2.  **ADD**: The user wants to include, insert, or add a new topic or section.
    - *Keywords: "add", "include", "can you put in", "I want a section on"*

3.  **REPLACE**: The user wants to swap existing content for something else. This involves both a removal and an addition.
    - *Keywords: "replace", "swap", "instead of X, add Y", "change this for that"*

4.  **CLARIFY**: The user's request is vague, ambiguous, incomplete, or refers to content that does not exist. Your function is to flag this for clarification.
    - *Examples: "make it better", "change it", "I don't like it", "can you fix section 10" (when only 5 exist).*

5.  **FINALIZE**: The user expresses satisfaction and wants to complete the process.
    - *Keywords: "it's perfect", "looks great", "I'm done", "that's all"*

**Examples:**

- User Request: "get rid of the part about the history of programming"
- Category: REMOVE

- User Request: "I think it needs a module on cloud deployment with AWS"
- Category: ADD

- User Request: "The first section is too theoretical, can we replace it with a hands-on project?"
- Category: REPLACE

- User Request: "Just tweak it a bit"
- Category: CLARIFY

- User Request: "Perfect, this is exactly what I wanted. Thank you."
- Category: FINALIZE

---
**User Request:**
"{user_request}"

**Category:**
"""
)


PARAMETER_GENERATOR_PROMPT = PromptTemplate.from_template(
"""You are a precision parameter extraction AI. Your task is to extract the parameters required to execute a specific action, based on the user's request and the overall course context.

**OVERALL COURSE CONTEXT**
- **Course Title:** "{course_title}"
- **Course Introduction:** "{course_introduction}"
- **Current Section Titles:** {section_titles}

**USER REQUEST:**
"{user_request}"

**ACTION TO PERFORM:**
"{action_name}"

**INSTRUCTION:**
- **Task:** {instruction}
- **Rules:**
    - For actions involving section titles (`REMOVE`, `REPLACE`), you MUST use the exact title from the 'Current Section Titles' list.
    - For search queries (`ADD`, `REPLACE`), the query MUST be specific and relevant to the overall course context. For example, for a Python course, a query for "data structures" should be "python data structures tutorial".

**PARAMETERS:**
"""
)

MESSAGE_GENERATOR_PROMPT = PromptTemplate.from_template(
"""You are a helpful and conversational AI course editor.
Your task is to create a natural, user-friendly message based on a technical operation report.

**Context:**
The user is in a loop of modifying their course. You just performed an action for them.

**Technical Operation Report:**
"{operation_report}"

**Your Task:**
- If the operation was a success, confirm it clearly and ask an open-ended question like "What would you like to do next?" or "Any other changes?".
- If the operation failed, explain the issue simply (without technical jargon) and guide the user on how to proceed.
- Keep the tone helpful and encouraging.

**Message to User:**
"""
)

SUMMARIZER_PROMPT = PromptTemplate.from_template(
"""You are a concise technical writer. Your task is to summarize the provided text into a maximum of two short, clear sentences. Focus on the main purpose and content.

**Original Text:**
"{text_to_summarize}"

**Summarized Text (max 2 sentences):**
"""
)