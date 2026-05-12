"""
AutoJob AI — Agents API
Endpoints for AI-powered job analysis and matching.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.job import Job
from app.models.user import User
from app.schemas.agent import AnalyzeJobsRequest, AnalyzeJobsResponse, JobAnalysisResult
from app.agents.orchestrator import run_job_analysis, MATCH_THRESHOLD
from app.utils.auth import get_current_user

logger = logging.getLogger("autojob.api.agents")

router = APIRouter(tags=["Agents"])


@router.post("/agents/analyze-jobs", response_model=AnalyzeJobsResponse)
async def analyze_jobs(
    request: AnalyzeJobsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Analyze scraped jobs using the AI agent pipeline.

    Workflow:
    1. Fetch jobs from database
    2. Analyze user profile
    3. Score each job (0-100) via AI
    4. Generate tailored resume + cover letter for qualified jobs
    """
    logger.info(f"Agent analysis requested by '{request.full_name}' — max {request.max_jobs} jobs")

    # Step 1: Fetch jobs from database
    result = await db.execute(
        select(Job)
        .where(Job.is_active == True)
        .order_by(Job.scraped_at.desc())
        .limit(request.max_jobs)
    )
    db_jobs = result.scalars().all()

    if not db_jobs:
        return AnalyzeJobsResponse(
            status="error",
            message="No jobs found in the database. Run a job search first.",
        )

    # Convert DB models to dicts for the pipeline
    jobs_data = [
        {
            "id": str(j.id),
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "description": j.description,
            "job_type": j.job_type,
            "apply_url": j.apply_url,
        }
        for j in db_jobs
    ]

    # Build user profile
    user_profile = {
        "full_name": request.full_name,
        "skills": request.skills,
        "preferred_roles": request.preferred_roles,
        "experience_years": request.experience_years,
        "resume_text": request.resume_text,
    }

    # Step 2: Run the AI pipeline
    try:
        pipeline_result = await run_job_analysis(user_profile, jobs_data)
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        raise HTTPException(status_code=500, detail=f"AI pipeline failed: {e}")

    # Step 3: Build response
    results = pipeline_result.get("results", [])
    summary = pipeline_result.get("summary", {})

    return AnalyzeJobsResponse(
        status="success",
        message=f"Analyzed {summary.get('total_jobs', 0)} jobs — {summary.get('qualified', 0)} qualified.",
        total_jobs=summary.get("total_jobs", 0),
        qualified=summary.get("qualified", 0),
        skipped=summary.get("skipped", 0),
        average_score=summary.get("average_score", 0),
        results=[
            JobAnalysisResult(
                job_id=r.get("job_id", ""),
                job_title=r.get("job_title", ""),
                company=r.get("company", ""),
                match_score=r.get("match_score", 0),
                recommendation=r.get("recommendation", "skip"),
                match_reasons=r.get("match_reasons", []),
                missing_skills=r.get("missing_skills", []),
                match_summary=r.get("match_summary", ""),
                tailored_summary=r.get("tailored_summary"),
                cover_letter=r.get("cover_letter"),
                key_highlights=r.get("key_highlights", []),
            )
            for r in results
        ],
        errors=pipeline_result.get("errors", []),
    )
