"""
AutoJob AI — LangGraph Orchestrator
Connects all agents into a directed workflow for job analysis.

Flow:
  START → analyze_profile → match_jobs → tailor_resumes → END
                                ↓
          For each job: score >= threshold → tailor resume
                        score < threshold  → skip (no tailoring)
"""

import asyncio
import logging
from typing import TypedDict

from langgraph.graph import StateGraph, END

from app.agents.profile_analyzer import analyze_profile
from app.agents.job_matcher import match_job
from app.agents.resume_tailor import tailor_resume

logger = logging.getLogger("autojob.agents.orchestrator")

# Match score threshold — jobs below this are skipped
MATCH_THRESHOLD = 60


# ── State Definition ─────────────────────────────────

class AgentState(TypedDict):
    """State passed between nodes in the LangGraph workflow."""
    # Input
    user_profile: dict      # Raw profile from DB or request
    jobs: list[dict]        # Jobs to analyze
    skip_tailoring: bool    # If True, skip resume tailoring (e.g. Naukri doesn't need cover letters)

    # Intermediate
    analyzed_profile: dict  # Structured profile from Profile Analyzer
    match_results: list[dict]  # Match scores for each job

    # Output
    results: list[dict]     # Final results with scores + tailored content
    errors: list[str]       # Any errors during processing


# ── Node Functions ───────────────────────────────────

async def node_analyze_profile(state: AgentState) -> dict:
    """Node 1: Analyze user profile."""
    logger.info("═══ Step 1: Analyzing Profile ═══")

    try:
        profile = await analyze_profile(state["user_profile"])
        return {"analyzed_profile": profile, "errors": state.get("errors", [])}
    except Exception as e:
        logger.error(f"Profile analysis failed: {e}")
        return {
            "analyzed_profile": state["user_profile"],
            "errors": state.get("errors", []) + [f"Profile analysis: {e}"],
        }


async def node_match_jobs(state: AgentState) -> dict:
    """Node 2: Match each job against the profile."""
    logger.info("═══ Step 2: Matching Jobs ═══")

    profile = state.get("analyzed_profile", state["user_profile"])
    jobs = state.get("jobs", [])
    match_results = []
    errors = list(state.get("errors", []))

    for i, job in enumerate(jobs):
        try:
            # Rate limit: delay between API calls
            if i > 0:
                await asyncio.sleep(2)
            result = await match_job(profile, job)
            match_results.append({
                "job_index": i,
                "job_id": job.get("id", ""),
                "job_title": job.get("title", ""),
                "company": job.get("company", ""),
                **result,
            })
        except Exception as e:
            logger.error(f"Matching failed for job {i}: {e}")
            errors.append(f"Job matching [{job.get('title', '?')}]: {e}")
            match_results.append({
                "job_index": i,
                "job_id": job.get("id", ""),
                "job_title": job.get("title", ""),
                "company": job.get("company", ""),
                "match_score": 0,
                "recommendation": "error",
                "summary": f"Error: {e}",
                "match_reasons": [],
                "missing_skills": [],
            })

    logger.info(f"Matched {len(match_results)} jobs")
    return {"match_results": match_results, "errors": errors}


async def node_tailor_resumes(state: AgentState) -> dict:
    """Node 3: Tailor resumes for qualified jobs (score >= threshold).
    Skipped entirely for platforms like Naukri that don't need cover letters."""

    profile = state.get("analyzed_profile", state["user_profile"])
    jobs = state.get("jobs", [])
    match_results = state.get("match_results", [])
    final_results = []
    errors = list(state.get("errors", []))
    skip_tailoring = state.get("skip_tailoring", False)

    qualified = sum(1 for m in match_results if m.get("match_score", 0) >= MATCH_THRESHOLD)

    if skip_tailoring:
        logger.info(f"═══ Step 3: Skipping Resume Tailoring (platform doesn't need it) ═══")
        logger.info(f"  {qualified}/{len(match_results)} jobs qualify (threshold: {MATCH_THRESHOLD})")
        # Just pass through match results without tailoring
        for match in match_results:
            final_results.append({
                "job_id": match.get("job_id", ""),
                "job_title": match.get("job_title", ""),
                "company": match.get("company", ""),
                "match_score": match.get("match_score", 0),
                "recommendation": match.get("recommendation", "skip"),
                "match_reasons": match.get("match_reasons", []),
                "missing_skills": match.get("missing_skills", []),
                "match_summary": match.get("summary", ""),
                "tailored_summary": None,
                "cover_letter": None,
                "key_highlights": [],
            })
        return {"results": final_results, "errors": errors}

    logger.info("═══ Step 3: Tailoring Resumes ═══")
    logger.info(f"  {qualified}/{len(match_results)} jobs qualify (threshold: {MATCH_THRESHOLD})")

    for match in match_results:
        score = match.get("match_score", 0)
        job_idx = match.get("job_index", 0)
        job = jobs[job_idx] if job_idx < len(jobs) else {}

        result_entry = {
            "job_id": match.get("job_id", ""),
            "job_title": match.get("job_title", ""),
            "company": match.get("company", ""),
            "match_score": score,
            "recommendation": match.get("recommendation", "skip"),
            "match_reasons": match.get("match_reasons", []),
            "missing_skills": match.get("missing_skills", []),
            "match_summary": match.get("summary", ""),
            "tailored_summary": None,
            "cover_letter": None,
            "key_highlights": [],
        }

        # Only tailor resume for qualified jobs
        if score >= MATCH_THRESHOLD:
            try:
                # Rate limit: delay between API calls
                await asyncio.sleep(2)
                tailored = await tailor_resume(profile, job, match)
                result_entry["tailored_summary"] = tailored.get("tailored_summary")
                result_entry["cover_letter"] = tailored.get("cover_letter")
                result_entry["key_highlights"] = tailored.get("key_highlights", [])
            except Exception as e:
                logger.error(f"Resume tailoring failed for '{match.get('job_title')}': {e}")
                errors.append(f"Resume tailor [{match.get('job_title', '?')}]: {e}")
        else:
            logger.info(f"  Skipping resume tailor for '{match.get('job_title')}' (score: {score})")

        final_results.append(result_entry)

    return {"results": final_results, "errors": errors}


# ── Graph Builder ────────────────────────────────────

def build_analysis_workflow() -> StateGraph:
    """Build the LangGraph workflow for job analysis."""
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("analyze_profile", node_analyze_profile)
    workflow.add_node("match_jobs", node_match_jobs)
    workflow.add_node("tailor_resumes", node_tailor_resumes)

    # Set flow: start → profile → match → tailor → end
    workflow.set_entry_point("analyze_profile")
    workflow.add_edge("analyze_profile", "match_jobs")
    workflow.add_edge("match_jobs", "tailor_resumes")
    workflow.add_edge("tailor_resumes", END)

    return workflow.compile()


# Pre-compiled workflow (reusable)
analysis_pipeline = build_analysis_workflow()


async def run_job_analysis(user_profile: dict, jobs: list[dict], skip_tailoring: bool = False) -> dict:
    """
    Run the full job analysis pipeline.

    Args:
        user_profile: User profile data
        jobs: List of job dicts to analyze
        skip_tailoring: If True, skip resume tailoring step (for platforms like Naukri
                        that don't need cover letters)

    Returns:
        Final state with results, match scores, and tailored content
    """
    logger.info(f"🚀 Starting job analysis pipeline: {len(jobs)} jobs (tailoring: {'OFF' if skip_tailoring else 'ON'})")

    initial_state: AgentState = {
        "user_profile": user_profile,
        "jobs": jobs,
        "skip_tailoring": skip_tailoring,
        "analyzed_profile": {},
        "match_results": [],
        "results": [],
        "errors": [],
    }

    final_state = await analysis_pipeline.ainvoke(initial_state)

    # Summary
    results = final_state.get("results", [])
    qualified = sum(1 for r in results if r.get("match_score", 0) >= MATCH_THRESHOLD)
    avg_score = sum(r.get("match_score", 0) for r in results) / max(len(results), 1)

    logger.info(f"✅ Analysis complete: {len(results)} jobs | {qualified} qualified | avg score: {avg_score:.0f}")

    return {
        "results": results,
        "errors": final_state.get("errors", []),
        "summary": {
            "total_jobs": len(results),
            "qualified": qualified,
            "skipped": len(results) - qualified,
            "average_score": round(avg_score, 1),
        },
    }
