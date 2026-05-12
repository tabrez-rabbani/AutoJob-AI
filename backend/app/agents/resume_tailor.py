"""
AutoJob AI — Resume Tailor Agent
Generates job-specific resume summaries and cover letters via LLM.
"""

import json
import logging

from app.utils.llm import llm_chat

logger = logging.getLogger("autojob.agents.tailor")

RESUME_TAILOR_PROMPT = """You are a professional resume writer. Create a tailored resume summary and cover letter for this specific job application.

Return a JSON object with EXACTLY these fields:
{
  "tailored_summary": "3-4 sentence professional summary highlighting relevant experience for THIS role",
  "cover_letter": "Brief 3-paragraph cover letter (intro, why I'm a fit, closing). Keep under 200 words.",
  "key_highlights": ["highlight1", "highlight2", "highlight3"],
  "suggested_title": "Optimized resume title for this application"
}

Guidelines:
- Reference specific job requirements and match them to the candidate's skills
- Be professional but not generic — make it specific to this company and role
- Focus on achievements and impact, not just listing skills
- Keep the tone confident but not arrogant

Return ONLY valid JSON, no other text."""


async def tailor_resume(profile: dict, job: dict, match_result: dict) -> dict:
    """
    Generate a tailored resume summary and cover letter for a specific job.

    Args:
        profile: Structured profile from Profile Analyzer
        job: Job listing dict
        match_result: Match analysis from Job Matcher (score, reasons, etc.)

    Returns:
        Tailored resume content dict
    """
    logger.info(f"Tailoring resume for: '{job.get('title', '?')}' at {job.get('company', '?')}")

    profile_text = _build_profile_text(profile)
    job_text = _build_job_text(job)
    match_text = _build_match_text(match_result)

    content = await llm_chat(
        messages=[
            {"role": "system", "content": RESUME_TAILOR_PROMPT},
            {
                "role": "user",
                "content": (
                    f"CANDIDATE PROFILE:\n{profile_text}\n\n"
                    f"TARGET JOB:\n{job_text}\n\n"
                    f"MATCH ANALYSIS:\n{match_text}"
                ),
            },
        ],
        temperature=0.4,
        response_format={"type": "json_object"},
    )

    result = json.loads(content)
    logger.info(f"  Resume tailored — {len(result.get('cover_letter', ''))} char cover letter")

    return result


def _build_profile_text(profile: dict) -> str:
    """Build profile text for the prompt."""
    parts = [f"Name: {profile.get('name', 'Candidate')}"]
    if profile.get("summary"):
        parts.append(f"Summary: {profile['summary']}")
    if profile.get("skills"):
        parts.append(f"Skills: {', '.join(profile['skills'])}")
    if profile.get("experience_years"):
        parts.append(f"Experience: {profile['experience_years']} years")
    if profile.get("preferred_roles"):
        parts.append(f"Target Roles: {', '.join(profile['preferred_roles'])}")
    return "\n".join(parts)


def _build_job_text(job: dict) -> str:
    """Build job text for the prompt."""
    parts = [f"Title: {job.get('title', 'N/A')}", f"Company: {job.get('company', 'N/A')}"]
    if job.get("location"):
        parts.append(f"Location: {job['location']}")
    if job.get("description"):
        parts.append(f"Description: {job['description'][:2000]}")
    return "\n".join(parts)


def _build_match_text(match_result: dict) -> str:
    """Build match analysis text for the prompt."""
    parts = [f"Match Score: {match_result.get('match_score', 'N/A')}/100"]
    reasons = match_result.get("match_reasons", [])
    if reasons:
        parts.append(f"Match Reasons: {', '.join(reasons)}")
    missing = match_result.get("missing_skills", [])
    if missing:
        parts.append(f"Gaps to Address: {', '.join(missing)}")
    return "\n".join(parts)
