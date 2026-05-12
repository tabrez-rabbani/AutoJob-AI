"""
AutoJob AI — Auto Apply API
Full pipeline: Login → Scrape → AI Match → Apply to qualified jobs only.

Architecture (5 Steps):
  Thread 1 (Playwright):  Login → Scrape LinkedIn
  Main Event Loop:        AI Agent scores each job (LLM APIs)
  Thread 2 (Playwright):  Apply only to qualified jobs (score >= 60)
  Main Event Loop:        Save results to database

Windows Fix: Playwright runs in a dedicated thread with ProactorEventLoop.
AI agents run on uvicorn's main loop (they use HTTP APIs, not subprocesses).
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.application import (
    AutoApplyRequest,
    AutoApplyResponse,
    ApplicationResult,
)
from app.models.application import Application
from app.models.job import Job
from app.automation.adapters.linkedin import LinkedInAdapter
from app.services.job_service import save_scraped_jobs
from app.utils.auth import get_current_user
from app.utils.resume_parser import extract_resume_text
from app.agents.orchestrator import run_job_analysis, MATCH_THRESHOLD

logger = logging.getLogger("autojob.api.apply")

router = APIRouter(tags=["Auto Apply"])

MAX_APPLICATIONS_PER_CALL = 10


# ── Windows Thread Helper ────────────────────────────

def _run_async_in_new_loop(coro):
    """Run an async coroutine in a NEW event loop (with ProactorEventLoop on Windows)."""
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Step 1+2: Scrape Pipeline (runs in thread) ──────

async def _scrape_pipeline(
    linkedin_email: str,
    linkedin_password: str,
    keywords: str,
    location: str,
    max_results: int,
) -> dict:
    """Login to LinkedIn and scrape jobs. Runs in a dedicated thread."""
    adapter = LinkedInAdapter(headless=False)

    try:
        # Step 1: Login
        logger.info("Step 1/5: Logging into LinkedIn...")
        login_ok = await adapter.login({
            "email": linkedin_email,
            "password": linkedin_password,
        })

        if not login_ok:
            return {"status": "error", "message": "LinkedIn login failed. Check credentials.", "jobs": [], "adapter": None}

        # Step 2: Scrape
        logger.info(f"Step 2/5: Scraping jobs for '{keywords}' in '{location or 'Any'}'...")
        job_listings = await adapter.search_jobs(
            keywords=keywords,
            location=location or None,
            max_results=max_results,
        )

        if not job_listings:
            await adapter.close()
            return {"status": "error", "message": f"No jobs found on LinkedIn for '{keywords}'. Try different keywords.", "jobs": [], "adapter": None}

        logger.info(f"  → Scraped {len(job_listings)} jobs from LinkedIn")

        # Keep adapter alive for the apply step!
        return {"status": "success", "jobs": job_listings, "adapter": adapter}

    except Exception as e:
        logger.error(f"Scrape pipeline error: {e}")
        await adapter.close()
        return {"status": "error", "message": f"Scrape error: {str(e)}", "jobs": [], "adapter": None}


# ── Main Endpoint ────────────────────────────────────

@router.post("/jobs/auto-apply", response_model=AutoApplyResponse)
async def auto_apply_jobs(
    request: AutoApplyRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Full automation pipeline — one click does everything:

    1. Login to LinkedIn (thread)
    2. Scrape jobs using keywords/location (thread)
    3. AI Agent scores & matches each job (main loop)
    4. Filter qualified jobs (score >= 60) (main loop)
    5. Apply to qualified jobs only (thread)
    6. Save everything to database (main loop)

    Uses user's Settings profile (skills, roles, experience) for AI matching.
    """
    # Ensure resume is uploaded
    if not user.resume_url:
        return AutoApplyResponse(
            status="error",
            message="Please upload your resume first (Settings → Resume).",
            dry_run=request.dry_run,
        )

    resume_path = user.resume_url
    mode = "🏁 DRY RUN" if request.dry_run else "🚀 LIVE"
    logger.info(
        f"{mode} — Full pipeline started by {user.email}: "
        f"keywords='{request.keywords}', location='{request.location}', "
        f"max {request.max_applications} jobs, {request.delay_seconds}s delay"
    )

    # ═══════════════════════════════════════════════════
    # STEP 1+2: SCRAPE (in thread — Playwright needs ProactorEventLoop)
    # ═══════════════════════════════════════════════════
    try:
        scrape_result = await asyncio.to_thread(
            _run_async_in_new_loop,
            _scrape_pipeline(
                linkedin_email=request.linkedin_email,
                linkedin_password=request.linkedin_password,
                keywords=request.keywords,
                location=request.location,
                max_results=min(request.max_applications * 3, 25),
            )
        )
    except Exception as e:
        logger.error(f"Scrape thread error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    if scrape_result["status"] == "error":
        return AutoApplyResponse(
            status="error",
            message=scrape_result["message"],
            dry_run=request.dry_run,
        )

    scraped_jobs = scrape_result["jobs"]

    # Save scraped jobs to DB
    try:
        save_result = await save_scraped_jobs(db, scraped_jobs)
        await db.commit()
        logger.info(f"  → Saved {save_result['saved']} new jobs, {save_result['skipped']} duplicates")
    except Exception as e:
        logger.error(f"Failed to save scraped jobs: {e}")

    # ═══════════════════════════════════════════════════
    # STEP 3+4: AI MATCHING (on main loop — uses LLM HTTP APIs)
    # ═══════════════════════════════════════════════════
    logger.info("Step 3/5: AI Agent analyzing & scoring jobs...")

    # Extract text from uploaded resume (PRIMARY data source)
    resume_text = ""
    if resume_path:
        logger.info(f"  Extracting text from resume: {resume_path}")
        resume_text = await extract_resume_text(resume_path)
        if resume_text:
            logger.info(f"  → Extracted {len(resume_text)} chars from resume")
        else:
            logger.warning("  → Could not extract text from resume")

    # Build user profile: Resume text + Settings data (both fed to AI)
    user_profile = {
        "full_name": user.full_name or "",
        "resume_text": resume_text,  # ← PRIMARY: AI reads full resume
        "skills": user.skills or [],
        "preferred_roles": user.preferred_roles or [],
        "experience_years": user.experience_years or 0,
    }

    # Convert scraped jobs to dicts for the AI pipeline
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
        for j in scraped_jobs
    ]

    # Run AI analysis
    try:
        ai_result = await run_job_analysis(user_profile, jobs_for_ai)
        ai_results = ai_result.get("results", [])
        ai_summary = ai_result.get("summary", {})

        logger.info(
            f"  → AI analyzed {ai_summary.get('total_jobs', 0)} jobs: "
            f"{ai_summary.get('qualified', 0)} qualified (score >= {MATCH_THRESHOLD}), "
            f"avg score: {ai_summary.get('average_score', 0)}"
        )
    except Exception as e:
        logger.warning(f"⚠️ AI analysis failed ({e}). Falling back to applying to all jobs.")
        # Fallback: if AI fails, treat all jobs as qualified
        ai_results = [
            {
                "job_id": j.platform_job_id,
                "job_title": j.title,
                "company": j.company,
                "match_score": 100,  # Default max score
                "recommendation": "apply",
            }
            for j in scraped_jobs
        ]

    # Step 4: Filter qualified jobs (score >= threshold)
    qualified_jobs = []
    skipped_by_ai = 0

    for ai_job in ai_results:
        score = ai_job.get("match_score", 0)
        job_id = ai_job.get("job_id", "")

        # Find the original scraped job by ID
        original_job = next(
            (j for j in scraped_jobs if j.platform_job_id == job_id),
            None
        )

        if not original_job or not original_job.apply_url:
            continue

        if score >= MATCH_THRESHOLD:
            # Get cover letter from AI analysis results
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
            logger.info(f"  ⏭ Skipped '{original_job.title}' at {original_job.company} (score: {score} < {MATCH_THRESHOLD})")

    logger.info(f"Step 4/5: {len(qualified_jobs)} qualified, {skipped_by_ai} skipped by AI")

    if not qualified_jobs:
        return AutoApplyResponse(
            status="success",
            message=f"Scraped {len(scraped_jobs)} jobs. AI found 0 matching your profile (threshold: {MATCH_THRESHOLD}). Update your Skills/Roles in Settings for better matches.",
            total_attempted=0,
            skipped=skipped_by_ai,
            dry_run=request.dry_run,
        )

    # Limit to max_applications
    qualified_jobs = qualified_jobs[:min(request.max_applications, MAX_APPLICATIONS_PER_CALL)]

    # ═══════════════════════════════════════════════════
    # STEP 5: APPLY (in thread — Playwright again)
    # ═══════════════════════════════════════════════════
    logger.info(f"Step 5/5: Applying to {len(qualified_jobs)} qualified jobs...")

    try:
        apply_result = await asyncio.to_thread(
            _run_async_in_new_loop,
            _apply_pipeline_standalone(
                linkedin_email=request.linkedin_email,
                linkedin_password=request.linkedin_password,
                qualified_jobs=qualified_jobs,
                resume_path=resume_path,
                phone=request.phone,
                delay_seconds=request.delay_seconds,
                dry_run=request.dry_run,
                user_profile=user_profile,
            )
        )
    except Exception as e:
        logger.error(f"Apply thread error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # ═══════════════════════════════════════════════════
    # BUILD RESPONSE
    # ═══════════════════════════════════════════════════
    results = apply_result.get("results", [])
    counts = apply_result.get("counts", {})
    total = len(results)

    logger.info(
        f"✅ Full pipeline complete: {len(scraped_jobs)} scraped | "
        f"{len(qualified_jobs)} qualified | {total} attempted | "
        f"{counts.get('applied', 0)} applied | {counts.get('skipped', 0)} skipped"
    )

    # ═══════════════════════════════════════════════════
    # SAVE APPLICATION RECORDS TO DATABASE
    # ═══════════════════════════════════════════════════
    try:
        from sqlalchemy import select
        # Fetch actual DB jobs to get their UUIDs
        platform_job_ids = [j.platform_job_id for j in scraped_jobs]
        db_result = await db.execute(select(Job).where(Job.platform_job_id.in_(platform_job_ids)))
        db_jobs = {job.platform_job_id: job for job in db_result.scalars().all()}

        # Save records for jobs that went through apply step
        for r in results:
            # Find the original scraped job to get its platform_job_id
            original_job = next(
                (j for j in scraped_jobs if j.apply_url == r.get("apply_url")),
                None
            )
            if not original_job or original_job.platform_job_id not in db_jobs:
                continue

            db_job = db_jobs[original_job.platform_job_id]

            app_record = Application(
                user_id=user.id,
                job_id=db_job.id,
                status=r.get("status", "failed"),
                match_score=r.get("match_score") or next(
                    (q["match_score"] for q in qualified_jobs if q["apply_url"] == r.get("apply_url")),
                    None
                ),
                cover_letter=r.get("cover_letter"),
                applied_at=datetime.now(timezone.utc) if r.get("status") == "applied" else None,
                notes=r.get("message", ""),
            )
            db.add(app_record)

        # Save records for AI-skipped jobs (below threshold)
        for ai_job in ai_results:
            score = ai_job.get("match_score", 0)
            if score >= MATCH_THRESHOLD:
                continue  # Already saved above

            job_id_str = ai_job.get("job_id", "")
            if job_id_str not in db_jobs:
                continue

            db_job = db_jobs[job_id_str]

            app_record = Application(
                user_id=user.id,
                job_id=db_job.id,
                status="skipped",
                match_score=score,
                notes=f"AI score {score} below threshold {MATCH_THRESHOLD}",
            )
            db.add(app_record)

        await db.commit()
        logger.info("  → Application records saved to database")
    except Exception as e:
        logger.error(f"Failed to save application records: {e}")
        await db.rollback()

    return AutoApplyResponse(
        status="success",
        message=(
            f"Scraped {len(scraped_jobs)} jobs → AI matched {len(qualified_jobs)} "
            f"→ Applied to {counts.get('applied', 0)}"
        ),
        total_attempted=total,
        applied=counts.get("applied", 0),
        external_apply=counts.get("external_apply", 0),
        skipped=counts.get("skipped", 0) + skipped_by_ai,
        failed=counts.get("failed", 0),
        dry_run=request.dry_run,
        results=[
            ApplicationResult(
                job_id="",
                job_title=r["job_title"],
                company=r["company"],
                apply_url=r["apply_url"],
                status=r["status"],
                message=r["message"],
            )
            for r in results
        ],
    )


# ── Standalone Apply Pipeline (new login) ────────────
# Since we can't share the browser across threads, we re-login for the apply step.

async def _apply_pipeline_standalone(
    linkedin_email: str,
    linkedin_password: str,
    qualified_jobs: list[dict],
    resume_path: str,
    phone: str,
    delay_seconds: int,
    dry_run: bool,
    user_profile: dict | None = None,
) -> dict:
    """Apply to qualified jobs with a fresh LinkedIn login session."""
    adapter = LinkedInAdapter(headless=False)
    results = []
    counts = {"applied": 0, "external_apply": 0, "skipped": 0, "failed": 0}

    try:
        # Re-login (browser session from scrape thread can't be shared)
        logger.info("  Re-logging into LinkedIn for apply step...")
        login_ok = await adapter.login({
            "email": linkedin_email,
            "password": linkedin_password,
        })

        if not login_ok:
            return {"results": [], "counts": counts}

        for i, job in enumerate(qualified_jobs):
            if i > 0:
                logger.info(f"⏳ Waiting {delay_seconds}s before next application...")
                await asyncio.sleep(delay_seconds)

            logger.info(
                f"📋 [{i+1}/{len(qualified_jobs)}] Applying: '{job['title']}' at {job['company']} "
                f"(match: {job.get('match_score', '?')}%)"
            )

            answers = {}
            if phone:
                answers["phone"] = phone

            # Build job info context for AI screening
            job_info = {
                "title": job["title"],
                "company": job["company"],
                "description": job.get("description", ""),
                "location": job.get("location", ""),
            }

            apply_result = await adapter.apply_to_job(
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
            counts[status] = counts.get(status, 0) + 1

            results.append({
                "job_title": job["title"],
                "company": job["company"],
                "apply_url": job["apply_url"],
                "status": status,
                "message": message,
                "cover_letter": job.get("cover_letter"),
            })

            logger.info(f"  Result: {status.upper()} — {message}")

    except Exception as e:
        logger.error(f"Apply pipeline error: {e}")

    finally:
        await adapter.close()

    return {"results": results, "counts": counts}
