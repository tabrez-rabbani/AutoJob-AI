"""
AutoJob AI — Application Schemas
Pydantic models for auto-apply API requests and responses.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class AutoApplyRequest(BaseModel):
    """Request to auto-apply to qualified jobs."""

    # LinkedIn credentials
    linkedin_email: str = Field(..., description="LinkedIn email")
    linkedin_password: str = Field(..., description="LinkedIn password")

    # Job search parameters
    keywords: str = Field(..., min_length=1, max_length=200, description="Job search keywords (e.g. 'React Developer')")
    location: str = Field("", description="Location filter (e.g. 'Bangalore')")

    # Optional fields for forms
    phone: str = Field("", description="Phone number for application forms")

    # Config
    max_applications: int = Field(5, ge=1, le=10, description="Max jobs to apply to (safety limit)")
    delay_seconds: int = Field(60, ge=10, le=300, description="Delay between applications")
    dry_run: bool = Field(True, description="If True, stops before final submit (test mode)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "linkedin_email": "YOUR_EMAIL@gmail.com",
                "linkedin_password": "YOUR_PASSWORD",
                "keywords": "React Developer",
                "location": "Bangalore",
                "phone": "+91-9876543210",
                "max_applications": 3,
                "delay_seconds": 60,
                "dry_run": True,
            }
        }
    }


class ApplicationResult(BaseModel):
    """Result of a single application attempt."""
    job_id: str
    job_title: str
    company: str
    apply_url: str
    status: str  # applied, external_apply, skipped, failed
    message: str


class AutoApplyResponse(BaseModel):
    """Response from the auto-apply endpoint."""
    status: str  # success / error
    message: str
    total_attempted: int = 0
    applied: int = 0
    external_apply: int = 0
    skipped: int = 0
    failed: int = 0
    dry_run: bool = True
    results: list[ApplicationResult] = []
