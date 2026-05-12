"""
AutoJob AI — Dashboard API
Endpoints for user dashboard stats, job listings, and application tracking.
All endpoints require JWT authentication.
"""

import logging
from typing import Optional
from datetime import datetime, timedelta, date

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.job import Job
from app.models.application import Application, ApplicationStatus
from app.models.user import User
from app.utils.auth import get_current_user

logger = logging.getLogger("autojob.api.dashboard")

router = APIRouter(tags=["Dashboard"])


# ── Response Models ──────────────────────────────────

class DashboardStats(BaseModel):
    """Overview stats for the dashboard."""
    total_scraped: int = 0
    total_qualified: int = 0
    total_applied: int = 0
    total_external: int = 0
    total_skipped: int = 0
    total_failed: int = 0


class DashboardJob(BaseModel):
    """Job listing for the dashboard."""
    id: str
    title: str
    company: str
    location: str | None
    job_type: str | None
    apply_url: str
    application_status: str | None = None
    match_score: float | None = None
    scraped_at: str | None = None


class DashboardJobsResponse(BaseModel):
    """Response for dashboard jobs listing."""
    count: int
    jobs: list[DashboardJob]


class JobDetailResponse(BaseModel):
    """Full detail response for a single job."""
    id: str
    title: str
    company: str
    location: str | None
    description: str | None
    salary_range: str | None
    job_type: str | None
    platform: str
    platform_job_id: str
    apply_url: str
    posted_date: str | None
    scraped_at: str | None
    is_active: bool
    # Application data
    application_status: str | None = None
    match_score: float | None = None
    applied_at: str | None = None
    application_notes: str | None = None


class DashboardApplication(BaseModel):
    """Application entry for the dashboard."""
    id: str
    job_id: str
    job_title: str
    company: str
    status: str
    match_score: float | None
    applied_at: str | None
    notes: str | None


class DashboardAppliedResponse(BaseModel):
    """Response for applied jobs listing."""
    count: int
    applications: list[DashboardApplication]


# ── Endpoints ────────────────────────────────────────

@router.get("/dashboard/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get dashboard overview stats for the current user (fully user-scoped)."""

    # Total scraped = total unique jobs this user has any application record for
    total_scraped = await db.execute(
        select(func.count(func.distinct(Application.job_id)))
        .where(Application.user_id == user.id)
    )

    # User's application stats by status
    app_stats = {}
    for status_val in [
        ApplicationStatus.APPLIED,
        ApplicationStatus.EXTERNAL_APPLY,
        ApplicationStatus.SKIPPED,
        ApplicationStatus.FAILED,
        ApplicationStatus.QUEUED,
    ]:
        count = await db.execute(
            select(func.count(Application.id))
            .where(Application.user_id == user.id)
            .where(Application.status == status_val.value)
        )
        app_stats[status_val.value] = count.scalar() or 0

    # Total qualified = applied + external + queued
    qualified = (
        app_stats.get("applied", 0)
        + app_stats.get("external_apply", 0)
        + app_stats.get("queued", 0)
    )

    return DashboardStats(
        total_scraped=total_scraped.scalar() or 0,
        total_qualified=qualified,
        total_applied=app_stats.get("applied", 0),
        total_external=app_stats.get("external_apply", 0),
        total_skipped=app_stats.get("skipped", 0),
        total_failed=app_stats.get("failed", 0),
    )


@router.get("/dashboard/jobs", response_model=DashboardJobsResponse)
async def get_dashboard_jobs(
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = Query(None, description="Search by job title or company"),
    status: Optional[str] = Query(None, description="Filter by application status"),
    min_score: Optional[float] = Query(None, description="Minimum match score"),
    max_score: Optional[float] = Query(None, description="Maximum match score"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get jobs that this user has interacted with (user-scoped), with optional filters."""

    # Base query conditions
    base_conditions = [
        Application.user_id == user.id,
        Job.is_active == True,
    ]

    # Search filter (title or company)
    if search:
        search_term = f"%{search}%"
        base_conditions.append(
            or_(Job.title.ilike(search_term), Job.company.ilike(search_term))
        )

    # Status filter
    if status:
        base_conditions.append(Application.status == status)

    # Score range filters
    if min_score is not None:
        base_conditions.append(Application.match_score >= min_score)
    if max_score is not None:
        base_conditions.append(Application.match_score <= max_score)

    # Date range filters
    if date_from:
        try:
            base_conditions.append(Job.scraped_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            base_conditions.append(Job.scraped_at <= datetime.fromisoformat(date_to + "T23:59:59"))
        except ValueError:
            pass

    # Get total count
    count_query = (
        select(func.count(Job.id))
        .join(Application, Application.job_id == Job.id)
        .where(*base_conditions)
    )
    total_count_result = await db.execute(count_query)
    total_count = total_count_result.scalar() or 0

    # Fetch paginated jobs
    result = await db.execute(
        select(Job)
        .join(Application, Application.job_id == Job.id)
        .where(*base_conditions)
        .order_by(Job.scraped_at.desc())
        .limit(limit)
        .offset(offset)
    )
    jobs = result.scalars().unique().all()

    # Fetch user's applications for these jobs
    job_ids = [j.id for j in jobs]
    app_result = await db.execute(
        select(Application)
        .where(Application.user_id == user.id)
        .where(Application.job_id.in_(job_ids))
    ) if job_ids else None
    apps_by_job = {a.job_id: a for a in (app_result.scalars().all() if app_result else [])}

    dashboard_jobs = []
    for job in jobs:
        app = apps_by_job.get(job.id)
        dashboard_jobs.append(DashboardJob(
            id=str(job.id),
            title=job.title,
            company=job.company,
            location=job.location,
            job_type=job.job_type,
            apply_url=job.apply_url,
            application_status=app.status if app else None,
            match_score=app.match_score if app else None,
            scraped_at=job.scraped_at.isoformat() if job.scraped_at else None,
        ))


    return DashboardJobsResponse(count=total_count, jobs=dashboard_jobs)


@router.get("/dashboard/jobs/{job_id}", response_model=JobDetailResponse)
async def get_job_detail(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full details for a single job."""
    import uuid as _uuid
    try:
        parsed_id = _uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID")

    result = await db.execute(select(Job).where(Job.id == parsed_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Get user's application for this job
    app_result = await db.execute(
        select(Application).where(
            Application.job_id == job.id,
            Application.user_id == user.id,
        )
    )
    app = app_result.scalar_one_or_none()

    return JobDetailResponse(
        id=str(job.id),
        title=job.title,
        company=job.company,
        location=job.location,
        description=job.description,
        salary_range=job.salary_range,
        job_type=job.job_type,
        platform=job.platform,
        platform_job_id=job.platform_job_id,
        apply_url=job.apply_url,
        posted_date=job.posted_date.isoformat() if job.posted_date else None,
        scraped_at=job.scraped_at.isoformat() if job.scraped_at else None,
        is_active=job.is_active,
        application_status=app.status if app else None,
        match_score=app.match_score if app else None,
        applied_at=app.applied_at.isoformat() if app and app.applied_at else None,
        application_notes=app.notes if app else None,
    )


@router.get("/dashboard/qualified", response_model=DashboardJobsResponse)
async def get_qualified_jobs(
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None),
    max_score: Optional[float] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get qualified jobs with optional filters."""
    # Fetch all jobs the user has interacted with
    base_conditions = [
        Application.user_id == user.id,
        Job.is_active == True,
    ]

    if search:
        search_term = f"%{search}%"
        base_conditions.append(
            or_(Job.title.ilike(search_term), Job.company.ilike(search_term))
        )
    if date_from:
        try:
            base_conditions.append(Job.scraped_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            base_conditions.append(Job.scraped_at <= datetime.fromisoformat(date_to + "T23:59:59"))
        except ValueError:
            pass

    result = await db.execute(
        select(Job)
        .join(Application, Application.job_id == Job.id)
        .where(*base_conditions)
        .order_by(Job.scraped_at.desc())
    )
    all_jobs = result.scalars().unique().all()
    
    job_ids = [j.id for j in all_jobs]
    app_result = await db.execute(
        select(Application)
        .where(Application.user_id == user.id)
        .where(Application.job_id.in_(job_ids))
    ) if job_ids else None
    apps_by_job = {a.job_id: a for a in (app_result.scalars().all() if app_result else [])}

    qualified_dashboard_jobs = []
    for job in all_jobs:
        app = apps_by_job.get(job.id)
        if not app:
            continue
            
        score = app.match_score or 0
        if score >= 70 or app.status in ["qualified", "applied", "external_apply", "queued"]:
            # Apply additional user filters
            if status and app.status != status:
                continue
            if min_score is not None and score < min_score:
                continue
            if max_score is not None and score > max_score:
                continue

            qualified_dashboard_jobs.append(DashboardJob(
                id=str(job.id),
                title=job.title,
                company=job.company,
                location=job.location,
                job_type=job.job_type,
                apply_url=job.apply_url,
                application_status=app.status,
                match_score=app.match_score,
                scraped_at=job.scraped_at.isoformat() if job.scraped_at else None,
            ))

    total_count = len(qualified_dashboard_jobs)
    paginated_jobs = qualified_dashboard_jobs[offset : offset + limit]

    return DashboardJobsResponse(count=total_count, jobs=paginated_jobs)


@router.get("/dashboard/applied", response_model=DashboardAppliedResponse)
async def get_applied_jobs(
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None),
    max_score: Optional[float] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all applications for the current user with optional filters."""

    base_conditions = [Application.user_id == user.id]

    if status:
        base_conditions.append(Application.status == status)
    if min_score is not None:
        base_conditions.append(Application.match_score >= min_score)
    if max_score is not None:
        base_conditions.append(Application.match_score <= max_score)
    if date_from:
        try:
            base_conditions.append(Application.created_at >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            base_conditions.append(Application.created_at <= datetime.fromisoformat(date_to + "T23:59:59"))
        except ValueError:
            pass

    # For search, we need to join with Job
    join_needed = bool(search)

    if search:
        search_term = f"%{search}%"

    # Count query
    count_q = select(func.count(Application.id)).where(*base_conditions)
    if join_needed:
        count_q = count_q.join(Job, Job.id == Application.job_id).where(
            or_(Job.title.ilike(search_term), Job.company.ilike(search_term))
        )
    total_count = (await db.execute(count_q)).scalar() or 0

    # Data query
    data_q = select(Application).where(*base_conditions).order_by(Application.created_at.desc())
    if join_needed:
        data_q = data_q.join(Job, Job.id == Application.job_id).where(
            or_(Job.title.ilike(search_term), Job.company.ilike(search_term))
        )
    data_q = data_q.limit(limit).offset(offset)
    applications = (await db.execute(data_q)).scalars().all()

    items = []
    for app in applications:
        job_result = await db.execute(select(Job).where(Job.id == app.job_id))
        job = job_result.scalar_one_or_none()

        items.append(DashboardApplication(
            id=str(app.id),
            job_id=str(app.job_id),
            job_title=job.title if job else "Unknown",
            company=job.company if job else "Unknown",
            status=app.status,
            match_score=app.match_score,
            applied_at=app.applied_at.isoformat() if app.applied_at else None,
            notes=app.notes,
        ))

    return DashboardAppliedResponse(count=total_count, applications=items)


# ── Analytics Models ─────────────────────────────────

class DailyActivity(BaseModel):
    """One day's application count."""
    date: str  # ISO date string, e.g. "2026-04-14"
    count: int


class SourceCount(BaseModel):
    """Application count per platform source."""
    platform: str
    count: int


class AnalyticsResponse(BaseModel):
    """Combined analytics data for dashboard charts."""
    daily_activity: list[DailyActivity]   # Last 7 days
    source_distribution: list[SourceCount] # Per-platform counts
    heatmap: list[DailyActivity]           # Last 365 days


@router.get("/dashboard/analytics", response_model=AnalyticsResponse)
async def get_dashboard_analytics(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get analytics data for dashboard charts (activity, sources, heatmap)."""

    today = date.today()

    # ── 1. Daily Activity (Last 7 days) ──
    seven_days_ago = datetime.combine(today - timedelta(days=6), datetime.min.time())
    daily_rows = await db.execute(
        select(
            func.date(Application.applied_at).label("day"),
            func.count(Application.id).label("cnt"),
        )
        .where(Application.user_id == user.id)
        .where(Application.status == ApplicationStatus.APPLIED.value)
        .where(Application.applied_at >= seven_days_ago)
        .group_by(func.date(Application.applied_at))
        .order_by(func.date(Application.applied_at))
    )
    daily_map = {str(row.day): row.cnt for row in daily_rows.all()}

    # Fill in missing days (0 count) for the last 7 days
    daily_activity = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        daily_activity.append(DailyActivity(
            date=d.isoformat(),
            count=daily_map.get(str(d), 0),
        ))

    # ── 2. Source Distribution (per platform) ──
    source_rows = await db.execute(
        select(
            Job.platform,
            func.count(Application.id).label("cnt"),
        )
        .join(Job, Application.job_id == Job.id)
        .where(Application.user_id == user.id)
        .where(Application.status == ApplicationStatus.APPLIED.value)
        .group_by(Job.platform)
        .order_by(func.count(Application.id).desc())
    )
    source_distribution = [
        SourceCount(platform=row.platform.capitalize(), count=row.cnt)
        for row in source_rows.all()
    ]

    # ── 3. Heatmap (Last 365 days) ──
    year_ago = datetime.combine(today - timedelta(days=364), datetime.min.time())
    heatmap_rows = await db.execute(
        select(
            func.date(Application.applied_at).label("day"),
            func.count(Application.id).label("cnt"),
        )
        .where(Application.user_id == user.id)
        .where(Application.status == ApplicationStatus.APPLIED.value)
        .where(Application.applied_at >= year_ago)
        .group_by(func.date(Application.applied_at))
        .order_by(func.date(Application.applied_at))
    )
    heatmap_map = {str(row.day): row.cnt for row in heatmap_rows.all()}

    heatmap = []
    for i in range(364, -1, -1):
        d = today - timedelta(days=i)
        heatmap.append(DailyActivity(
            date=d.isoformat(),
            count=heatmap_map.get(str(d), 0),
        ))

    return AnalyticsResponse(
        daily_activity=daily_activity,
        source_distribution=source_distribution,
        heatmap=heatmap,
    )
