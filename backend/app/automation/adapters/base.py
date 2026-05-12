"""
AutoJob AI — Platform Adapter Base
Abstract interface that ALL job platform adapters must implement.
To add a new platform: create a new file (e.g. naukri.py) that subclasses this.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class JobListing:
    """Standardized job data returned by all adapters."""
    platform: str
    platform_job_id: str
    title: str
    company: str
    location: str | None
    description: str | None
    salary_range: str | None
    job_type: str | None
    apply_url: str
    posted_date: str | None


class JobPlatformAdapter(ABC):
    """
    Abstract base class for job platform automation.

    Every job platform (LinkedIn, Naukri, Indeed, etc.) must implement
    these methods. Agents call adapter methods — they never interact
    with job platforms directly.
    """

    @abstractmethod
    async def login(self, credentials: dict) -> bool:
        """
        Log into the job platform.
        Returns True if login was successful.
        """
        ...

    @abstractmethod
    async def search_jobs(
        self,
        keywords: str,
        location: str | None = None,
        filters: dict | None = None,
        max_results: int = 25,
    ) -> list[JobListing]:
        """
        Search for jobs and return standardized listings.
        """
        ...

    @abstractmethod
    async def get_job_details(self, job_url: str) -> dict:
        """
        Get full details for a specific job (description, requirements, etc.)
        """
        ...

    @abstractmethod
    async def apply_to_job(
        self,
        job_url: str,
        resume_path: str,
        cover_letter: str | None = None,
        answers: dict | None = None,
    ) -> dict:
        """
        Apply to a job. Returns dict with status and details.
        Example: {"success": True, "confirmation_id": "..."}
        """
        ...

    @abstractmethod
    async def save_session(self, filepath: str) -> None:
        """Save browser session/cookies for reuse."""
        ...

    @abstractmethod
    async def load_session(self, filepath: str) -> bool:
        """Load a saved session. Returns True if session is still valid."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources (close browser, etc.)."""
        ...
