"""
AutoJob AI — Job Schemas
Pydantic models for job-related API requests and responses.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Request Schemas ──────────────────────────────────

class JobSearchRequest(BaseModel):
    """Request to trigger a LinkedIn job search."""
    keywords: str = Field(..., min_length=1, max_length=200, description="Job search keywords")
    location: str | None = Field(None, max_length=100, description="Location filter")
    max_results: int = Field(10, ge=1, le=100, description="Maximum results to return")

    # LinkedIn credentials (required for search)
    linkedin_email: str = Field(..., description="LinkedIn email")
    linkedin_password: str = Field(..., description="LinkedIn password")

    model_config = {
        "json_schema_extra": {
            "example": {
                "keywords": "React Developer",
                "location": "Bangalore",
                "max_results": 10,
                "linkedin_email": "YOUR_TEST_EMAIL@gmail.com",
                "linkedin_password": "YOUR_TEST_PASSWORD"
            }
        }
    }


# ── Response Schemas ─────────────────────────────────

class JobResponse(BaseModel):
    """Single job listing response."""
    id: str
    platform: str
    platform_job_id: str
    title: str
    company: str
    location: str | None
    description: str | None
    salary_range: str | None
    job_type: str | None
    apply_url: str
    scraped_at: datetime | None

    class Config:
        from_attributes = True


class JobSearchResponse(BaseModel):
    """Response after a job search operation."""
    status: str  # "success" or "error"
    message: str
    jobs_found: int = 0
    jobs_saved: int = 0
    jobs_skipped: int = 0
    jobs: list[JobResponse] = []


class JobListResponse(BaseModel):
    """Response for listing stored jobs."""
    count: int
    total: int
    jobs: list[JobResponse]
