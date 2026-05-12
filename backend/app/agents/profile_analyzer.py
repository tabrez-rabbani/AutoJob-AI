"""
AutoJob AI — Profile Analyzer Agent
Parses user resume/profile and extracts structured data via LLM.
"""

import json
import logging

from app.utils.llm import llm_chat

logger = logging.getLogger("autojob.agents.profile")

PROFILE_EXTRACTION_PROMPT = """You are a career profile analyzer. Extract structured information from the given resume or profile data.

Return a JSON object with EXACTLY these fields:
{
  "name": "Full name",
  "summary": "1-2 sentence professional summary",
  "skills": ["skill1", "skill2", ...],
  "experience_years": number,
  "current_role": "current or most recent role",
  "preferred_roles": ["role1", "role2"],
  "education": "highest degree and field",
  "technologies": ["tech1", "tech2", ...],
  "industries": ["industry1", "industry2"],
  "email": "email address found in resume (or null)",
  "phone": "phone number found in resume (or null)",
  "linkedin_url": "LinkedIn profile URL (or null)",
  "github_url": "GitHub profile URL (or null)",
  "portfolio_url": "Portfolio/personal website URL (or null)"
}

Contact info extraction guidelines:
- Look for email addresses, phone numbers, LinkedIn URLs, GitHub URLs, and portfolio/personal website URLs in the resume header/footer.
- LinkedIn URL examples: linkedin.com/in/username, www.linkedin.com/in/username
- GitHub URL examples: github.com/username
- Portfolio URL: any personal website that is NOT LinkedIn or GitHub
- Phone numbers can be in any format (with/without country code)
- If a field is not found, use null

If any field is not available, use null or empty list.
Return ONLY valid JSON, no other text."""


async def analyze_profile(profile_data: dict) -> dict:
    """
    Analyze user profile and extract structured information.

    Priority: Resume text (most complete) > Settings data (fallback)

    Args:
        profile_data: dict with keys like 'resume_text', 'skills', 'preferred_roles', etc.

    Returns:
        Structured profile dict with extracted skills, experience, etc.
    """
    resume_text = profile_data.get("resume_text", "")

    # ── PRIMARY: Use LLM to analyze full resume text ──
    if resume_text and len(resume_text.strip()) > 50:
        logger.info(f"Extracting profile from resume via LLM ({len(resume_text)} chars)...")

        content = await llm_chat(
            messages=[
                {"role": "system", "content": PROFILE_EXTRACTION_PROMPT},
                {"role": "user", "content": f"Resume:\n{resume_text}"},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        result = json.loads(content)
        logger.info(f"Profile extracted: {result.get('name', 'Unknown')} | {len(result.get('skills', []))} skills")
        return result

    # ── FALLBACK: Use Settings data if no resume text ──
    if profile_data.get("skills") or profile_data.get("preferred_roles"):
        logger.info("No resume text — using Settings profile data as fallback")
        return {
            "name": profile_data.get("full_name", "User"),
            "summary": f"{profile_data.get('full_name', 'User')} with {profile_data.get('experience_years', 0)} years experience",
            "skills": profile_data.get("skills", []),
            "experience_years": profile_data.get("experience_years", 0),
            "current_role": profile_data.get("preferred_roles", ["Developer"])[0] if profile_data.get("preferred_roles") else "",
            "preferred_roles": profile_data.get("preferred_roles", []),
            "education": None,
            "technologies": profile_data.get("skills", []),
            "industries": [],
        }

    # ── LAST RESORT: No resume, no Settings ──
    logger.warning("No resume text AND no Settings data — AI matching will be generic")
    return {
        "name": profile_data.get("full_name", "User"),
        "skills": [],
        "experience_years": 0,
        "preferred_roles": [],
        "technologies": [],
        "industries": [],
        "summary": "",
        "current_role": "",
        "education": None,
    }
