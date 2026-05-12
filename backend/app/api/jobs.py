"""
AutoJob AI — Jobs API
Endpoints for triggering job search and retrieving stored jobs.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.job import JobSearchRequest, JobSearchResponse, JobListResponse, JobResponse
from app.services.job_service import save_scraped_jobs, get_jobs, get_job_count
from app.automation.adapters.linkedin import LinkedInAdapter
from app.utils.auth import get_current_user

logger = logging.getLogger("autojob.api.jobs")

router = APIRouter(tags=["Jobs"])


@router.post("/jobs/search", response_model=JobSearchResponse)
async def trigger_job_search(
    request: JobSearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Trigger a LinkedIn job search.
    Logs into LinkedIn, searches for jobs, and saves results to the database.

    ⚠️ This runs Playwright in the current process. In production,
    this should be dispatched as a Celery background task.
    """
    adapter = LinkedInAdapter(headless=False)  # Visible browser — LinkedIn blocks headless

    try:
        # Step 1: Login
        logger.info(f"Starting job search: '{request.keywords}'")
        login_success = await adapter.login({
            "email": request.linkedin_email,
            "password": request.linkedin_password,
        })

        if not login_success:
            return JobSearchResponse(
                status="error",
                message="LinkedIn login failed. Check credentials or try again later.",
            )

        # Step 2: Search
        job_listings = await adapter.search_jobs(
            keywords=request.keywords,
            location=request.location,
            max_results=request.max_results,
        )

        if not job_listings:
            return JobSearchResponse(
                status="success",
                message="Search completed but no jobs found.",
            )

        # Step 3: Save to database
        save_result = await save_scraped_jobs(db, job_listings)

        # Step 4: Return results
        return JobSearchResponse(
            status="success",
            message=f"Found {len(job_listings)} jobs, saved {save_result['saved']} new jobs.",
            jobs_found=len(job_listings),
            jobs_saved=save_result["saved"],
            jobs_skipped=save_result["skipped"],
            jobs=[
                JobResponse(
                    id="",
                    platform=j.platform,
                    platform_job_id=j.platform_job_id,
                    title=j.title,
                    company=j.company,
                    location=j.location,
                    description=j.description,
                    salary_range=j.salary_range,
                    job_type=j.job_type,
                    apply_url=j.apply_url,
                    scraped_at=None,
                )
                for j in job_listings
            ],
        )

    except Exception as e:
        logger.error(f"Job search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        await adapter.close()


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    platform: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List stored jobs from the database.
    Optional filter by platform (linkedin, naukri, indeed).
    """
    jobs = await get_jobs(db, platform=platform, limit=limit, offset=offset)
    total = await get_job_count(db, platform=platform)

    return JobListResponse(
        count=len(jobs),
        total=total,
        jobs=[
            JobResponse(
                id=str(j.id),
                platform=j.platform,
                platform_job_id=j.platform_job_id,
                title=j.title,
                company=j.company,
                location=j.location,
                description=j.description,
                salary_range=j.salary_range,
                job_type=j.job_type,
                apply_url=j.apply_url,
                scraped_at=j.scraped_at,
            )
            for j in jobs
        ],
    )
