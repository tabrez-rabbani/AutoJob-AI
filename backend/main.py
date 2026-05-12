"""
AutoJob AI — FastAPI Application Entry Point
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.agents import router as agents_router
from app.api.applications import router as apply_router
from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.automation import router as automation_router
from app.workers.task_manager import task_manager

# ── Logging ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
# Silence noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("autojob")


# ── Lifespan (startup / shutdown) ────────────────────
async def _periodic_cleanup():
    """Background task: clean up old completed/failed tasks every 30 minutes."""
    while True:
        await asyncio.sleep(30 * 60)  # Run every 30 minutes
        try:
            removed = task_manager.cleanup_old_tasks(max_age_hours=2)
            if removed:
                logger.info(f"🧹 Periodic cleanup: removed {removed} old tasks")
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs on startup and shutdown."""
    logger.info(f"🚀 {settings.app_name} starting up ({settings.app_env})")
    # Start background cleanup task
    cleanup_task = asyncio.create_task(_periodic_cleanup())
    yield
    # Cancel cleanup on shutdown
    cleanup_task.cancel()
    logger.info(f"👋 {settings.app_name} shutting down")


# ── App Instance ─────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    description="AI-powered job application automation platform",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_dev else None,      # Disable in production
    redoc_url="/redoc" if settings.is_dev else None,     # Disable in production
)

# ── CORS ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate Limiting ────────────────────────────────────
from app.utils.rate_limiter import RateLimiterMiddleware
app.add_middleware(RateLimiterMiddleware)

# ── Routers ──────────────────────────────────────────
app.include_router(health_router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(agents_router, prefix="/api")
app.include_router(apply_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")
app.include_router(automation_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint — API info."""
    info = {
        "name": settings.app_name,
        "version": "0.1.0",
        "health": "/api/health",
    }
    if settings.is_dev:
        info["docs"] = "/docs"
    return info
