"""
AutoJob AI — Database Models
Import all models here so Alembic can discover them.
"""

from app.models.user import User, SubscriptionTier  # noqa: F401
from app.models.job import Job, JobPlatform, JobType  # noqa: F401
from app.models.application import Application, ApplicationStatus  # noqa: F401
