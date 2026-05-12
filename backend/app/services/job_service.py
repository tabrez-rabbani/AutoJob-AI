"""
AutoJob AI — Job Service
Business logic for saving and retrieving jobs from the database.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.automation.adapters.base import JobListing
from app.models.job import Job

logger = logging.getLogger("autojob.services.job")


async def save_scraped_jobs(
    db: AsyncSession,
    jobs: list[JobListing],
) -> dict:
    """
    Save scraped job listings to the database.
    Skips duplicates based on platform + platform_job_id.

    Returns:
        {"saved": int, "skipped": int, "total": int}
    """
    saved = 0
    skipped = 0

    for job_listing in jobs:
        # Check for existing job (avoid duplicates)
        existing = await db.execute(
            select(Job).where(
                Job.platform == job_listing.platform,
                Job.platform_job_id == job_listing.platform_job_id,
            )
        )

        existing_job = existing.scalar_one_or_none()
        if existing_job:
            # If the job exists but lacks a description/salary, update it
            updated = False
            if not existing_job.description and job_listing.description:
                existing_job.description = job_listing.description
                updated = True
            if not existing_job.salary_range and job_listing.salary_range:
                existing_job.salary_range = job_listing.salary_range
                updated = True
            
            if updated:
                logger.debug(f"Updated missing details for existing job: {job_listing.title}")
                
            skipped += 1
            continue

        # Create new job record
        job = Job(
            platform=job_listing.platform,
            platform_job_id=job_listing.platform_job_id,
            title=job_listing.title,
            company=job_listing.company,
            location=job_listing.location,
            description=job_listing.description,
            salary_range=job_listing.salary_range,
            job_type=job_listing.job_type,
            apply_url=job_listing.apply_url,
            posted_date=None,
            scraped_at=datetime.now(timezone.utc),
            is_active=True,
        )

        db.add(job)
        saved += 1

    if saved > 0:
        await db.flush()

    result = {"saved": saved, "skipped": skipped, "total": len(jobs)}
    logger.info(f"Jobs saved: {saved} new, {skipped} duplicates, {len(jobs)} total")
    return result


async def get_jobs(
    db: AsyncSession,
    platform: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Job]:
    """Get jobs from database with optional platform filter."""
    query = select(Job).where(Job.is_active == True).order_by(Job.scraped_at.desc())

    if platform:
        query = query.where(Job.platform == platform)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_job_count(db: AsyncSession, platform: str | None = None) -> int:
    """Get total count of active jobs."""
    from sqlalchemy import func

    query = select(func.count(Job.id)).where(Job.is_active == True)
    if platform:
        query = query.where(Job.platform == platform)

    result = await db.execute(query)
    return result.scalar() or 0
