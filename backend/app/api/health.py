"""
AutoJob AI — Health Check API
Simple endpoints to verify the backend, database, and Redis are running.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """Basic health check — confirms the API is running."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "environment": settings.app_env,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/db")
async def database_health(db: AsyncSession = Depends(get_db)):
    """Check PostgreSQL connection."""
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        error_detail = str(e) if settings.is_dev else "Connection failed"
        return {"status": "unhealthy", "database": "disconnected", "error": error_detail}


@router.get("/health/redis")
async def redis_health():
    """Check Redis connection."""
    try:
        import redis as redis_lib

        r = redis_lib.from_url(settings.redis_url)
        r.ping()
        r.close()
        return {"status": "healthy", "redis": "connected"}
    except Exception as e:
        error_detail = str(e) if settings.is_dev else "Connection failed"
        return {"status": "unhealthy", "redis": "disconnected", "error": error_detail}
