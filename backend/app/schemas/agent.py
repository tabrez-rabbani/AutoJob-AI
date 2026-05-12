"""
AutoJob AI — Agent Schemas
Pydantic models for AI agent API requests and responses.
"""

from pydantic import BaseModel, Field


# ── Request ──────────────────────────────────────────

class AnalyzeJobsRequest(BaseModel):
    """Request to analyze scraped jobs against a user profile."""

    # User profile (simplified — in production this comes from DB/auth)
    full_name: str = Field(..., description="User's full name")
    skills: list[str] = Field(..., min_length=1, description="User's skills")
    preferred_roles: list[str] = Field(..., min_length=1, description="Target roles")
    experience_years: int = Field(0, ge=0, description="Years of experience")
    resume_text: str | None = Field(None, description="Full resume text (optional)")

    # Analysis config
    match_threshold: int = Field(60, ge=0, le=100, description="Minimum match score to qualify")
    max_jobs: int = Field(10, ge=1, le=50, description="Max jobs to analyze")

    model_config = {
        "json_schema_extra": {
            "example": {
                "full_name": "Sohan Kumar",
                "skills": ["React", "JavaScript", "TypeScript", "Node.js", "CSS", "HTML"],
                "preferred_roles": ["Frontend Developer", "React Developer", "Full Stack Developer"],
                "experience_years": 2,
                "resume_text": None,
                "match_threshold": 60,
                "max_jobs": 10,
            }
        }
    }


# ── Response ─────────────────────────────────────────

class JobAnalysisResult(BaseModel):
    """Analysis result for a single job."""
    job_id: str
    job_title: str
    company: str
    match_score: int
    recommendation: str  # "apply", "skip", "maybe"
    match_reasons: list[str] = []
    missing_skills: list[str] = []
    match_summary: str = ""
    tailored_summary: str | None = None
    cover_letter: str | None = None
    key_highlights: list[str] = []


class AnalyzeJobsResponse(BaseModel):
    """Response from the job analysis pipeline."""
    status: str  # "success" or "error"
    message: str
    total_jobs: int = 0
    qualified: int = 0
    skipped: int = 0
    average_score: float = 0
    results: list[JobAnalysisResult] = []
    errors: list[str] = []
