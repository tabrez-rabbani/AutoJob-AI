"""
AutoJob AI — Email Tailor Agent
Generates professional email-specific cover letters with subject lines.
Different from resume_tailor.py — optimized for direct email to recruiters.
"""

import json
import logging

from app.utils.llm import llm_chat

logger = logging.getLogger("autojob.agents.email_tailor")

EMAIL_TAILOR_PROMPT = """You are a professional career coach writing an email to a recruiter/HR person who posted a job on LinkedIn.

The candidate saw a LinkedIn post about a job opening and wants to apply via email. Write a professional yet warm email.

Return a JSON object with EXACTLY these fields:
{
  "subject": "Email subject line (concise, professional, mentions the role)",
  "body": "Full email body with greeting, 2-3 paragraphs, and sign-off"
}

Email writing guidelines:
- Subject should be clear: "Application for [Role] — [Candidate Name]"
- Start with "Dear [Recruiter Name]" if name is known, else "Dear Hiring Manager"
- Opening: Mention you saw their LinkedIn post about the opening
- Middle: 2-3 sentences about why you're a good fit (reference specific skills matching the role)
- Closing: Express enthusiasm, mention resume is attached, request for a conversation
- Sign off with the candidate's full name
- CRITICAL: You must format the email with proper paragraph breaks using `\n\n` between the greeting, each body paragraph, and the sign-off.
- After the name, add contact details on separate lines using `\n` (only include what's available):
  - Phone number (if provided)
  - LinkedIn URL (if provided)
  - GitHub URL (if provided)
  - Portfolio URL (if provided)
- Keep the TOTAL email under 180 words — recruiters scan fast
- Sound human and genuine, NOT like ChatGPT. No buzzwords like "synergy" or "leverage"
- Do NOT use phrases like "I am writing to express my interest" — be direct and natural

Return ONLY valid JSON, no other text."""


async def tailor_email(
    user_profile: dict,
    job_info: dict,
    recruiter_name: str = "",
) -> dict:
    """
    Generate a tailored email (subject + body) for a job post found in the feed.

    Args:
        user_profile: Candidate's profile data
        job_info: Job details extracted from the post (role, company, description)
        recruiter_name: Name of the person who posted (if known)

    Returns:
        {"subject": "...", "body": "..."}
    """
    role = job_info.get("role", "the position")
    company = job_info.get("company", "your company")
    logger.info(f"Crafting email for: '{role}' at {company}")

    profile_text = _build_profile_text(user_profile)
    job_text = _build_job_text(job_info)

    user_content = (
        f"CANDIDATE PROFILE:\n{profile_text}\n\n"
        f"JOB DETAILS FROM LINKEDIN POST:\n{job_text}\n\n"
        f"RECRUITER/POSTER NAME: {recruiter_name or 'Unknown'}\n"
    )

    try:
        content = await llm_chat(
            messages=[
                {"role": "system", "content": EMAIL_TAILOR_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.5,
            response_format={"type": "json_object"},
        )

        result = json.loads(content)
        logger.info(f"  Email crafted — Subject: {result.get('subject', '?')[:60]}")
        return result

    except Exception as e:
        logger.error(f"Email tailoring failed: {e}")
        # Fallback: generate a basic email
        name = user_profile.get("name", user_profile.get("full_name", "Candidate"))
        return {
            "subject": f"Application for {role} — {name}",
            "body": (
                f"Dear {recruiter_name or 'Hiring Manager'},\n\n"
                f"I saw your LinkedIn post about the {role} opening at {company} "
                f"and I'd love to apply. I've attached my resume for your review.\n\n"
                f"I look forward to the opportunity to discuss how I can contribute to your team.\n\n"
                f"Best regards,\n{name}"
            ),
        }


def _build_profile_text(profile: dict) -> str:
    """Build profile text for the prompt."""
    parts = [f"Name: {profile.get('name', profile.get('full_name', 'Candidate'))}"]
    if profile.get("summary"):
        parts.append(f"Summary: {profile['summary']}")
    if profile.get("skills"):
        skills = profile["skills"]
        if isinstance(skills, list):
            skills = ", ".join(skills)
        parts.append(f"Skills: {skills}")
    if profile.get("experience_years"):
        parts.append(f"Experience: {profile['experience_years']} years")
    if profile.get("preferred_roles"):
        roles = profile["preferred_roles"]
        if isinstance(roles, list):
            roles = ", ".join(roles)
        parts.append(f"Target Roles: {roles}")
    # Contact info for signature
    if profile.get("phone"):
        parts.append(f"Phone: {profile['phone']}")
    if profile.get("linkedin_url"):
        parts.append(f"LinkedIn: {profile['linkedin_url']}")
    if profile.get("github_url"):
        parts.append(f"GitHub: {profile['github_url']}")
    if profile.get("portfolio_url"):
        parts.append(f"Portfolio: {profile['portfolio_url']}")
    return "\n".join(parts)


def _build_job_text(job_info: dict) -> str:
    """Build job info text for the prompt."""
    parts = [f"Role: {job_info.get('role', 'N/A')}"]
    if job_info.get("company"):
        parts.append(f"Company: {job_info['company']}")
    if job_info.get("location"):
        parts.append(f"Location: {job_info['location']}")
    if job_info.get("summary"):
        parts.append(f"Description: {job_info['summary']}")
    if job_info.get("original_post", {}).get("text"):
        # Include first 500 chars of the original post for more context
        parts.append(f"Original Post: {job_info['original_post']['text'][:500]}")
    return "\n".join(parts)
