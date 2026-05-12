"""
AutoJob AI — Screening Question Answerer Agent
Uses LLM to answer LinkedIn Easy Apply screening questions based on the user's full profile.

The AI acts AS the user — it knows everything about the user's background,
skills, experience, education, and preferences. It answers honestly and
strategically to maximize the user's chances of getting the job.
"""

import json
import logging

from app.utils.llm import llm_chat

logger = logging.getLogger("autojob.agents.screening")

SCREENING_PROMPT = """You are acting AS the job applicant. You have complete knowledge of
the applicant's profile below. Answer each screening question as if you ARE this person.

RULES:
1. Answer honestly based on the profile data.
2. For yes/no questions, respond with exactly "Yes" or "No".
3. For dropdown/select questions, pick the BEST matching option from the provided choices.
4. For text questions, keep answers concise (1-2 sentences max).
5. If the profile doesn't have enough information for a question, make a reasonable
   inference based on available data (skills, experience, education, etc.).
6. Always lean towards answers that help the applicant get the job, while staying truthful.

CRITICAL — NUMERIC ANSWER RULES (these fields ONLY accept numbers):
- Experience questions (years of experience, experience in X): respond with ONLY a decimal number. Examples: "1", "0.5", "2", "0"
  - "1 year" is WRONG → "1" is CORRECT
  - "No experience" is WRONG → "0" is CORRECT
  - "6 months" is WRONG → "0.5" is CORRECT
- CTC / Salary questions (current CTC, expected CTC, salary): respond with ONLY a decimal number (in LPA).
  - "Not specified" is WRONG → "0" is CORRECT
  - "3-5 LPA" is WRONG → "5" is CORRECT  
  - "Not Applicable, I'm a fresher" is WRONG → "0" is CORRECT
- Notice period questions (notice period, days remaining): respond with ONLY a number of days.
  - "0 days, available immediately" is WRONG → "0" is CORRECT
  - "30 days" is WRONG → "30" is CORRECT
  - "Immediately" is WRONG → "0" is CORRECT

Return a JSON object where keys are the question labels (exactly as given) and values are
your answers.

Example input:
Questions: ["How many years of Python experience?", "Are you authorized to work in India?", "Current CTC in INR?", "Expected CTC?", "Notice period in days?"]

Example output:
{"How many years of Python experience?": "2", "Are you authorized to work in India?": "Yes", "Current CTC in INR?": "0", "Expected CTC?": "5", "Notice period in days?": "0"}

Return ONLY valid JSON, no other text."""


async def answer_screening_questions(
    user_profile: dict,
    job_info: dict,
    questions: list[dict],
) -> dict:
    """
    Answer screening questions using the user's full profile.

    Args:
        user_profile: Full user profile dict (name, skills, experience, resume_text, etc.)
        job_info: Job details (title, company, description)
        questions: List of question dicts, each with:
            - "label": The question text
            - "type": "text" | "number" | "select" | "radio" | "textarea"
            - "options": List of options (for select/radio) or None

    Returns:
        Dict mapping question label -> answer string
    """
    if not questions:
        return {}

    logger.info(f"Answering {len(questions)} screening questions via AI...")

    # Build profile context
    profile_text = _build_full_profile_text(user_profile)

    # Build job context
    job_text = (
        f"Job Title: {job_info.get('title', 'N/A')}\n"
        f"Company: {job_info.get('company', 'N/A')}\n"
        f"Location: {job_info.get('location', 'N/A')}\n"
    )
    if job_info.get("description"):
        job_text += f"Description (first 1000 chars): {job_info['description'][:1000]}\n"

    # Build questions text
    questions_text = ""
    for i, q in enumerate(questions, 1):
        questions_text += f"\n{i}. {q['label']}"
        if q.get("type"):
            questions_text += f" (type: {q['type']})"
        if q.get("options"):
            questions_text += f"\n   Options: {', '.join(q['options'])}"

    try:
        content = await llm_chat(
            messages=[
                {"role": "system", "content": SCREENING_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"APPLICANT PROFILE:\n{profile_text}\n\n"
                        f"JOB BEING APPLIED TO:\n{job_text}\n\n"
                        f"SCREENING QUESTIONS:{questions_text}"
                    ),
                },
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        answers = json.loads(content)
        logger.info(f"  AI answered {len(answers)} questions")

        return answers

    except Exception as e:
        logger.error(f"Screening question answerer failed: {e}")
        return {}


def _build_full_profile_text(profile: dict) -> str:
    """Build a comprehensive profile text that gives AI maximum context."""
    parts = []

    if profile.get("full_name"):
        parts.append(f"Name: {profile['full_name']}")
    if profile.get("name"):
        parts.append(f"Name: {profile['name']}")
    if profile.get("summary"):
        parts.append(f"Professional Summary: {profile['summary']}")
    if profile.get("skills"):
        skills = profile["skills"]
        if isinstance(skills, list):
            parts.append(f"Skills: {', '.join(skills)}")
        else:
            parts.append(f"Skills: {skills}")
    if profile.get("technologies"):
        parts.append(f"Technologies: {', '.join(profile['technologies'])}")
    if profile.get("experience_years") is not None:
        parts.append(f"Total Experience: {profile['experience_years']} years")
    if profile.get("current_ctc") is not None:
        parts.append(f"Current CTC: {profile['current_ctc']} LPA")
    if profile.get("expected_ctc") is not None:
        parts.append(f"Expected CTC: {profile['expected_ctc']} LPA")
    if profile.get("notice_period_days") is not None:
        parts.append(f"Notice Period: {profile['notice_period_days']} days")
    if profile.get("current_role"):
        parts.append(f"Current/Recent Role: {profile['current_role']}")
    if profile.get("preferred_roles"):
        parts.append(f"Target Roles: {', '.join(profile['preferred_roles'])}")
    if profile.get("education"):
        parts.append(f"Education: {profile['education']}")
    if profile.get("industries"):
        parts.append(f"Industries: {', '.join(profile['industries'])}")
    if profile.get("preferred_locations"):
        locs = profile["preferred_locations"]
        if isinstance(locs, list):
            parts.append(f"Preferred Locations: {', '.join(locs)}")
    if profile.get("phone"):
        parts.append(f"Phone: {profile['phone']}")
    if profile.get("linkedin_url"):
        parts.append(f"LinkedIn: {profile['linkedin_url']}")

    # Include raw resume text for maximum context (truncated)
    if profile.get("resume_text"):
        resume_snippet = profile["resume_text"][:3000]
        parts.append(f"\nFull Resume Text:\n{resume_snippet}")

    return "\n".join(parts) if parts else "No profile data available"
