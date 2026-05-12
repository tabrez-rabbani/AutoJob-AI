"""
AutoJob AI — Automation API (Background Processing + SSE)
Endpoints for starting automation in background and streaming real-time progress.

Flow:
  1. POST /automation/start   → starts pipeline in background thread, returns task_id
  2. GET  /automation/{id}/stream → SSE stream for real-time progress
  3. GET  /automation/{id}/status → poll-based status check (fallback)
"""

import asyncio
import json
import sys
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.application import Application, ApplicationStatus
from app.models.job import Job
from sqlalchemy import select, func
from app.automation.factory import get_adapter, SUPPORTED_PLATFORMS
from app.services.job_service import save_scraped_jobs
from app.utils.auth import get_current_user
from app.utils.resume_parser import extract_resume_text
from app.agents.orchestrator import run_job_analysis, MATCH_THRESHOLD
from app.workers.task_manager import task_manager, PipelineStage, TaskStatus
from app.config import settings

logger = logging.getLogger("autojob.api.automation")

router = APIRouter(prefix="/automation", tags=["Automation"])

MAX_APPLICATIONS_PER_CALL = 25

# Platform-specific daily apply limits (fallback when not in config)
PLATFORM_DAILY_LIMITS = {
    "linkedin": 10,
    "naukri": 25,
}


# ── Schemas ──────────────────────────────────────────

class StartAutomationRequest(BaseModel):
    linkedin_email: str = ""
    linkedin_password: str = ""
    naukri_email: str = ""
    naukri_password: str = ""
    platforms: list[str] = ["linkedin"]
    keywords: str
    location: str = ""
    country: str = "India"
    phone: str = ""
    max_applications: int = 5
    delay_seconds: int = 15
    dry_run: bool = True


class StartAutomationResponse(BaseModel):
    task_id: str
    status: str
    message: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    stage: str
    stage_message: str
    jobs_scraped: int = 0
    jobs_matched: int = 0
    jobs_qualified: int = 0
    jobs_applied: int = 0
    jobs_failed: int = 0
    jobs_skipped: int = 0
    current_job_index: int = 0
    total_jobs: int = 0
    result: dict | None = None
    error: str | None = None


# ── Windows Thread Helper ────────────────────────────

def _run_async_in_new_loop(func, kwargs):
    """
    Run an async coroutine function in a NEW event loop (ProactorEventLoop on Windows).
    We must create the coroutine INSIDE the new loop to prevent asyncpg errors like
    "got Future attached to a different loop".
    """
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # Create coroutine in the correct event loop
        coro = func(**kwargs)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Endpoints ────────────────────────────────────────

@router.post("/start", response_model=StartAutomationResponse)
async def start_automation(
    request: StartAutomationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Start the full automation pipeline in background.
    Returns immediately with a task_id for tracking progress.
    """
    # Check for resume
    if not user.resume_url:
        raise HTTPException(status_code=400, detail="Please upload your resume first (Settings → Resume).")

    # Check for existing active task
    active = task_manager.get_user_active_task(str(user.id))
    if active:
        return StartAutomationResponse(
            task_id=active.task_id,
            status="already_running",
            message="An automation pipeline is already running. Track its progress with the existing task_id.",
        )

    # Create the task
    task_id = task_manager.create_task(str(user.id))
    if task_id is None:
        raise HTTPException(
            status_code=503,
            detail="Server is busy — too many automations running. Please try again in a few minutes.",
        )

    # Extract resume text now (on main loop) since we need DB access
    resume_path = user.resume_url
    resume_text = ""
    if resume_path:
        resume_text = await extract_resume_text(resume_path) or ""

    user_profile = {
        "full_name": user.full_name or "",
        "resume_text": resume_text,
        "skills": user.skills or [],
        "preferred_roles": user.preferred_roles or [],
        "preferred_locations": user.preferred_locations or [],
        "experience_years": user.experience_years or 0,
        "current_ctc": user.current_ctc or 0,
        "expected_ctc": user.expected_ctc or 0,
        "notice_period_days": user.notice_period_days or 0,
        "phone": user.phone or "",
        "linkedin_url": user.linkedin_url or "",
        "current_city": user.current_city or "",
    }

    # Build credentials map for each platform
    platform_creds = {}
    for p in request.platforms:
        p = p.strip().lower()
        if p not in SUPPORTED_PLATFORMS:
            continue
        if p == "linkedin":
            from app.utils.security import decrypt_credential
            ln_email = request.linkedin_email
            ln_password = request.linkedin_password
            if not ln_email and user.linkedin_email_enc:
                try: ln_email = decrypt_credential(user.linkedin_email_enc)
                except: pass
            if not ln_password and user.linkedin_password_enc:
                try: ln_password = decrypt_credential(user.linkedin_password_enc)
                except: pass
            platform_creds[p] = {"email": ln_email, "password": ln_password}
        elif p == "naukri":
            # Decrypt from DB if user saved credentials
            from app.utils.security import decrypt_credential
            nk_email = request.naukri_email
            nk_password = request.naukri_password
            if not nk_email and user.naukri_email_enc:
                try: nk_email = decrypt_credential(user.naukri_email_enc)
                except: pass
            if not nk_password and user.naukri_password_enc:
                try: nk_password = decrypt_credential(user.naukri_password_enc)
                except: pass
            platform_creds[p] = {"email": nk_email, "password": nk_password}

    if not platform_creds:
        raise HTTPException(status_code=400, detail="No valid platforms selected.")

    # Launch the pipeline in a background thread
    kwargs = dict(
        task_id=task_id,
        user_id=str(user.id),
        platform_creds=platform_creds,
        keywords=request.keywords,
        location=request.location,
        country=request.country,
        phone=request.phone,
        max_applications=min(request.max_applications, MAX_APPLICATIONS_PER_CALL),
        delay_seconds=request.delay_seconds,
        dry_run=request.dry_run,
        resume_path=resume_path,
        user_profile=user_profile,
    )
    
    asyncio.get_event_loop().run_in_executor(
        None,
        _run_async_in_new_loop,
        _background_pipeline,
        kwargs,
    )

    mode = "🏁 DRY RUN" if request.dry_run else "🚀 LIVE"
    platforms_str = ", ".join(platform_creds.keys())
    logger.info(f"{mode} — Pipeline started on [{platforms_str}] as task {task_id[:8]} by {user.email}")

    return StartAutomationResponse(
        task_id=task_id,
        status="started",
        message=f"Pipeline started! Track progress with task_id: {task_id}",
    )


@router.get("/{task_id}/status", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    user: User = Depends(get_current_user),
):
    """Get current status of a background task (poll-based fallback)."""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Verify task belongs to this user
    if task.user_id != str(user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    return TaskStatusResponse(
        task_id=task.task_id,
        status=task.status.value,
        stage=task.progress.stage.value,
        stage_message=task.progress.stage_message,
        jobs_scraped=task.progress.jobs_scraped,
        jobs_matched=task.progress.jobs_matched,
        jobs_qualified=task.progress.jobs_qualified,
        jobs_applied=task.progress.jobs_applied,
        jobs_failed=task.progress.jobs_failed,
        jobs_skipped=task.progress.jobs_skipped,
        current_job_index=task.progress.current_job_index,
        total_jobs=task.progress.total_jobs,
        result=task.result,
        error=task.error,
    )


@router.get("/{task_id}/stream")
async def stream_task_progress(
    task_id: str,
    token: str = Query(..., description="JWT token for SSE auth (EventSource can't send headers)"),
):
    """
    SSE (Server-Sent Events) endpoint for real-time progress updates.
    Frontend connects with EventSource and receives live updates.
    Auth via query param since EventSource API cannot send Authorization headers.
    """
    # Validate JWT token from query param
    from app.utils.security import decode_access_token
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Verify task ownership — match user email from JWT to task's user_id
    # We need to look up the user to compare IDs
    from app.database import async_session as async_session_factory
    from sqlalchemy import select
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.email == payload["sub"]))
        requesting_user = result.scalar_one_or_none()
    if not requesting_user or str(requesting_user.id) != task.user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    async def event_generator():
        # Send all past messages first (for late-joining clients)
        for msg in task_manager.get_message_log(task_id):
            yield f"data: {json.dumps(msg)}\n\n"

        # Stream new updates until task finishes
        while True:
            current_task = task_manager.get_task(task_id)
            if not current_task:
                yield f"data: {json.dumps({'stage': 'error', 'message': 'Task not found'})}\n\n"
                break

            if current_task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                # Send final state
                final = {
                    "stage": current_task.progress.stage.value,
                    "message": current_task.progress.stage_message,
                    "status": current_task.status.value,
                    "result": current_task.result,
                    "error": current_task.error,
                }
                yield f"data: {json.dumps(final)}\n\n"
                break

            # Wait for the next update (with timeout to keep connection alive)
            got_update = await task_manager.wait_for_update(task_id, timeout=15.0)
            if got_update:
                # Send the latest message from the log
                log = task_manager.get_message_log(task_id)
                if log:
                    yield f"data: {json.dumps(log[-1])}\n\n"
            else:
                # Send heartbeat to keep connection alive
                yield f": heartbeat\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Background Pipeline ─────────────────────────────

async def _background_pipeline(
    task_id: str,
    user_id: str,
    platform_creds: dict,
    keywords: str,
    location: str,
    country: str,
    phone: str,
    max_applications: int,
    delay_seconds: int,
    dry_run: bool,
    resume_path: str,
    user_profile: dict,
) -> None:
    """
    Full automation pipeline that runs in a background thread.
    Loops through each selected platform sequentially.
    Reports progress through task_manager for SSE streaming.
    """
    # ── Create a Thread-Local Database Engine ──
    # Asyncpg connections are bound to the event loop they are created in.
    # Since this runs in a new thread and new event loop, we CANNOT use the globally imported `async_session`
    # because its connection pool belongs to the main thread's event loop.
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    
    # NullPool prevents connection pooling entirely, guaranteeing fresh connections on this loop
    thread_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    local_async_session = async_sessionmaker(thread_engine, expire_on_commit=False)

    try:
        # ═════════════════════════════════════════════
        # MULTI-PLATFORM LOOP
        # ═════════════════════════════════════════════
        all_job_listings = []
        all_results = []
        total_applied = 0
        total_failed = 0
        total_skipped = 0
        platform_reports = []

        for platform_name, creds in platform_creds.items():
            p_label = platform_name.capitalize()
            logger.info(f"\n{'='*50}\n[{p_label}] Starting pipeline\n{'='*50}")

            # ═════════════════════════════════════════════
            # EARLY CHECK: Daily Apply Limit (fail fast)
            # ═════════════════════════════════════════════
            try:
                # Construct today's midnight in UTC without importing time
                # (importing 'from datetime import time' shadows global 'datetime')
                _now_utc = datetime.now(timezone.utc)
                early_today_start = datetime(
                    _now_utc.year, _now_utc.month, _now_utc.day,
                    tzinfo=timezone.utc
                )
                
                async with local_async_session() as db:
                    early_apply_count = await db.scalar(
                        select(func.count(Application.id)).where(
                            Application.user_id == user_id,
                            Application.created_at >= early_today_start,
                            Application.status == ApplicationStatus.APPLIED.value
                        )
                    ) or 0
                
                early_max = getattr(
                    settings,
                    f"{platform_name}_max_applies_per_day",
                    PLATFORM_DAILY_LIMITS.get(platform_name, 10)
                )
                
                if early_apply_count >= early_max:
                    task_manager.fail_task(
                        task_id,
                        f"Daily limit reached: You have applied to {early_apply_count} "
                        f"jobs today (max {early_max}). Try again tomorrow."
                    )
                    logger.warning(
                        f"[{p_label}] Daily limit check: {early_apply_count}/{early_max} — BLOCKED"
                    )
                    return
                else:
                    remaining = early_max - early_apply_count
                    logger.info(
                        f"[{p_label}] Daily limit check: {early_apply_count}/{early_max} used, "
                        f"{remaining} remaining"
                    )
            except Exception as e:
                logger.warning(f"[{p_label}] Early limit check failed (continuing): {e}")

            # ═════════════════════════════════════════════
            # STEP 1: LOGIN
            # ═════════════════════════════════════════════
            task_manager.update_progress(
                task_id, stage=PipelineStage.LOGIN,
                message=f"[{p_label}] Logging in...",
            )

            adapter = get_adapter(platform_name, headless=False)
            login_ok = await adapter.login({
                "email": creds.get("email", ""),
                "password": creds.get("password", ""),
            })

            if not login_ok:
                task_manager.update_progress(
                    task_id, stage=PipelineStage.LOGIN,
                    message=f"[{p_label}] ❌ Login failed. Skipping this platform.",
                )
                await adapter.close()
                platform_reports.append(f"{p_label}: Login failed")
                continue

            task_manager.update_progress(
                task_id, stage=PipelineStage.LOGIN,
                message=f"[{p_label}] ✅ Logged in successfully",
            )

            # ═════════════════════════════════════════════
            # STEP 2: SCRAPE JOBS (inside platform loop)
                # ═════════════════════════════════════════════
            # ── Check Scrape Limit ──
            try:
                # Use current date in UTC — construct midnight directly
                # NOTE: Do NOT import from datetime inside this function!
                # It shadows the global 'datetime' class and breaks everything.
                _scrape_now = datetime.now(timezone.utc)
                today_start = datetime(
                    _scrape_now.year, _scrape_now.month, _scrape_now.day,
                    tzinfo=timezone.utc
                )
            
                # Count scraped jobs today for this platform
                async with local_async_session() as db:
                    scrape_count_query = select(func.count(Job.id)).where(
                        Job.platform == platform_name, 
                        Job.scraped_at >= today_start
                    )
                    today_scrapes = await db.scalar(scrape_count_query) or 0
            except Exception as e:
                logger.error(f"Failed to check scrape limits: {e}")
                today_scrapes = 0

            max_daily_scrapes = getattr(settings, f"{platform_name}_max_scrapes_per_day", 50)
            remaining_scrapes = max_daily_scrapes - today_scrapes

            if remaining_scrapes <= 0:
                task_manager.update_progress(task_id, stage=PipelineStage.SCRAPING, message=f"[{p_label}] Daily scrape limit reached ({today_scrapes}/{max_daily_scrapes}). Skipping.")
                await adapter.close()
                platform_reports.append(f"{p_label}: Scrape limit reached")
                continue

            # For Naukri ~70% jobs are external apply, so we need to scrape 3x
            # to have a realistic chance of finding enough direct-apply jobs
            if platform_name == "naukri":
                max_requested = min(max_applications * 3, 60)
            else:
                max_requested = min(max_applications * 3, 25)
        
            # Parse locations (split by comma, clean whitespace)
            locations_list = [loc.strip() for loc in location.split(",")] if location and location.strip() else [None]
            job_listings = []

            for loc in locations_list:
                remaining_scrapes = max_daily_scrapes - today_scrapes
                if remaining_scrapes <= 0:
                    break
                
                allowed_results = min(max_requested - len(job_listings), remaining_scrapes)
                if allowed_results <= 0:
                    break

                loc_name = loc if loc else "Anywhere"
                task_manager.update_progress(
                    task_id, stage=PipelineStage.SCRAPING,
                    message=f"[{p_label}] Searching for '{keywords}' in '{loc_name}' (allowed: {allowed_results})...",
                )

                chunk = await adapter.search_jobs(
                    keywords=keywords,
                    location=loc,
                    country=country,
                    max_results=allowed_results,
                )
            
                if chunk:
                    job_listings.extend(chunk)
                    today_scrapes += len(chunk)
                
                if len(job_listings) >= max_requested:
                    break

            if not job_listings:
                task_manager.update_progress(task_id, stage=PipelineStage.SCRAPING, message=f"[{p_label}] No jobs found for '{keywords}'. Skipping.")
                await adapter.close()
                platform_reports.append(f"{p_label}: No jobs found")
                continue

            # ═════════════════════════════════════════════
            # STEP 2B: QUICK PRE-SCAN — Filter external apply jobs
            # ═════════════════════════════════════════════
            # Before closing the browser, quickly visit each job URL to check
            # if it has a direct Apply button or is external/expired.
            # This saves expensive AI API calls on jobs we can't apply to.
            if platform_name == "naukri" and len(job_listings) > 0:
                task_manager.update_progress(
                    task_id, stage=PipelineStage.SCRAPING,
                    message=f"[{p_label}] 🔍 Pre-scanning {len(job_listings)} jobs for direct apply...",
                    jobs_scraped=len(job_listings),
                )

                direct_apply_jobs = []
                external_count = 0
                seen_urls: set[str] = set()  # Dedup by URL

                for idx, job in enumerate(job_listings):
                    # Skip duplicate URLs
                    if job.apply_url in seen_urls:
                        continue
                    seen_urls.add(job.apply_url)

                    try:
                        await adapter._page.goto(job.apply_url, wait_until="domcontentloaded", timeout=15000)
                        await adapter.browser_manager.human_delay(1, 2)

                        # Check for external apply
                        apply_btn = adapter._page.locator(
                            "button#apply-button, "
                            "button[class*='apply-button'], "
                            "button:has-text('Apply'), "
                            "a:has-text('Apply on company site'), "
                            "button:has-text('Apply on company site')"
                        )

                        is_external = False
                        if await apply_btn.count() == 0:
                            is_external = True  # No apply button = expired/external
                        else:
                            btn_text = (await apply_btn.first.inner_text()).strip().lower()
                            if "company site" in btn_text or "external" in btn_text:
                                is_external = True

                        if is_external:
                            external_count += 1
                            logger.info(f"  Pre-scan [{idx+1}/{len(job_listings)}]: '{job.title}' — EXTERNAL (removed)")
                        else:
                            direct_apply_jobs.append(job)
                            logger.info(f"  Pre-scan [{idx+1}/{len(job_listings)}]: '{job.title}' — DIRECT APPLY ✅")

                    except Exception as e:
                        # If scan fails, keep the job (will be handled during apply)
                        direct_apply_jobs.append(job)
                        logger.warning(f"  Pre-scan [{idx+1}/{len(job_listings)}]: '{job.title}' — scan error, keeping ({e})")
                        
                    # Early stop: if we found enough direct-apply jobs to satisfy the user's request
                    if len(direct_apply_jobs) >= max_applications:
                        logger.info(f"  🎯 Found {max_applications} direct-apply jobs. Stopping pre-scan early.")
                        break

                logger.info(f"Pre-scan complete: {len(direct_apply_jobs)} direct-apply, {external_count} external removed")
                job_listings = direct_apply_jobs

                task_manager.update_progress(
                    task_id, stage=PipelineStage.SCRAPING,
                    message=f"[{p_label}] ✅ {len(job_listings)} direct-apply jobs (filtered {external_count} external)",
                    jobs_scraped=len(job_listings),
                )

                if not job_listings:
                    await adapter.close()
                    task_manager.update_progress(
                        task_id, stage=PipelineStage.SCRAPING,
                        message=f"[{p_label}] No direct-apply jobs found. All were external.",
                    )
                    platform_reports.append(f"{p_label}: All jobs were external apply")
                    continue

            # Close the scraping browser — we'll open a new one for applying
            # NOTE: For LinkedIn, we keep the same browser to preserve session/fingerprint.
            # LinkedIn blocks Easy Apply if the browser fingerprint changes mid-session.
            if platform_name != "linkedin":
                await adapter.close()

            task_manager.update_progress(
                task_id, stage=PipelineStage.SCRAPING,
                message=f"[{p_label}] ✅ Found {len(job_listings)} jobs",
                jobs_scraped=len(job_listings),
            )

            # Save scraped jobs to DB
            try:
                async with local_async_session() as db:
                    save_result = await save_scraped_jobs(db, job_listings)
                    await db.commit()
                    logger.info(f"  Saved {save_result['saved']} new jobs")
            except Exception as e:
                logger.error(f"Failed to save scraped jobs: {e}")

            # ═════════════════════════════════════════════
            # STEP 3: AI MATCHING
            # ═════════════════════════════════════════════
            task_manager.update_progress(
                task_id, stage=PipelineStage.AI_MATCHING,
                message=f"[{p_label}] 🧠 AI analyzing and scoring jobs...",
            )

            jobs_for_ai = [
                {
                    "id": j.platform_job_id,
                    "title": j.title,
                    "company": j.company,
                    "location": j.location,
                    "description": j.description or "",
                    "job_type": j.job_type,
                    "apply_url": j.apply_url,
                }
                for j in job_listings
            ]

            try:
                # Naukri doesn't need cover letters — skip tailoring to save time & API calls
                skip_tailor = (platform_name == "naukri")
                ai_result = await run_job_analysis(user_profile, jobs_for_ai, skip_tailoring=skip_tailor)
                ai_results = ai_result.get("results", [])
                ai_summary = ai_result.get("summary", {})

                task_manager.update_progress(
                    task_id, stage=PipelineStage.AI_MATCHING,
                    message=f"✅ AI scored {ai_summary.get('total_jobs', 0)} jobs — {ai_summary.get('qualified', 0)} qualified",
                    jobs_matched=ai_summary.get("total_jobs", 0),
                    jobs_qualified=ai_summary.get("qualified", 0),
                )
            except Exception as e:
                logger.warning(f"AI analysis failed ({e}). Falling back to all jobs.")
                ai_results = [
                    {
                        "job_id": j.platform_job_id,
                        "job_title": j.title,
                        "company": j.company,
                        "match_score": 100,
                        "recommendation": "apply",
                    }
                    for j in job_listings
                ]
                task_manager.update_progress(
                    task_id, stage=PipelineStage.AI_MATCHING,
                    message="⚠️ AI analysis failed — using all jobs as fallback",
                    jobs_matched=len(job_listings),
                    jobs_qualified=len(job_listings),
                )

            # Filter qualified jobs
            qualified_jobs = []
            skipped_by_ai = 0

            for ai_job in ai_results:
                score = ai_job.get("match_score", 0)
                job_id = ai_job.get("job_id", "")
                original_job = next(
                    (j for j in job_listings if j.platform_job_id == job_id), None
                )

                if not original_job or not original_job.apply_url:
                    continue

                if score >= MATCH_THRESHOLD:
                    cover_letter = ai_job.get("cover_letter")
                    qualified_jobs.append({
                        "title": original_job.title,
                        "company": original_job.company,
                        "apply_url": original_job.apply_url,
                        "match_score": score,
                        "recommendation": ai_job.get("recommendation", "apply"),
                        "cover_letter": cover_letter,
                        "description": original_job.description or "",
                        "location": original_job.location or "",
                    })
                else:
                    skipped_by_ai += 1

            if not qualified_jobs:
                task_manager.update_progress(
                    task_id, stage=PipelineStage.AI_MATCHING,
                    message=f"[{p_label}] No jobs matched your profile (threshold: {MATCH_THRESHOLD}).",
                    jobs_skipped=skipped_by_ai,
                )
                platform_reports.append(f"{p_label}: {len(job_listings)} scraped, 0 matched")
                continue

            # ── Check Apply Limit ──
            try:
                # Reusing the today_start variable from above
                async with local_async_session() as db:
                    apply_count_query = select(func.count(Application.id)).where(
                        Application.user_id == user_id,
                        Application.created_at >= today_start,
                        Application.status == ApplicationStatus.APPLIED.value
                    )
                    today_applies = await db.scalar(apply_count_query) or 0
            except Exception as e:
                logger.error(f"Failed to check apply limits: {e}")
                today_applies = 0

            max_daily_applies = getattr(settings, f"{platform_name}_max_applies_per_day", PLATFORM_DAILY_LIMITS.get(platform_name, 10))
            remaining_applies = max_daily_applies - today_applies

            if remaining_applies <= 0:
                task_manager.fail_task(task_id, f"Daily limit reached: You have applied to {today_applies} jobs today (max {max_daily_applies}). Try again tomorrow.")
                return

            # Restrict to remaining allowance or user request
            final_max_applies = min(max_applications, remaining_applies)
        
            if len(qualified_jobs) > final_max_applies:
                task_manager.update_progress(
                    task_id, stage=PipelineStage.APPLYING,
                    message=f"Trimming qualified jobs from {len(qualified_jobs)} to {final_max_applies} due to daily limits ({remaining_applies} remaining today).",
                )
                skipped_by_ai += (len(qualified_jobs) - final_max_applies)
                qualified_jobs = qualified_jobs[:final_max_applies]

            task_manager.update_progress(
                task_id, stage=PipelineStage.APPLYING,
                message=f"Starting applications to {len(qualified_jobs)} qualified jobs...",
                total_jobs=len(qualified_jobs),
                jobs_skipped=skipped_by_ai,
            )

            # Reuse same browser session for LinkedIn (preserves fingerprint + cookies)
            # For other platforms, open a fresh one
            if platform_name == "linkedin":
                apply_adapter = adapter  # Reuse same browser
            else:
                apply_adapter = get_adapter(platform_name, headless=False)
                login_ok = await apply_adapter.login({
                    "email": creds.get("email", ""),
                    "password": creds.get("password", ""),
                })

                if not login_ok:
                    task_manager.update_progress(task_id, stage=PipelineStage.APPLYING, message=f"[{p_label}] ❌ Re-login for apply step failed. Skipping.")
                    await apply_adapter.close()
                    platform_reports.append(f"{p_label}: Apply re-login failed")
                    continue

            results = []
            applied_count = 0
            failed_count = 0
            skipped_count = skipped_by_ai
            applied_urls: set[str] = set()  # Dedup: don't apply to same job twice

            for i, job in enumerate(qualified_jobs):
                # Skip duplicate URLs
                if job["apply_url"] in applied_urls:
                    logger.info(f"  [{i+1}/{len(qualified_jobs)}] Skipping duplicate: '{job['title']}'")
                    skipped_count += 1
                    continue
                applied_urls.add(job["apply_url"])
                task_manager.update_progress(
                    task_id, stage=PipelineStage.APPLYING,
                    message=f"📋 [{i+1}/{len(qualified_jobs)}] Applying: '{job['title']}' at {job['company']} (match: {job.get('match_score', '?')}%)",
                    current_job_index=i + 1,
                )

                answers = {}
                if phone:
                    answers["phone"] = phone

                job_info = {
                    "title": job["title"],
                    "company": job["company"],
                    "description": job.get("description", ""),
                    "location": job.get("location", ""),
                }

                # ── Retry loop with exponential backoff ──
                max_retries = settings.max_retries_per_job
                base_delay = settings.retry_base_delay
                apply_succeeded = False

                for attempt in range(1, max_retries + 1):
                    try:
                        apply_result = await apply_adapter.apply_to_job(
                            job_url=job["apply_url"],
                            resume_path=resume_path,
                            cover_letter=job.get("cover_letter"),
                            answers=answers,
                            user_profile=user_profile,
                            job_info=job_info,
                            dry_run=dry_run,
                        )

                        status = apply_result.get("status", "failed")
                        message = apply_result.get("message", "")

                        if status == "applied" or status == "skipped":
                            # Success or intentional skip — no retry needed
                            apply_succeeded = True
                            break
                        elif status == "external_apply":
                            # External apply — no retry, fast skip
                            apply_succeeded = True
                            break
                        elif status == "failed" and attempt < max_retries:
                            retry_wait = base_delay * (2 ** (attempt - 1))  # 30, 60, 120...
                            task_manager.update_progress(
                                task_id, stage=PipelineStage.APPLYING,
                                message=f"🔄 [{i+1}/{len(qualified_jobs)}] Retry {attempt}/{max_retries} for '{job['title']}' — waiting {retry_wait}s ({message})",
                                current_job_index=i + 1,
                            )
                            logger.warning(f"Retry {attempt}/{max_retries} for '{job['title']}' in {retry_wait}s")
                            await asyncio.sleep(retry_wait)
                            continue
                        else:
                            # Final attempt also failed
                            break

                    except Exception as e:
                        message = str(e)
                        status = "failed"
                        if attempt < max_retries:
                            retry_wait = base_delay * (2 ** (attempt - 1))
                            task_manager.update_progress(
                                task_id, stage=PipelineStage.APPLYING,
                                message=f"🔄 [{i+1}/{len(qualified_jobs)}] Error on '{job['title']}' — retry {attempt}/{max_retries} in {retry_wait}s",
                                current_job_index=i + 1,
                            )
                            logger.warning(f"Exception on '{job['title']}': {e}. Retrying in {retry_wait}s")
                            await asyncio.sleep(retry_wait)
                        else:
                            logger.error(f"All {max_retries} retries exhausted for '{job['title']}': {e}")
                            break

                # Update counters based on final result
                if status == "applied":
                    applied_count += 1
                elif status == "failed":
                    failed_count += 1
                else:
                    skipped_count += 1

                # ── Smart delay: full wait after real apply, fast skip for external/skipped ──
                if i < len(qualified_jobs) - 1:  # no delay after last job
                    if status == "applied":
                        # Naukri is lenient — shorter delay is safe
                        # LinkedIn needs full delay due to aggressive anti-bot
                        if platform_name == "naukri":
                            wait = min(delay_seconds, 7)
                        else:
                            wait = delay_seconds
                        task_manager.update_progress(
                            task_id, stage=PipelineStage.APPLYING,
                            message=f"⏳ Waiting {wait}s before next application...",
                            current_job_index=i + 1,
                        )
                        await asyncio.sleep(wait)
                    else:
                        # External/skipped/failed — just a brief 3s pause
                        await asyncio.sleep(3)

                retry_note = f" (after {attempt} attempts)" if attempt > 1 else ""
                results.append({
                    "job_title": job["title"],
                    "company": job["company"],
                    "apply_url": job["apply_url"],
                    "status": status,
                    "message": message + retry_note,
                    "cover_letter": job.get("cover_letter"),
                    "match_score": job.get("match_score"),
                    "retries": attempt - 1,
                })

                icon = '✅' if status == 'applied' else '⏭' if status == 'skipped' else '❌'
                task_manager.update_progress(
                    task_id, stage=PipelineStage.APPLYING,
                    message=f"{icon} {job['title']} at {job['company']} — {status.upper()}{retry_note}",
                    jobs_applied=applied_count,
                    jobs_failed=failed_count,
                    jobs_skipped=skipped_count,
                )

            await apply_adapter.close()

            # ═════════════════════════════════════════════
            # STEP 5: SAVE TO DATABASE
            # ═════════════════════════════════════════════
            task_manager.update_progress(
                task_id, stage=PipelineStage.SAVING,
                message="💾 Saving application records to database...",
            )

            try:
                async with local_async_session() as db:
                    platform_job_ids = [j.platform_job_id for j in job_listings]
                    db_result = await db.execute(select(Job).where(Job.platform_job_id.in_(platform_job_ids)))
                    db_jobs = {job.platform_job_id: job for job in db_result.scalars().all()}

                    for r in results:
                        original_job = next(
                            (j for j in job_listings if j.apply_url == r.get("apply_url")), None
                        )
                        if not original_job or original_job.platform_job_id not in db_jobs:
                            continue

                        db_job = db_jobs[original_job.platform_job_id]
                        app_record = Application(
                            user_id=user_id,
                            job_id=db_job.id,
                            status=r.get("status", "failed"),
                            match_score=r.get("match_score"),
                            cover_letter=r.get("cover_letter"),
                            applied_at=datetime.now(timezone.utc) if r.get("status") == "applied" else None,
                            notes=r.get("message", ""),
                        )
                        db.add(app_record)

                    # Save skipped jobs too
                    for ai_job in ai_results:
                        score = ai_job.get("match_score", 0)
                        if score >= MATCH_THRESHOLD:
                            continue
                        job_id_str = ai_job.get("job_id", "")
                        if job_id_str not in db_jobs:
                            continue
                        db_job = db_jobs[job_id_str]
                        app_record = Application(
                            user_id=user_id,
                            job_id=db_job.id,
                            status="skipped",
                            match_score=score,
                            notes=f"AI score {score} below threshold {MATCH_THRESHOLD}",
                        )
                        db.add(app_record)

                    await db.commit()
                    logger.info("Application records saved to database")
            except Exception as e:
                logger.error(f"Failed to save application records: {e}")

            all_job_listings.extend(job_listings)
            all_results.extend(results)
            total_applied += applied_count
            total_failed += failed_count
            total_skipped += skipped_count
            platform_reports.append(f"{p_label}: Scraped {len(job_listings)} → Applied {applied_count}")

        # ═════════════════════════════════════════════
        # CROSS-PLATFORM FINAL REPORT
        # ═════════════════════════════════════════════
        if not all_results and not platform_reports:
            task_manager.fail_task(task_id, "No platforms were processed successfully.")
            return

        report_lines = " | ".join(platform_reports) if platform_reports else "No data"
        final_result = {
            "status": "success",
            "message": f"{report_lines}",
            "total_attempted": len(all_results),
            "applied": total_applied,
            "skipped": total_skipped,
            "failed": total_failed,
            "dry_run": dry_run,
            "results": all_results,
            "platform_reports": platform_reports,
        }

        task_manager.complete_task(task_id, final_result)

    except Exception as e:
        logger.error(f"Background pipeline error: {e}")
        task_manager.fail_task(task_id, str(e))

    finally:
        # Clean up the thread-local engine
        try:
            await thread_engine.dispose()
        except Exception:
            pass


# ══════════════════════════════════════════════════════
# PHASE 2: FEED SCANNER PIPELINE
# ══════════════════════════════════════════════════════

class StartFeedScanRequest(BaseModel):
    linkedin_email: str
    linkedin_password: str
    max_emails: int = 5
    dry_run: bool = True


@router.post("/feed-scan/start", response_model=StartAutomationResponse)
async def start_feed_scan(
    request: StartFeedScanRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Start the Feed Scanner pipeline in background.
    Scrolls LinkedIn feed, finds job posts, and emails recruiters.
    """
    # Check for resume
    if not user.resume_url:
        raise HTTPException(status_code=400, detail="Please upload your resume first (Settings → Resume).")

    # Check for SMTP configured
    if not user.smtp_email_enc or not user.smtp_password_enc:
        raise HTTPException(
            status_code=400,
            detail="Email settings not configured. Please set them in 'Settings > Communication'."
        )

    # Check for existing active task
    active = task_manager.get_user_active_task(str(user.id))
    if active:
        return StartAutomationResponse(
            task_id=active.task_id,
            status="already_running",
            message="An automation pipeline is already running.",
        )

    # Create the task
    task_id = task_manager.create_task(str(user.id))
    if task_id is None:
        raise HTTPException(
            status_code=503,
            detail="Server is busy — too many automations running. Please try again in a few minutes.",
        )

    # Extract resume text
    resume_path = user.resume_url
    resume_text = ""
    if resume_path:
        resume_text = await extract_resume_text(resume_path) or ""

    user_profile = {
        "full_name": user.full_name or "",
        "resume_text": resume_text,
        "skills": user.skills or [],
        "preferred_roles": user.preferred_roles or [],
        "experience_years": user.experience_years or 0,
        "phone": user.phone or "",
        "linkedin_url": user.linkedin_url or "",
        "github_url": user.github_url or "",
        "portfolio_url": user.portfolio_url or "",
    }

    kwargs = dict(
        task_id=task_id,
        user_id=str(user.id),
        linkedin_email=request.linkedin_email,
        linkedin_password=request.linkedin_password,
        max_emails=min(request.max_emails, 10),  # Hard cap at 10
        dry_run=request.dry_run,
        resume_path=resume_path,
        user_profile=user_profile,
        smtp_email=user.smtp_email_enc,  # Sent as encrypted, decrypted inside standard adapter
        smtp_password=user.smtp_password_enc, # Sent as encrypted, decrypted inside standard adapter
        smtp_host=user.smtp_host or "smtp.gmail.com",
        smtp_port=user.smtp_port or 587,
    )

    asyncio.get_event_loop().run_in_executor(
        None,
        _run_async_in_new_loop,
        _background_feed_pipeline,
        kwargs,
    )

    mode = "🏁 DRY RUN" if request.dry_run else "🚀 LIVE"
    logger.info(f"{mode} — Feed scan started as task {task_id[:8]} by {user.email}")

    return StartAutomationResponse(
        task_id=task_id,
        status="started",
        message=f"Feed scan started! Track progress with task_id: {task_id}",
    )


async def _background_feed_pipeline(
    task_id: str,
    user_id: str,
    linkedin_email: str,
    linkedin_password: str,
    max_emails: int,
    dry_run: bool,
    resume_path: str,
    user_profile: dict,
    smtp_email: str,
    smtp_password: str,
    smtp_host: str,
    smtp_port: int,
) -> None:
    """
    Full Feed Scanner pipeline:
    Login → Scroll Feed → AI Analyze Posts → Filter Jobs → Tailor Email → Send → Done
    """
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession as ThreadAsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select
    from app.config import settings as app_settings

    thread_engine = create_async_engine(app_settings.database_url, echo=False)
    ThreadSession = sessionmaker(thread_engine, class_=ThreadAsyncSession, expire_on_commit=False)

    try:
        # ═══ STEP 1: LOGIN ═══
        task_manager.update_progress(
            task_id, stage=PipelineStage.LOGIN,
            message="Logging in to LinkedIn for feed scan...",
        )

        from app.automation.adapters.linkedin import LinkedInAdapter
        adapter = LinkedInAdapter(headless=False)
        logged_in = await adapter.login({"email": linkedin_email, "password": linkedin_password})

        if not logged_in:
            task_manager.fail_task(task_id, "LinkedIn login failed.")
            await thread_engine.dispose()
            return

        task_manager.update_progress(
            task_id, stage=PipelineStage.LOGIN,
            message="✅ LinkedIn login successful",
        )

        # ═══ STEP 2: SCROLL FEED (with keyword pre-filter) ═══
        task_manager.update_progress(
            task_id, stage=PipelineStage.SCRAPING,
            message="📜 Loading user profile for smart filtering...",
        )

        # Fetch user's preferred_roles and skills for keyword pre-filtering
        user_keywords = []
        async with ThreadSession() as sess:
            from app.models import User
            user_row = await sess.execute(select(User).where(User.id == user_id))
            user_obj = user_row.scalar_one_or_none()
            if user_obj:
                if isinstance(user_obj.preferred_roles, list):
                    user_keywords.extend([r.strip() for r in user_obj.preferred_roles if r and isinstance(r, str)])
                elif isinstance(user_obj.preferred_roles, str):
                    user_keywords.extend([r.strip() for r in user_obj.preferred_roles.split(",") if r.strip()])
                    
                if isinstance(user_obj.skills, list):
                    user_keywords.extend([s.strip() for s in user_obj.skills if s and isinstance(s, str)])
                elif isinstance(user_obj.skills, str):
                    user_keywords.extend([s.strip() for s in user_obj.skills.split(",") if s.strip()])
                    
                logger.info(f"  User keywords for filtering: {user_keywords[:10]}...")

        task_manager.update_progress(
            task_id, stage=PipelineStage.SCRAPING,
            message="📜 Scrolling LinkedIn feed with smart filtering...",
        )

        from app.automation.adapters.feed_scraper import LinkedInFeedScraper
        scraper = LinkedInFeedScraper(adapter.browser_manager, adapter._page, user_keywords=user_keywords)
        feed_posts = await scraper.scroll_and_extract()

        if not feed_posts:
            task_manager.update_progress(
                task_id, stage=PipelineStage.SCRAPING,
                message="No posts found in feed.",
            )
            await adapter.close()
            task_manager.complete_task(task_id, {"status": "success", "message": "No posts found", "emails_sent": 0})
            await thread_engine.dispose()
            return

        task_manager.update_progress(
            task_id, stage=PipelineStage.SCRAPING,
            message=f"Found {len(feed_posts)} posts — analyzing with AI...",
            jobs_scraped=len(feed_posts),
        )

        # Close browser — no more LinkedIn interaction needed
        await adapter.close()

        # ═══ STEP 3: AI ANALYZE POSTS ═══
        task_manager.update_progress(
            task_id, stage=PipelineStage.AI_MATCHING,
            message="🧠 AI is analyzing posts for job openings...",
        )

        from app.agents.post_analyzer import analyze_posts_batch
        post_dicts = [{"text": p.text, "author": p.author, "post_url": p.post_url, "post_id": p.post_id} for p in feed_posts]
        job_posts = await analyze_posts_batch(post_dicts)

        if not job_posts:
            task_manager.update_progress(
                task_id, stage=PipelineStage.AI_MATCHING,
                message="No job posts with emails found in feed.",
            )
            task_manager.complete_task(task_id, {"status": "success", "message": "No actionable job posts found", "emails_sent": 0})
            await thread_engine.dispose()
            return

        task_manager.update_progress(
            task_id, stage=PipelineStage.AI_MATCHING,
            message=f"Found {len(job_posts)} job posts with recruiter emails!",
            jobs_matched=len(job_posts),
        )

        # ═══ STEP 4: CHECK DAILY LIMIT & DEDUP ═══
        from app.services.email_sender import EmailSender

        async with ThreadSession() as db:
            remaining = await EmailSender.check_daily_limit(db, user_id)

        if remaining <= 0:
            task_manager.update_progress(
                task_id, stage=PipelineStage.APPLYING,
                message="Daily email limit reached (10/day). Try again tomorrow.",
            )
            task_manager.complete_task(task_id, {"status": "limit_reached", "message": "Daily email limit reached", "emails_sent": 0})
            await thread_engine.dispose()
            return

        # Limit job posts to remaining email budget
        actionable = job_posts[:min(max_emails, remaining)]
        task_manager.update_progress(
            task_id, stage=PipelineStage.APPLYING,
            message=f"Will email {len(actionable)} recruiters (limit: {remaining} remaining today)...",
            jobs_qualified=len(actionable),
        )

        # ═══ STEP 5: TAILOR & SEND EMAILS ═══
        from app.agents.email_tailor import tailor_email
        import asyncio as _asyncio

        sender = EmailSender(smtp_email, smtp_password, smtp_host, smtp_port)
        emails_sent = 0
        emails_failed = 0
        results = []

        for i, job_post in enumerate(actionable):
            recruiter_email = job_post.get("email", "")
            role = job_post.get("role", "Position")
            company = job_post.get("company", "")
            author = job_post.get("original_post", {}).get("author", "")

            task_manager.update_progress(
                task_id, stage=PipelineStage.APPLYING,
                message=f"Emailing [{i+1}/{len(actionable)}]: '{role}' → {recruiter_email}",
                current_job_index=i,
                total_jobs=len(actionable),
            )

            # Check for duplicate (same email + role already sent)
            async with ThreadSession() as db:
                from app.models.job import Job
                dup_check = await db.execute(
                    select(Job).where(
                        Job.poster_email == recruiter_email,
                        Job.title == role,
                        Job.source == "feed",
                    )
                )
                if dup_check.scalar_one_or_none():
                    logger.info(f"  ⏭️ Skipping duplicate: {recruiter_email} for '{role}'")
                    results.append({"email": recruiter_email, "role": role, "status": "skipped_duplicate"})
                    continue

            # Tailor the email via AI
            await _asyncio.sleep(1)  # Rate limit
            email_content = await tailor_email(
                user_profile=user_profile,
                job_info=job_post,
                recruiter_name=author,
            )

            subject = email_content.get("subject", f"Application for {role}")
            body = email_content.get("body", "")

            # Send or dry-run
            if dry_run:
                logger.info(f"  🏁 DRY RUN — Would send to {recruiter_email}: '{subject}'")
                send_result = {"status": "dry_run", "message": f"Dry run — {recruiter_email}"}
            else:
                send_result = await sender.send_application_email(
                    to_email=recruiter_email,
                    subject=subject,
                    body=body,
                    resume_path=resume_path,
                    sender_name=user_profile.get("full_name", ""),
                )

            # Save to DB regardless (for tracking)
            async with ThreadSession() as db:
                from app.models.job import Job
                from app.models.application import Application

                # Save job record
                job = Job(
                    platform="linkedin",
                    platform_job_id=job_post.get("original_post", {}).get("post_id", f"feed_{i}"),
                    source="feed",
                    title=role,
                    company=company or "Unknown",
                    location=job_post.get("location", ""),
                    description=job_post.get("summary", ""),
                    apply_url=job_post.get("original_post", {}).get("post_url", ""),
                    poster_email=recruiter_email,
                )
                db.add(job)
                await db.flush()

                # Save application record
                status = "emailed" if send_result.get("status") == "sent" else (
                    "applied" if send_result.get("status") == "dry_run" else "failed"
                )
                app = Application(
                    user_id=user_id,
                    job_id=job.id,
                    status=status,
                    apply_method="email",
                    cover_letter=body,
                    applied_at=datetime.now(timezone.utc) if status in ("emailed", "applied") else None,
                    notes=f"Subject: {subject}",
                )
                db.add(app)
                await db.commit()

            if send_result.get("status") in ("sent", "dry_run"):
                emails_sent += 1
            else:
                emails_failed += 1

            results.append({"email": recruiter_email, "role": role, "status": send_result.get("status"), "subject": subject})

            # Human delay between emails
            await _asyncio.sleep(3)

        # ═══ DONE ═══
        task_manager.update_progress(
            task_id, stage=PipelineStage.APPLYING,
            message=f"✅ Feed scan complete: {emails_sent} emails sent, {emails_failed} failed",
            jobs_applied=emails_sent,
            jobs_failed=emails_failed,
        )

        final_result = {
            "status": "success",
            "message": f"Feed scan: {len(feed_posts)} posts → {len(job_posts)} jobs → {emails_sent} emails sent",
            "posts_scanned": len(feed_posts),
            "job_posts_found": len(job_posts),
            "emails_sent": emails_sent,
            "emails_failed": emails_failed,
            "dry_run": dry_run,
            "results": results,
        }

        task_manager.complete_task(task_id, final_result)

    except Exception as e:
        logger.error(f"Feed pipeline error: {e}")
        task_manager.fail_task(task_id, str(e))

    finally:
        try:
            await thread_engine.dispose()
        except Exception:
            pass

