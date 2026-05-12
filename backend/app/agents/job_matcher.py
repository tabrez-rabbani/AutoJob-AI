"""
AutoJob AI — Job Matcher Agent
Compares job descriptions with user profile via LLM to calculate match scores.
"""

import json
import logging

from app.utils.llm import llm_chat

logger = logging.getLogger("autojob.agents.matcher")

MATCH_SCORING_PROMPT = """You are a job matching expert. Compare the candidate's profile with the job listing and provide a match analysis.

Return a JSON object with EXACTLY these fields:
{
  "match_score": number (0-100),
  "match_reasons": ["reason1", "reason2", "reason3"],
  "missing_skills": ["skill1", "skill2"],
  "recommendation": "apply" | "skip" | "maybe",
  "summary": "1-2 sentence match analysis"
}

Scoring guidelines:
- 80-100: Excellent match — profile strongly aligns with requirements
- 60-79: Good match — most requirements met, minor gaps
- 40-59: Partial match — some relevant skills but significant gaps
- 0-39: Poor match — not suitable for this role

Return ONLY valid JSON, no other text."""


async def match_job(profile: dict, job: dict) -> dict:
    """
    Match a job listing against the user profile.

    Args:
        profile: Structured profile from Profile Analyzer
        job: Job listing dict with title, company, location, description

    Returns:
        Match result with score, reasons, and recommendation
    """
    # Build the comparison prompt
    profile_summary = _format_profile(profile)
    job_summary = _format_job(job)

    logger.info(f"Matching: '{job.get('title', '?')}' at {job.get('company', '?')}")

    content = await llm_chat(
        messages=[
            {"role": "system", "content": MATCH_SCORING_PROMPT},
            {
                "role": "user",
                "content": f"CANDIDATE PROFILE:\n{profile_summary}\n\nJOB LISTING:\n{job_summary}",
            },
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )

    result = json.loads(content)

    # Ensure score is in valid range
    result["match_score"] = max(0, min(100, result.get("match_score", 0)))

    score = result["match_score"]
    rec = result.get("recommendation", "skip")
    logger.info(f"  Score: {score}/100 → {rec.upper()}")

    return result


def _format_profile(profile: dict) -> str:
    """Format profile dict into readable text for OpenAI."""
    parts = []
    if profile.get("name"):
        parts.append(f"Name: {profile['name']}")
    if profile.get("summary"):
        parts.append(f"Summary: {profile['summary']}")
    if profile.get("skills"):
        parts.append(f"Skills: {', '.join(profile['skills'])}")
    if profile.get("technologies"):
        parts.append(f"Technologies: {', '.join(profile['technologies'])}")
    if profile.get("experience_years"):
        parts.append(f"Experience: {profile['experience_years']} years")
    if profile.get("preferred_roles"):
        parts.append(f"Preferred Roles: {', '.join(profile['preferred_roles'])}")
    if profile.get("education"):
        parts.append(f"Education: {profile['education']}")

    return "\n".join(parts) if parts else "No profile data available"


def _format_job(job: dict) -> str:
    """Format job dict into readable text for OpenAI."""
    parts = []
    if job.get("title"):
        parts.append(f"Title: {job['title']}")
    if job.get("company"):
        parts.append(f"Company: {job['company']}")
    if job.get("location"):
        parts.append(f"Location: {job['location']}")
    if job.get("job_type"):
        parts.append(f"Type: {job['job_type']}")
    if job.get("description"):
        parts.append(f"Description: {job['description'][:2000]}")
    else:
        # If no description, infer from title
        parts.append(f"(No detailed description available — match based on title/company)")

    return "\n".join(parts) if parts else "No job data available"
