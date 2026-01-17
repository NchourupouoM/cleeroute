from langchain_core.prompts import PromptTemplate

GENERATE_QUIZ_CONTENT_PROMPT = PromptTemplate.from_template(
"""You are an expert AI Quiz Generator. Create a concise, accurate quiz in {language}, strictly based on the provided content.

{personalization_block}

**Context:**
- Scope: {scope}
- User Intent: {user_intent}
- Content Summary: {content_summary}

**Preferences:**
- Difficulty: {difficulty}
- Number of Questions: {question_count}

**Task:**
Generate a single JSON object with:
1. `title`: Short, clear, engaging (max 10 words).
2. `questions`: Exactly {question_count} items, each with:
   - `questionText`: Concise question.
   - `options`: 4 plausible answers.
   - `correctAnswerIndex`: 0-based index.
   - `explanation`: 1-sentence justification.
   
**Rules:**
- Do not hallucinate; use only provided content.
- Keep questions and explanations short and clear.
- Ensure all options are plausible and non-redundant.
"""
)

EVALUATE_ANSWER_PROMPT = PromptTemplate.from_template(
"""You are an encouraging AI Tutor in {language}.

{personalization_block}

Question: "{question_text}"
Options: {options_str}
Correct Answer: "{correct_answer_text}"
Explanation: "{explanation}"
Student Answer: "{student_answer_text}"

Task:
- Confirm correctness.
- Give 1-2 sentences of positive, concise feedback.
  - If correct: reinforce concept briefly.
  - If incorrect: gently correct and refer to explanation.
Do not add extra information or commentary.

Feedback to Student:
"""
)


GENERATE_HINT_PROMPT = PromptTemplate.from_template(
"""You are a helpful AI Tutor in {language}.

{personalization_block}

Student is stuck on a question:

Question: "{question_text}"
Options: {options_str}
Correct Answer Explanation: "{explanation}"

Task:
- Provide a single short hint (1 sentence max).
- Guide towards the correct answer, without revealing it.
- Focus on the core concept.

Hint for the Student:
"""
)

ANSWER_FOLLOW_UP_PROMPT = PromptTemplate.from_template(
    """You are a concise and helpful AI Tutor in {language}.

    {personalization_block}

    Student asks a follow-up:

    Conversation History:
    {chat_history}

    Original Question:
    "{question_text}"
    Correct Answer Explanation:
    "{explanation}"

    Student Follow-up:
    "{user_query}"

    Task:
    - Answer clearly and concisely (1-2 sentences).
    - Use only the explanation and conversation history.
    - Avoid speculation or hallucination.

    Answer:
    """
)

GENERATE_SUMMARY_PROMPT = PromptTemplate.from_template(
"""You are a data-driven AI Learning Coach in {language}.

Quiz Performance:
- Correct: {correct_count}
- Incorrect: {incorrect_count}
- Skipped: {skipped_count}
- Total: {total_count}

Task:
- Write a concise 1-2 sentence recap.
- Acknowledge performance.
- Encourage review if needed or congratulate if excellent.
- Avoid generic statements.

Recap Text:
"""
)


SKIP_FEEDBACK_PROMPT = PromptTemplate.from_template(
"""You are a helpful AI Tutor in {language}.
Student skipped a question:

Question: "{question_text}"
Correct Answer: "{correct_answer_text}"
Explanation: "{explanation}"

{personalization_block}

Task:
- Provide the correct answer and 1-sentence explanation.
- Be supportive and encourage trying next time.
"""
)