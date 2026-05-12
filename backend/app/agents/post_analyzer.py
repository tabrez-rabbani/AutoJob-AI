"""
AutoJob AI — Post Analyzer Agent
Uses LLM to classify LinkedIn feed posts as job-related or not.
Extracts job role and recruiter email from job posts.
"""

import json
import logging

from app.utils.llm import llm_chat

logger = logging.getLogger("autojob.agents.post_analyzer")

POST_ANALYZER_PROMPT = """You are a LinkedIn post analyst. Your job is to determine if a LinkedIn feed post is about hiring/job openings.

Analyze the post text and return a JSON object with EXACTLY these fields:
{
  "is_job_post": true/false,
  "confidence": 0.0-1.0,
  "role": "Job title if found, else null",
  "company": "Company name if mentioned, else null",
  "email": "Contact email if found in the post, else null",
  "location": "Job location if mentioned, else null",
  "summary": "One line summary of the job if it is a job post, else null"
}

Guidelines:
- A job post typically contains words like: hiring, looking for, opening, position, vacancy, join our team, send resume, apply, DM, drop your CV, walk-in
- Extract the EXACT email address if present (look for patterns like name@company.com)
- If the post contains both a job description AND an email, set is_job_post to true
- If the post is about career advice, promotions, or general updates — it is NOT a job post
- Be strict: only mark as job post if it's clearly about an active opening
- Return ONLY valid JSON, no other text."""


async def analyze_post(post_text: str, author: str = "") -> dict:
    """
    Analyze a single LinkedIn post to determine if it's a job posting.

    Args:
        post_text: The full text content of the post
        author: Name of the post author (for context)

    Returns:
        Analysis dict with is_job_post, role, email, company, etc.
    """
    if not post_text or len(post_text) < 20:
        return {"is_job_post": False, "confidence": 0, "email": None, "role": None}

    try:
        user_content = f"Post Author: {author}\n\nPost Text:\n{post_text[:3000]}"

        content = await llm_chat(
            messages=[
                {"role": "system", "content": POST_ANALYZER_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )

        result = json.loads(content)

        is_job = result.get("is_job_post", False)
        email = result.get("email")
        role = result.get("role")

        if is_job and email:
            logger.info(f"  ✅ Job post found: '{role}' | Email: {email}")
        elif is_job:
            logger.info(f"  📋 Job post found: '{role}' (no email)")
        else:
            logger.debug(f"  ⏭️ Not a job post (confidence: {result.get('confidence', 0):.2f})")

        return result

    except Exception as e:
        logger.error(f"Post analysis failed: {e}")
        return {"is_job_post": False, "confidence": 0, "email": None, "role": None, "error": str(e)}


async def analyze_posts_batch(posts: list[dict]) -> list[dict]:
    """
    Analyze a batch of posts. Returns only job posts with emails.

    Args:
        posts: List of dicts with 'text' and 'author' keys

    Returns:
        Filtered list of analysis results (only job posts with emails)
    """
    import asyncio

    results = []

    for i, post in enumerate(posts):
        # Rate limit: small delay between LLM calls
        if i > 0:
            await asyncio.sleep(1.5)

        analysis = await analyze_post(
            post_text=post.get("text", ""),
            author=post.get("author", ""),
        )

        # Only keep job posts that have an email
        if analysis.get("is_job_post") and analysis.get("email"):
            analysis["original_post"] = post
            results.append(analysis)

    logger.info(f"📊 Analyzed {len(posts)} posts → {len(results)} actionable job posts with emails")
    return results
